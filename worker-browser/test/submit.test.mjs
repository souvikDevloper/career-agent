import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { captchaChallenged, clickAndConfirm, fillForm, hostAllowed, isBlockedAddress, lockDown } from "../src/submit.mjs";

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

test("fills a Greenhouse-shaped form addressed by id, and accepts a reference-less confirmation", async (t) => {
  // Greenhouse gives the same identifier as the questions API, but the page
  // carries it as `id` on text inputs and as `name="...[]"` on multi-selects.
  // Looking only at `name` reported every field missing and abandoned the packet.
  const chromium = await loadPlaywright();
  if (!chromium) return t.skip("playwright not installed");
  const server = http.createServer((req, res) => {
    const body = req.method === "GET" ? fixture("greenhouse-apply.html") : fixture("greenhouse-confirm.html");
    res.writeHead(200, { "Content-Type": "text/html" });
    if (req.method === "GET") return res.end(body);
    req.on("data", () => {});
    req.on("end", () => res.end(body));
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
    await page.goto(`http://127.0.0.1:${port}/twilio/jobs/8177722`);
    const answers = {
      first_name: "Asha", last_name: "Rao", email: "asha@example.test", phone: "+91 90000 00000",
      resume: "__RESUME__", question_68976768: "1", question_68976769: "7",
      cover_letter_text: "I build serverless Python APIs.",
    };
    const { filled, missing } = await fillForm(page, answers, join(here, "fixtures", "resume.pdf"));
    assert.deepEqual(missing, [], "every Greenhouse field should be reachable");
    assert.equal(filled.length, Object.keys(answers).length);
    assert.equal(await page.locator("#first_name").inputValue(), "Asha");
    assert.equal(await page.locator("#question_68976768").inputValue(), "1");

    const result = await clickAndConfirm(page, { timeoutMs: 8000 });
    assert.equal(result.outcome, "submitted");
    assert.equal(result.reference, undefined, "Greenhouse issues no reference number");
  } finally {
    await browser.close();
    server.close();
  }
});

test("wording alone is not a submission", async (t) => {
  // A posting page may say "thank you for applying" in its own copy. Reporting
  // that as submitted would invent a receipt for an application never sent.
  const chromium = await loadPlaywright();
  if (!chromium) return t.skip("playwright not installed");
  const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(`<!doctype html><html><body>
      <p>Thank you for applying to roles at our company.</p>
      <form method="post"><input id="first_name" type="text" /><button type="submit">Submit</button></form>
      </body></html>`);
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
    await page.goto(`http://127.0.0.1:${port}/x`);
    const result = await clickAndConfirm(page, { timeoutMs: 4000 });
    assert.equal(result.outcome, "unknown", "the form is still on the page, so nothing was confirmed");
  } finally {
    await browser.close();
    server.close();
  }
});

test("a configured captcha is not a challenge; a visible one is", async (t) => {
  // Greenhouse ships GOOGLE_RECAPTCHA_INVISIBLE_KEY and "disable_captcha": false
  // in a config blob on every job page. Searching the HTML for "captcha" reported
  // captcha_required for every Greenhouse submission, including successful ones.
  const chromium = await loadPlaywright();
  if (!chromium) return t.skip("playwright not installed");
  const pages = {
    configured: `<!doctype html><html><body>
        <script>window.CONFIG = {"GOOGLE_RECAPTCHA_INVISIBLE_KEY":"6Lfmcbcp","disable_captcha":false};</script>
        <h1>Thank you for applying</h1><p>We have received your application.</p>
      </body></html>`,
    challenged: `<!doctype html><html><body>
        <iframe title="recaptcha challenge expires in two minutes" src="https://www.google.com/recaptcha/api2/bframe?x=1"
                style="width:400px;height:580px"></iframe>
        <form method="post"><button type="submit">Submit</button></form>
      </body></html>`,
  };
  let which = "configured";
  const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(pages[which]);
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
    await lockDown(context, ["127.0.0.1", "google.com"], { allowLocal: true });
    const page = await context.newPage();

    await page.goto(`http://127.0.0.1:${port}/x`);
    assert.equal(await captchaChallenged(page), false, "a config blob is not a challenge");

    which = "challenged";
    await page.goto(`http://127.0.0.1:${port}/y`);
    assert.equal(await captchaChallenged(page), true, "a visible challenge frame is");
    const result = await clickAndConfirm(page, { timeoutMs: 4000 });
    assert.equal(result.reason, "captcha_required");
  } finally {
    await browser.close();
    server.close();
  }
});
