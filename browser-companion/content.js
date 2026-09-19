(() => {
  if (window.__careerAgentCompanion) return;
  window.__careerAgentCompanion = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const send = (msg) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(msg, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!res?.ok) return reject(new Error(res?.error || "Browser companion is not connected"));
      resolve(res);
    });
  });

  function banner(text, tone = "info") {
    let box = document.getElementById("career-agent-companion-status");
    if (!box) {
      box = document.createElement("div");
      box.id = "career-agent-companion-status";
      Object.assign(box.style, {
        position: "fixed", right: "18px", bottom: "18px", zIndex: "2147483647",
        maxWidth: "390px", padding: "12px 14px", borderRadius: "12px",
        font: "13px/1.45 system-ui,sans-serif", color: "white",
        boxShadow: "0 10px 35px rgba(0,0,0,.3)"
      });
      document.documentElement.appendChild(box);
    }
    box.style.background = tone === "bad" ? "#8b1e3f" : tone === "good" ? "#116149" : "#312e81";
    box.textContent = text;
  }

  function visible(el) {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
  }

  const PLACEHOLDER_CHOICE = /^(select|choose|please select)( an?)? (option|answer)|^select an option$/;

  function questionContainer(el) {
    let node = el.parentElement;
    for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
      const text = String(node.textContent || "").trim();
      if (text.length >= 12 && text.length <= 900 &&
          (text.includes("?") || text.includes("*") || /required/i.test(text))) {
        return node;
      }
    }
    return el.parentElement;
  }

  function rawLabelOf(el) {
    const parts = [];
    const labelled = String(el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
    for (const id of labelled) {
      const n = document.getElementById(id);
      if (n) parts.push(n.textContent);
    }
    parts.push(el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.getAttribute("name"), el.id);
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) parts.push(lab.textContent);
    }
    const parent = el.closest("label");
    if (parent) parts.push(parent.textContent);
    const group = el.closest("[data-automation-id], .form-group, .field, [role='group'], fieldset");
    if (group) {
      const lab = group.querySelector("legend, label, [class*='label'], [class*='question']");
      if (lab) parts.push(lab.textContent);
    }
    const q = questionContainer(el);
    if (q) parts.push(q.textContent?.slice(0, 700));
    return parts.filter(Boolean).join(" ");
  }

  function labelOf(el) {
    let text = norm(rawLabelOf(el));
    text = text
      .replace(/select an option/g, " ")
      .replace(/please select an option/g, " ")
      .replace(/required fields?/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return text;
  }

  function controls() {
    return [...document.querySelectorAll("input, textarea, select")].filter((el) => visible(el) && !el.disabled);
  }

  function customChoiceControls() {
    const nodes = [...document.querySelectorAll("[role='combobox'], [aria-haspopup='listbox'], button")];
    return nodes.filter((el, index) => {
      if (!visible(el) || el.disabled) return false;
      const roleChoice = el.getAttribute("role") === "combobox" || el.getAttribute("aria-haspopup") === "listbox";
      const placeholderButton = el.tagName === "BUTTON" && PLACEHOLDER_CHOICE.test(norm(el.textContent || el.getAttribute("aria-label") || ""));
      if (!roleChoice && !placeholderButton) return false;
      // Avoid returning both a wrapper and its nested real combobox.
      return !nodes.some((other, j) => j !== index && other !== el && el.contains(other) &&
        (other.getAttribute("role") === "combobox" || other.getAttribute("aria-haspopup") === "listbox"));
    });
  }

  function allControls() {
    return [...new Set([...controls(), ...customChoiceControls()])];
  }

  function isCustomChoice(el) {
    return el.tagName !== "SELECT" &&
      (el.getAttribute("role") === "combobox" || el.getAttribute("aria-haspopup") === "listbox" ||
       (el.tagName === "BUTTON" && PLACEHOLDER_CHOICE.test(norm(el.textContent || ""))));
  }

  function findControl(key, exactName) {
    const all = allControls();
    if (exactName) {
      const exact = all.find((el) => el.name === exactName || el.id === exactName);
      if (exact) return exact;
    }
    const k = norm(key);
    const aliases = {
      "full name": ["full name", "legal name", "name"],
      "email": ["email", "email address"],
      "phone": ["phone", "phone number", "mobile"],
      "why this role": ["why this role", "cover letter", "interest", "why are you interested"],
    };
    const wants = aliases[k] || [k];
    let best = null;
    let bestScore = 0;
    for (const el of all) {
      const label = labelOf(el);
      let score = 0;
      for (const w of wants) {
        if (label === w) score = Math.max(score, 5);
        else if (label.includes(w)) score = Math.max(score, 3);
      }
      if (k === "full name" && /first name|last name|surname/.test(label)) score = 4;
      if (score > bestScore) { best = el; bestScore = score; }
    }
    return best;
  }

  function openOptionNodes() {
    const selectors = [
      "[role='option']", "[role='listbox'] li", "[role='listbox'] button",
      "[data-testid*='option']", "[class*='option']"
    ];
    const seen = new Set();
    const out = [];
    for (const el of document.querySelectorAll(selectors.join(","))) {
      if (!visible(el)) continue;
      const text = String(el.textContent || el.getAttribute("aria-label") || "").trim();
      const key = norm(text);
      if (!key || key.length > 180 || seen.has(key)) continue;
      seen.add(key);
      out.push(el);
    }
    return out;
  }

  async function optionTexts(el) {
    if (el.tagName === "SELECT") {
      return [...el.options]
        .map((o) => String(o.textContent || o.value || "").trim())
        .filter((x) => x && !PLACEHOLDER_CHOICE.test(norm(x)));
    }
    if (!isCustomChoice(el)) return [];
    if (el.getAttribute("aria-expanded") !== "true") el.click();
    await sleep(180);
    const values = openOptionNodes().map((o) => String(o.textContent || o.getAttribute("aria-label") || "").trim());
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    if (el.getAttribute("aria-expanded") === "true") el.click();
    await sleep(60);
    return [...new Set(values)];
  }

  async function setValue(el, value) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "select") {
      const wanted = norm(value);
      const opt = [...el.options].find((o) => norm(o.value) === wanted || norm(o.textContent) === wanted);
      if (!opt) return false;
      el.value = opt.value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    if (isCustomChoice(el)) {
      const wanted = norm(value);
      if (el.getAttribute("aria-expanded") !== "true") el.click();
      await sleep(180);
      const options = openOptionNodes();
      const hit = options.find((o) => {
        const got = norm(o.textContent || o.getAttribute("aria-label") || "");
        return got === wanted ||
          ((wanted === "yes" || wanted === "no") && got.split(" ")[0] === wanted);
      });
      if (!hit) {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return false;
      }
      hit.click();
      await sleep(120);
      return true;
    }
    if (type === "checkbox") {
      const yes = /^(true|yes|1|on|agree|i agree)$/i.test(String(value));
      if (el.checked !== yes) el.click();
      return true;
    }
    if (type === "radio") {
      const group = [...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name)}"]`)];
      const wanted = norm(value);
      const hit = group.find((x) => norm(x.value) === wanted || labelOf(x).includes(wanted));
      if (!hit) return false;
      hit.click();
      return true;
    }
    const proto = tag === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    setter ? setter.call(el, String(value)) : (el.value = String(value));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  async function attachResume(resumeUrl) {
    if (!resumeUrl) return false;
    const files = controls().filter((el) => el.tagName === "INPUT" && (el.type || "").toLowerCase() === "file");
    if (!files.length) return false;
    const target = files.find((el) => /resume|cv/.test(labelOf(el))) || files[0];
    const data = await send({ type: "resume", url: resumeUrl });
    const bytes = Uint8Array.from(atob(data.base64), (c) => c.charCodeAt(0));
    const file = new File([bytes], "resume.pdf", { type: data.type || "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    target.files = dt.files;
    target.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  async function fill(packet) {
    let filled = 0;
    const fields = new Map((packet.fields || []).map((f) => [f.name, f]));
    for (const [key, raw] of Object.entries(packet.answers || {})) {
      if (raw === "__RESUME__") continue;
      const field = fields.get(key);
      const label = field?.label || key;
      if (norm(key) === "full name") {
        const first = controls().find((x) => /first name/.test(labelOf(x)));
        const last = controls().find((x) => /last name|surname/.test(labelOf(x)));
        const parts = String(raw).trim().split(/\s+/);
        if (first && await setValue(first, parts[0] || "")) filled++;
        if (last && await setValue(last, parts.slice(1).join(" ") || parts[0] || "")) filled++;
        if (first || last) continue;
      }
      const el = findControl(label, field?.name || key);
      if (el && await setValue(el, raw)) filled++;
    }
    if (await attachResume(packet.resume_url).catch(() => false)) filled++;
    return filled;
  }

  function attentionNeeded() {
    if (controls().some((el) => (el.type || "").toLowerCase() === "password")) {
      return "Please sign in to the employer account. Career Agent will continue after login.";
    }
    const body = norm(document.body?.innerText || "");
    if (/verification code|two factor|two-factor|multi factor|multi-factor|one time password|otp/.test(body)) {
      return "Complete the employer verification/MFA step. Career Agent will continue afterwards.";
    }
    const captcha = [...document.querySelectorAll('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[title*="challenge" i]')]
      .some((el) => visible(el));
    if (captcha) return "Complete the visible CAPTCHA. Career Agent does not bypass it.";
    return null;
  }

  function choiceText(el) {
    if (el.tagName === "SELECT") {
      return String(el.selectedOptions?.[0]?.textContent || el.value || "").trim();
    }
    return String(el.getAttribute("aria-valuetext") || el.getAttribute("data-value") ||
                  el.textContent || el.getAttribute("aria-label") || "").trim();
  }

  function choiceEmpty(el) {
    const value = norm(choiceText(el));
    return !value || PLACEHOLDER_CHOICE.test(value) || value === "select" || value === "choose";
  }

  function requiredLike(el) {
    if (el.required || el.getAttribute("aria-required") === "true") return true;
    const q = questionContainer(el);
    const text = String(q?.textContent || "");
    return text.includes("*") || /\brequired\b/i.test(text);
  }

  function unansweredRequired() {
    const out = [];
    for (const el of allControls()) {
      const type = (el.getAttribute("type") || "").toLowerCase();
      let empty = false;
      let required = requiredLike(el);

      if (el.tagName === "SELECT" || isCustomChoice(el)) {
        empty = choiceEmpty(el);
        // Authenticated screening pages often render required custom selects
        // without aria-required. A placeholder choice directly under a
        // question is still something we must not skip.
        if (empty && /\?|\*/.test(String(questionContainer(el)?.textContent || ""))) required = true;
      } else if (type === "checkbox" || type === "radio") {
        empty = el.name ? !document.querySelector(`[name="${CSS.escape(el.name)}"]:checked`) : !el.checked;
      } else if (type === "file") {
        empty = !(el.files && el.files.length);
      } else {
        empty = !String(el.value || "").trim();
      }
      if (required && empty) {
        const label = labelOf(el).slice(0, 180) || el.name || el.id || "required field";
        if (label && !PLACEHOLDER_CHOICE.test(norm(label))) out.push(label);
      }
    }
    return [...new Set(out)].slice(0, 6);
  }

  const SENSITIVE_FIELD = /password|passcode|verification|otp|captcha|social security|ssn|date of birth|dob|race|ethnicity|gender|sex|disability|veteran|marital|religion|sexual orientation|national id|aadhaar|pan number|passport/;

  function learnedAnswers() {
    const out = {};
    const seenRadio = new Set();
    for (const el of allControls()) {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "password", "file", "submit"].includes(type)) continue;
      const label = labelOf(el).slice(0, 120);
      if (!label || SENSITIVE_FIELD.test(label)) continue;

      let value = "";
      if (isCustomChoice(el)) {
        value = choiceText(el);
        if (choiceEmpty(el)) continue;
      } else if (type === "radio") {
        if (!el.name || seenRadio.has(el.name)) continue;
        seenRadio.add(el.name);
        const checked = document.querySelector(`input[type="radio"][name="${CSS.escape(el.name)}"]:checked`);
        if (!checked) continue;
        value = checked.value || labelOf(checked);
      } else if (type === "checkbox") {
        value = el.checked ? "Yes" : "No";
      } else if (el.tagName === "SELECT") {
        value = choiceText(el);
        if (choiceEmpty(el)) continue;
      } else {
        if (type === "button") continue;
        value = el.value;
      }
      value = String(value || "").trim();
      if (value) out[label] = value.slice(0, 1000);
    }
    return out;
  }

  async function resolveVisibleQuestions() {
    const discovered = [];
    const byLabel = new Map();
    for (const el of allControls()) {
      if (!(el.tagName === "SELECT" || isCustomChoice(el)) || !choiceEmpty(el)) continue;
      const label = labelOf(el).slice(0, 600);
      if (!label || SENSITIVE_FIELD.test(label) || byLabel.has(label)) continue;
      const options = await optionTexts(el).catch(() => []);
      discovered.push({ label, options, required: requiredLike(el) });
      byLabel.set(label, el);
    }
    if (!discovered.length) return 0;

    const response = await send({ type: "resolve_questions", questions: discovered }).catch(() => null);
    const answers = response?.data?.answers || [];
    let filled = 0;
    for (const answer of answers) {
      const el = byLabel.get(answer.label) || findControl(answer.label);
      if (el && choiceEmpty(el) && await setValue(el, answer.value)) filled++;
    }
    if (filled) {
      banner(`Career Agent filled ${filled} screening answer${filled === 1 ? "" : "s"} from your verified profile.`, "good");
      await rememberLearnedAnswers();
    }
    return filled;
  }

  async function rememberLearnedAnswers() {
    const answers = learnedAnswers();
    if (Object.keys(answers).length) {
      await send({ type: "save_answers", answers }).catch(() => {});
    }
  }

  async function waitForUser(getReason, timeoutMs = 8 * 60 * 1000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const reason = getReason();
      if (!reason) {
        await rememberLearnedAnswers();
        return true;
      }
      banner(reason);
      await sleep(1000);
    }
    return false;
  }

  function continueInSameTab(el) {
    const href = el?.href || el?.getAttribute?.("href");
    if (href && /^https?:/i.test(href)) {
      location.href = href;
    } else {
      el.click();
    }
  }

  function actionButton(re) {
    return [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button'], a")]
      .filter(visible)
      .find((el) => re.test(norm(el.textContent || el.value || el.getAttribute("aria-label") || "")));
  }

  function confirmed() {
    const text = norm(document.body?.innerText || "");
    return /thank you for applying|thanks for applying|application (has been )?(submitted|received)|we have received your application|application complete/.test(text);
  }

  async function complete(outcome, extra = {}) {
    return send({ type: "complete", body: { outcome, url: location.href, provider: location.hostname, ...extra } });
  }

  async function run() {
    try {
      const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
      const token = hash.get("career-agent-session");
      const api = hash.get("career-agent-api");
      if (token && api) {
        await send({ type: "remember", token, api, host: location.hostname });
        hash.delete("career-agent-session");
        hash.delete("career-agent-api");
        history.replaceState(null, "", location.pathname + location.search + (hash.toString() ? "#" + hash : ""));
      }

      const remembered = await chrome.runtime.sendMessage({ type: "session", host: location.hostname });
      if (!remembered?.ok) return;

      const packet = (await send({ type: "packet" })).data;
      let started = false;
      banner(`Career Agent: ready to apply to ${packet.title || "this role"}…`);

      for (let step = 0; step < 12; step++) {
        await sleep(900);

        const attention = attentionNeeded();
        if (attention) {
          const resolved = await waitForUser(() => attentionNeeded());
          if (!resolved) {
            await complete("needs_user", { reason: attention }).catch(() => {});
            banner("Career Agent paused. Finish the sign-in or verification step, then reopen this application.", "bad");
            return;
          }
        }

        if (!started) {
          await send({ type: "start" });
          started = true;
          banner(`Career Agent: filling ${packet.title || "this application"}…`);
        }

        await fill(packet);
        await resolveVisibleQuestions();
        await sleep(450);

        if (confirmed()) {
          await complete("submitted", { reference: "confirmed-by-employer-page" });
          banner("Career Agent: employer confirmed the application.", "good");
          return;
        }

        let required = unansweredRequired();
        if (required.length) {
          const reason = () => {
            required = unansweredRequired();
            return required.length ? `Needs your answer: ${required.join("; ")}` : null;
          };
          const resolved = await waitForUser(reason);
          if (!resolved) {
            await complete("needs_user", { reason: reason() || "Required employer question still needs an answer." });
            return;
          }
          banner("Career Agent: got it. I saved that answer for later applications and am continuing…", "good");
        }

        await rememberLearnedAnswers();

        const final = actionButton(/^(submit application|submit|send application|complete application)$/);
        if (final) {
          await send({ type: "dispatch" });
          banner("Career Agent: submitting the approved packet…");
          final.click();
          await sleep(5000);
          if (confirmed()) {
            await complete("submitted", { reference: "confirmed-by-employer-page" });
            banner("Career Agent: employer confirmed the application.", "good");
          } else {
            await complete("unknown", { reason: "Submit was clicked but employer confirmation could not be verified." });
            banner("Submit was clicked, but confirmation is unclear. Check before retrying.", "bad");
          }
          return;
        }

        const next = actionButton(/^(continue|next|save and continue|save continue|continue application)$/);
        if (next) {
          await rememberLearnedAnswers();
          continueInSameTab(next);
          await sleep(1200);
          continue;
        }

        const apply = actionButton(/^(apply|apply now|apply for this role|apply to this job|start application|continue application)$/);
        if (apply && controls().length < 3) {
          continueInSameTab(apply);
          await sleep(1500);
          continue;
        }

        // Amazon has optional interstitial steps such as SMS Notifications.
        // Their button copy varies between "Skip", "Not now" and "Save & Continue".
        // Only take a skip-style action when the current page explicitly says
        // the step is optional; never skip an unknown required question.
        const pageText = norm(document.body?.innerText || "");
        if (/optional/.test(pageText)) {
          const skip = actionButton(/^(skip|skip for now|not now|continue without|save continue)$/);
          if (skip) {
            await rememberLearnedAnswers();
            continueInSameTab(skip);
            await sleep(1200);
            continue;
          }
        }

        // Some employer career pages (notably Greenhouse-backed custom
        // sites) embed the actual application form in a cross-origin iframe.
        // The companion is injected into that frame too; the top document must
        // not declare failure while the child frame is doing the real work.
        const embeddedApplication = [...document.querySelectorAll("iframe[src]")].some((frame) => {
          const src = String(frame.getAttribute("src") || "").toLowerCase();
          return /greenhouse|workday|lever|ashby|application|apply/.test(src);
        });
        if (embeddedApplication && window.top === window) {
          banner("Career Agent: continuing inside the embedded employer application…");
          await sleep(1500);
          continue;
        }

        const reason = "Career Agent could not safely identify the next application control. Continue manually on this page.";
        banner(reason);
        await complete("needs_user", { reason });
        return;
      }
      await complete("needs_user", { reason: "Application has more steps than the companion can safely automate in one run." });
    } catch (e) {
      banner(`Career Agent stopped: ${String(e.message || e)}`, "bad");
    }
  }

  run();
})();
