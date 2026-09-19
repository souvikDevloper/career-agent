// Browser automation core. Holds no business rules: it fills exactly the approved
// answers, reports the form it saw, and records the outcome through the gate.

export const RECEIPT_SELECTOR = "#receipt-reference";

// Read after the submit click, and only alongside the form having gone away.
// A posting page can say "thank you for applying" in its own copy, so the text
// alone is not evidence that anything was sent.
export const CONFIRMATION_PATTERNS = [
  /thank you for applying/i,
  /thanks for applying/i,
  /your application (?:has been |was )?(?:successfully )?(?:submitted|received)/i,
  /we(?:'ve| have) received your application/i,
  /application (?:submitted|received|complete)/i,
];

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
 * Find a field by the identifier the employer's own API gave us.
 *
 * The same identifier reaches the page as a different attribute depending on who
 * built the form: the test portal names its inputs, Greenhouse renders a React
 * form whose text inputs carry only `id`, and its multi-selects use
 * `name="question_123[]"`. Looking only at `name` meant every field on a real
 * Greenhouse form came back missing and the packet was abandoned before submit.
 */
export function fieldLocator(page, name) {
  const e = cssEscape(name);
  return page.locator(`[name="${e}"], [name="${e}[]"], [id="${e}"]`);
}

/**
 * Fill the approved answers into the live form.
 * @returns {Promise<{filled:string[], missing:string[]}>}
 */
export async function fillForm(page, answers, resumePath) {
  const filled = [];
  const missing = [];
  for (const [name, value] of Object.entries(answers)) {
    const loc = fieldLocator(page, name);
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
      const v = cssEscape(String(value));
      const e = cssEscape(name);
      await page.locator(`[name="${e}"][value="${v}"], [id="${e}"][value="${v}"]`).check();
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
 * Whether the page is actually challenging us, rather than merely having a
 * captcha configured.
 *
 * Nearly every ATS page mentions "captcha" in its source: Greenhouse ships
 * `GOOGLE_RECAPTCHA_INVISIBLE_KEY` and `"disable_captcha": false` in a config
 * blob on every job. Searching the HTML for the word therefore reported
 * captcha_required for every submission including the ones that worked. An
 * invisible captcha only surfaces when it is suspicious, and what surfaces is a
 * visible frame asking a person to prove something - so that is what we look for.
 */
export async function captchaChallenged(page) {
  const frames = page.locator(
    'iframe[src*="recaptcha/api2/bframe"], iframe[src*="hcaptcha.com"][src*="challenge"], iframe[title*="challenge" i]',
  );
  const count = await frames.count().catch(() => 0);
  for (let i = 0; i < count; i++) {
    if (await frames.nth(i).isVisible().catch(() => false)) return true;
  }
  return false;
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
  if (await captchaChallenged(page)) {
    return { outcome: "known_failure", reason: "captcha_required" };
  }
  const errors = await page
    .locator("ul[style*='b42318'] li")
    .allTextContents()
    .catch(() => []);
  if (errors.length) return { outcome: "known_failure", reason: `employer form rejected: ${errors.join("; ").slice(0, 200)}` };

  // A board that issues no reference number still has to be distinguishable from
  // a page that silently did nothing. Require both halves: wording that says it
  // arrived, and the form no longer being on the page.
  const stillShowingForm = await page
    .locator('button[type="submit"], input[type="submit"]')
    .count()
    .catch(() => 1);
  const visible = await page.locator("body").innerText().catch(() => "");
  if (!stillShowingForm && CONFIRMATION_PATTERNS.some((re) => re.test(visible))) {
    return { outcome: "submitted", reason: "confirmed by page wording; employer issued no reference" };
  }
  return { outcome: "unknown", reason: "no confirmation received" };
}
