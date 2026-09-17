import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { clickAndConfirm, fillForm, hostAllowed, isBlockedAddress, lockDown } from "../src/submit.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (n) => readFileSync(join(here, "fixtures", n));

async function loadPlaywright() {
  for (const name of ["playwright-core", "playwright"]) {
    try {
      return (await import(name)).chromium;
    } catch {}
  }
  return null;
}

test("host allowlist and metadata blocking", () => {
  assert.equal(hostAllowed("https://abc.execute-api.us-east-1.amazonaws.com/portal/jobs/x/apply", ["abc.execute-api.us-east-1.amazonaws.com"]), true);
  assert.equal(hostAllowed("http://abc.execute-api.us-east-1.amazonaws.com/x", ["abc.execute-api.us-east-1.amazonaws.com"]), false);
  assert.equal(hostAllowed("https://evil.example/x", ["abc.execute-api.us-east-1.amazonaws.com"]), false);
  assert.equal(isBlockedAddress("169.254.169.254"), true);
});

test("fills the real portal form and reads the receipt", async (t) => {
  const chromium = await loadPlaywright();
  if (!chromium) return t.skip("playwright not installed");
  let posted = "";
  const server = http.createServer((req, res) => {
    if (req.method === "GET") {
      res.writeHead(200, { "Content-Type": "text/html" });
      return res.end(fixture("apply.html"));
    }
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      posted = Buffer.concat(chunks).toString("latin1");
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(fixture("receipt.html"));
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (e) {
    server.close();
    return t.skip("browser binary unavailable: " + e.message);
  }
  try {
    const context = await browser.newContext();
    await lockDown(context, ["127.0.0.1"], { allowLocal: true });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/portal/jobs/nw-100/apply`);
    const answers = {
      first_name: "Aarav", last_name: "Mehta", email: "aarav.mehta@example.com", phone: "+91 90000 00000",
      resume: "__RESUME__", university: "Deccan Institute of Technology (fictional)", graduation_year: "2027",
      work_authorization: "yes", start_date: "2027-01-10", why_northwind: "I build serverless Python APIs.", gender: "decline", accuracy: "yes",
    };
    const { filled, missing } = await fillForm(page, answers, join(here, "fixtures", "resume.pdf"));
    assert.deepEqual(missing, []);
    assert.equal(filled.length, Object.keys(answers).length);
    const result = await clickAndConfirm(page, { timeoutMs: 8000 });
    assert.equal(result.outcome, "submitted");
    assert.equal(result.reference, "NWL-ABC123");
    assert.match(posted, /name="work_authorization"\r\n\r\nyes/);
    assert.match(posted, /filename="resume.pdf"/);
  } finally {
    await browser.close();
    server.close();
  }
});
