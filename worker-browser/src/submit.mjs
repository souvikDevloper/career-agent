// Browser automation core. Holds no business rules: it fills exactly the approved
// answers, reports the form it saw, and records the outcome through the gate.

export const RECEIPT_SELECTOR = "#receipt-reference";

export function hostAllowed(url, allowedHosts) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.hostname === "127.0.0.1"
      ? allowedHosts.some((h) => u.hostname === h || u.hostname.endsWith("." + h))
      : false;
  } catch {
    return false;
  }
}

export function isBlockedAddress(hostname) {
  return (
    hostname === "169.254.169.254" ||
    hostname.startsWith("169.254.") ||
    hostname === "metadata.google.internal" ||
    /^10\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(hostname) ||
    hostname === "localhost"
  );
}

/** Restrict every request the page makes to allowlisted hosts; never reach instance metadata. */
export async function lockDown(context, allowedHosts, { allowLocal = false } = {}) {
  await context.route("**/*", (route) => {
    const url = route.request().url();
    let host = "";
    try {
      host = new URL(url).hostname;
    } catch {
      return route.abort();
    }
    if (url.startsWith("data:") || url.startsWith("blob:")) return route.continue();
    if (!allowLocal && isBlockedAddress(host)) return route.abort();
    if (!allowedHosts.some((h) => host === h || host.endsWith("." + h))) return route.abort();
    return route.continue();
  });
}

/**
 * Fill the approved answers into the live form.
 * @returns {Promise<{filled:string[], missing:string[]}>}
 */
export async function fillForm(page, answers, resumePath) {
  const filled = [];
  const missing = [];
  for (const [name, value] of Object.entries(answers)) {
    const loc = page.locator(`[name="${cssEscape(name)}"]`);
    const count = await loc.count();
    if (count === 0) {
      missing.push(name);
      continue;
    }
    const first = loc.first();
    const tag = await first.evaluate((el) => el.tagName.toLowerCase());
    const type = (await first.getAttribute("type")) || "";
    if (value === "__RESUME__" || type === "file") {
      if (!resumePath) {
        missing.push(name);
        continue;
      }
      await first.setInputFiles(resumePath);
    } else if (tag === "select") {
      await first.selectOption(String(value));
    } else if (type === "checkbox") {
      await first.check();
    } else if (type === "radio") {
      await page.locator(`[name="${cssEscape(name)}"][value="${cssEscape(String(value))}"]`).check();
    } else {
      await first.fill(String(value));
    }
    filled.push(name);
  }
  return { filled, missing };
}

export function cssEscape(s) {
  return String(s).replace(/["\\]/g, "\\$&");
}

/**
 * Click submit and classify the result.
 * @returns {Promise<{outcome:"submitted"|"known_failure"|"unknown", reference?:string, reason?:string}>}
 */
export async function clickAndConfirm(page, { timeoutMs = 25000 } = {}) {
  const button = page.locator('button[type="submit"], input[type="submit"]').first();
  try {
    await Promise.all([
      page.waitForLoadState("domcontentloaded", { timeout: timeoutMs }).catch(() => {}),
      button.click({ timeout: 10000 }),
    ]);
  } catch (err) {
    return { outcome: "unknown", reason: `click/navigation error: ${String(err.message || err).slice(0, 160)}` };
  }
  try {
    const receipt = page.locator(RECEIPT_SELECTOR);
    await receipt.waitFor({ state: "visible", timeout: timeoutMs });
    const reference = (await receipt.textContent())?.trim();
    const submittedAt = await page.locator("#receipt").getAttribute("data-submitted-at");
    if (reference) return { outcome: "submitted", reference, submittedAt };
  } catch {
    // fall through to classify
  }
  const text = (await page.content().catch(() => "")).toLowerCase();
  if (text.includes("captcha")) return { outcome: "known_failure", reason: "captcha_required" };
  const errors = await page
    .locator("ul[style*='b42318'] li")
    .allTextContents()
    .catch(() => []);
  if (errors.length) return { outcome: "known_failure", reason: `employer form rejected: ${errors.join("; ").slice(0, 200)}` };
  return { outcome: "unknown", reason: "no confirmation received" };
}
