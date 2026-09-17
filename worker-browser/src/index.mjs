// Lambda entry: consumes the FIFO submission queue (one message per invocation).
import { writeFile } from "node:fs/promises";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { chromium as playwright } from "playwright-core";
import { clickAndConfirm, fillForm, hostAllowed, lockDown } from "./submit.mjs";

const lambda = new LambdaClient({});
const s3 = new S3Client({});
const GATE = process.env.GATE_FUNCTION;
const BUCKET = process.env.BUCKET_NAME;
const ALLOWED = (process.env.ALLOWED_TARGET_HOSTS || "").split(",").map((s) => s.trim()).filter(Boolean);

const log = (event, fields = {}) => console.log(JSON.stringify({ event, ...fields }));

async function gate(payload) {
  const res = await lambda.send(
    new InvokeCommand({ FunctionName: GATE, Payload: Buffer.from(JSON.stringify(payload)) }),
  );
  const body = JSON.parse(Buffer.from(res.Payload).toString("utf8") || "{}");
  if (res.FunctionError) throw new Error(`gate error: ${JSON.stringify(body).slice(0, 300)}`);
  return body;
}

async function download(url, path) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`resume download failed: ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length > 2 * 1024 * 1024) throw new Error("resume too large for target");
  await writeFile(path, buf);
}

export async function handler(event) {
  const failures = [];
  for (const record of event.Records || []) {
    try {
      const retry = await processMessage(JSON.parse(record.body));
      if (retry) failures.push({ itemIdentifier: record.messageId });
    } catch (err) {
      log("submit.error", { error: String(err.message || err).slice(0, 300) });
      failures.push({ itemIdentifier: record.messageId });
    }
  }
  return { batchItemFailures: failures };
}

async function processMessage(msg) {
  const ids = { user_id: msg.user_id, app_id: msg.app_id, attempt_id: msg.attempt_id };
  const begin = await gate({ op: "begin", ...ids, packet_hash: msg.packet_hash });
  log("gate.begin", { app_id: msg.app_id, action: begin.action, reason: begin.reason });
  if (begin.action !== "proceed") return Boolean(begin.retry_later);

  const target = begin.target?.url;
  if (!target || !hostAllowed(target, ALLOWED)) {
    await gate({ op: "complete", ...ids, outcome: "known_failure", reason: "target host is not an allowed destination" });
    return false;
  }

  const chromium = (await import("@sparticuz/chromium")).default;
  const browser = await playwright.launch({ args: chromium.args, executablePath: await chromium.executablePath(), headless: true });
  let dispatched = false;
  try {
    const context = await browser.newContext({ acceptDownloads: false, javaScriptEnabled: true, userAgent: "CareerAgentBot/1.0 (+test-employer)" });
    await lockDown(context, ALLOWED);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const resumePath = begin.resume_url ? `/tmp/${msg.attempt_id}-resume.pdf` : null;
    if (resumePath) await download(begin.resume_url, resumePath);

    const response = await page.goto(target, { waitUntil: "domcontentloaded", timeout: 20000 });
    if (!response || response.status() >= 400) throw new Error(`target returned ${response?.status()}`);
    const { missing } = await fillForm(page, begin.answers, resumePath);
    if (missing.length) {
      await gate({ op: "complete", ...ids, outcome: "known_failure", reason: `form fields missing on page: ${missing.join(", ")}` });
      return false;
    }
    const html = await page.content();
    const d = await gate({ op: "dispatch", ...ids, fencing: begin.fencing, form_html: html });
    log("gate.dispatch", { app_id: msg.app_id, action: d.action, reason: d.reason });
    if (d.action !== "submit") return false; // form changed or lease lost: nothing was sent

    dispatched = true; // ---- external write boundary ----
    const result = await clickAndConfirm(page);
    let evidenceKey;
    if (result.outcome === "submitted") {
      const shot = await page.screenshot({ fullPage: false, type: "png" });
      evidenceKey = `${begin.evidence_prefix}/receipt.png`;
      await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: evidenceKey, Body: shot, ContentType: "image/png", ServerSideEncryption: "AES256" }));
    }
    await gate({
      op: "complete", ...ids, outcome: result.outcome, reason: result.reason, evidence_key: evidenceKey,
      receipt: result.reference ? { reference: result.reference, submitted_at: result.submittedAt, url: page.url() } : undefined,
    });
    log("submit.done", { app_id: msg.app_id, outcome: result.outcome });
    return false;
  } catch (err) {
    const reason = String(err.message || err).slice(0, 200);
    await gate({ op: "complete", ...ids, outcome: dispatched ? "unknown" : "known_failure", reason }).catch(() => {});
    return false;
  } finally {
    await browser.close().catch(() => {});
  }
}
