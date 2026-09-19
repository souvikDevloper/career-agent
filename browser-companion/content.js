(() => {
  if (window.__careerAgentCompanion) return;
  window.__careerAgentCompanion = true;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => String(value || "").toLowerCase().replace(/\(s\)/g, "s").replace(/[^a-z0-9]+/g, " ").trim();
  const clean = (value) => String(value || "").replace(/\s+/g, " ").replace(/\s*\*\s*$/, "").trim();
  const send = (msg) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(msg, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!res?.ok) return reject(Object.assign(new Error(res?.error || "Browser companion is not connected"), { code: res?.code }));
      resolve(res);
    });
  });
  const PLACEHOLDER = /^(?:(?:please )?(?:select|choose)(?: (?:an?|your|one|the))?(?: (?:option|answer|value|country|state|month|year))?|no selection)$/;
  const SENSITIVE = /\b(password|passcode|verification|otp|captcha|social security|ssn|date of birth|dob|race|ethnicity|gender|sex|disability|veteran|marital|religion|sexual orientation|national id|aadhaar|pan number|passport)\b/;
  const FIELD_GROUP = "[data-automation-id^='formField'], .form-group, .form-field, .field, fieldset, [role='group']";
  let stopped = false;
  let started = false;
  let dispatched = false;

  window.addEventListener("message", async (event) => {
    if (event.source !== window || event.origin !== location.origin || event.data?.type !== "CAREER_AGENT_PAIR_BROWSER") return;
    if (location.protocol !== "https:" || !/^\/app\/settings\/?$/.test(location.pathname)) return;
    const requestId = String(event.data.requestId || "").slice(0, 100);
    try {
      if (!navigator.userActivation?.isActive) throw new Error("Click Connect browser in Settings to pair this browser.");
      const api = new URL(event.data.api);
      if (api.origin !== location.origin) throw new Error("The browser must be connected from your Career Agent dashboard.");
      await send({ type: "pair_runner", token: event.data.token, api: api.origin, expires_in: event.data.expires_in, expires_at: event.data.expires_at });
      window.postMessage({ type: "CAREER_AGENT_BROWSER_PAIRED", requestId, ok: true }, location.origin);
    } catch (error) { window.postMessage({ type: "CAREER_AGENT_BROWSER_PAIRED", requestId, ok: false, error: String(error.message || error) }, location.origin); }
  });

  function banner(message, tone = "info") {
    let box = document.getElementById("career-agent-companion-status");
    if (!box) {
      box = document.createElement("div"); box.id = "career-agent-companion-status"; box.setAttribute("role", "status");
      Object.assign(box.style, { position: "fixed", right: "18px", bottom: "18px", zIndex: "2147483647", maxWidth: "430px", padding: "12px 14px", borderRadius: "12px", font: "13px/1.45 system-ui,sans-serif", color: "white", boxShadow: "0 10px 35px rgba(0,0,0,.3)" });
      box.appendChild(document.createElement("span"));
      const pause = document.createElement("button"); pause.textContent = "Pause";
      Object.assign(pause.style, { marginLeft: "12px", color: "white", background: "transparent", border: "1px solid currentColor", borderRadius: "4px", cursor: "pointer" });
      pause.onclick = () => { stopped = true; box.firstChild.textContent = "Career Agent paused. Reopen this application from Career Agent to resume."; pause.remove(); };
      box.appendChild(pause); document.documentElement.appendChild(box);
    }
    box.style.background = tone === "bad" ? "#8b1e3f" : tone === "good" ? "#116149" : "#312e81";
    box.firstChild.textContent = message;
  }
  function visible(el) {
    if (!el?.isConnected || el.closest("#career-agent-companion-status, [hidden], [aria-hidden='true'], [inert]")) return false;
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }
  function enabled(el) { return !el.disabled && el.getAttribute("aria-disabled") !== "true"; }
  function explicitLabel(el) {
    const labelled = (el.getAttribute("aria-labelledby") || "").split(/\s+/).map((id) => document.getElementById(id)?.textContent).filter(Boolean);
    if (labelled.length) return clean(labelled.join(" "));
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label"));
    const labels = [...(el.labels || [])].map((label) => label.textContent);
    if (labels.length) return clean(labels.join(" "));
    if (el.id) { const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (label) return clean(label.textContent); }
    return "";
  }
  function questionContainer(el) {
    const group = el.closest(FIELD_GROUP); if (group) return group;
    // Stop before a wrapper containing multiple unrelated questions.
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
      const children = node.querySelectorAll("input:not([type='hidden']), textarea, select, [role='combobox'], [aria-haspopup]");
      const text = clean(node.textContent);
      if (children.length <= 1 && text.length > 2 && text.length < 700 && /[?*]/.test(text)) return node;
      if (children.length > 1) break;
    }
    return el.parentElement;
  }
  function labelOf(el) {
    const group = questionContainer(el);
    if (el.type === "radio" && group) {
      const legend = group.querySelector("legend, [data-automation-id='formLabel'], [class*='question'], label:not([for])");
      if (legend && !legend.contains(el)) return clean(legend.textContent);
      const groupLabel = explicitLabel(group); if (groupLabel) return groupLabel;
    }
    const direct = explicitLabel(el); if (direct && !PLACEHOLDER.test(norm(direct))) return direct;
    if (group) {
      const label = group.querySelector("legend, [data-automation-id='formLabel'], label, [class*='label'], [class*='question']");
      if (label && !label.contains(el)) return clean(label.textContent);
      const clone = group.cloneNode(true);
      clone.querySelectorAll("input,textarea,select,button,[role='combobox'],[role='listbox'],[role='option'],[role='alert']").forEach((node) => node.remove());
      const text = clean(clone.textContent); if (text.length > 2 && text.length <= 600) return text;
    }
    return clean(el.getAttribute("placeholder") || el.name || el.id);
  }
  function fieldContext(el) {
    const partLabel = norm(explicitLabel(el) || el.getAttribute("placeholder"));
    const inputAutomation = el.getAttribute("data-automation-id") || "";
    const datePart = /^(month|mm)$/.test(partLabel) || inputAutomation === "dateSectionMonth" ? "month" :
      /^(year|yyyy)$/.test(partLabel) || inputAutomation === "dateSectionYear" ? "year" : undefined;
    const dateContext = {};
    let node = el.parentElement;
    while (node && node !== document.body) {
      const automation = node.getAttribute("data-automation-id") || "";
      if (datePart && !dateContext.date_field) {
        const dateLabel = norm(explicitLabel(node) || node.querySelector(":scope > label, :scope > legend, :scope > [data-automation-id='formLabel']")?.textContent);
        const dateField = /^(from|start date)$/.test(dateLabel) || /^formField[-_]startDate$/i.test(automation) ? "start" :
          /^(to|end date)$/.test(dateLabel) || /^formField[-_]endDate$/i.test(automation) ? "end" : undefined;
        if (dateField) Object.assign(dateContext, { date_field: dateField, date_part: datePart });
      }
      const heading = [...node.children].find((child) => child.matches("h2,h3,h4,legend,[data-automation-id='panelTitle']"));
      const repeated = norm(heading?.textContent).match(/^(?:work )?(experience|education)\s*(\d+)$/);
      if (repeated) return { section: repeated[1], index: Number(repeated[2]) - 1, ...dateContext };
      if (/^(workExperience|education)-\d+$/.test(automation)) return { section: automation.startsWith("work") ? "experience" : "education", index: Number(automation.split("-").pop()), ...dateContext };
      node = node.parentElement;
    }
    return undefined;
  }
  function currentRoleCheckbox(el) {
    return el.type === "checkbox" && fieldContext(el)?.section === "experience" &&
      /^(i currently work here|i currently work in this role|currently work here)$/.test(norm(labelOf(el)));
  }
  function isCustomChoice(el) {
    if (el.tagName === "SELECT") return false;
    return el.getAttribute("role") === "combobox" || ["listbox", "true", "menu", "dialog"].includes(el.getAttribute("aria-haspopup")) ||
      (el.tagName === "BUTTON" && (PLACEHOLDER.test(norm(el.textContent)) || /^(selectWidget|dropdown|promptOption)$/i.test(el.getAttribute("data-automation-id") || "")));
  }
  function controls() {
    const nodes = [...document.querySelectorAll("input,textarea,select,[role='combobox'],[aria-haspopup],button")]
      .filter((el) => visible(el) && enabled(el) && (el.matches("input,textarea,select") || isCustomChoice(el)))
      .filter((el) => !["button", "submit", "reset", "hidden", "password"].includes((el.getAttribute("type") || "").toLowerCase()) || isCustomChoice(el));
    return nodes.filter((el) => !nodes.some((other) => other !== el && el.contains(other)));
  }
  function radioGroup(el) { return el.name ? [...(el.form || document).querySelectorAll(`input[type='radio'][name="${CSS.escape(el.name)}"]`)].filter(visible) : [el]; }
  function radioLabel(el) { return explicitLabel(el) || clean(el.value); }
  function choiceText(el) {
    if (el.tagName === "SELECT") return clean(el.selectedOptions?.[0]?.textContent || el.value);
    return clean(el.getAttribute("aria-valuetext") || el.getAttribute("data-value") || el.value || el.textContent);
  }
  function empty(el) {
    if (el.type === "radio") return !radioGroup(el).some((radio) => radio.checked);
    if (el.type === "checkbox") return !el.checked;
    if (el.type === "file") return !el.files?.length && el.dataset.careerAgentUploaded !== "true";
    if (el.tagName === "SELECT" || isCustomChoice(el)) { const text = norm(choiceText(el)); return !text || PLACEHOLDER.test(text) || (el.tagName === "SELECT" && !el.value); }
    return !clean(el.value);
  }
  function requiredLike(el) {
    if (el.required || el.getAttribute("aria-required") === "true") return true;
    const group = questionContainer(el);
    const labelNode = el.labels?.[0] || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || group?.querySelector("label,legend,[data-automation-id='formLabel']");
    const labelled = (el.getAttribute("aria-labelledby") || "").split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ");
    const question = labelNode?.textContent || labelled || el.getAttribute("aria-label") || (clean(group?.textContent).length < 700 ? group?.textContent : "");
    return /\*|\brequired\b/i.test(question || "") || !!group?.querySelector("[aria-label='Required'],[data-automation-id='required']");
  }
  function unansweredRequired() {
    const uploads = [...document.querySelectorAll("input[type='file']")].filter((el) => enabled(el) && visible(questionContainer(el)));
    return [...new Set([...controls(), ...uploads].filter((el) => requiredLike(el) && empty(el)).map(labelOf))].filter(Boolean).slice(0, 8);
  }
  async function until(predicate, timeout = 2000, interval = 80) {
    const end = Date.now() + timeout;
    do { const value = predicate(); if (value) return value; await sleep(interval); } while (!stopped && Date.now() < end);
    return null;
  }
  function optionNodes(el) {
    const ids = `${el.getAttribute("aria-controls") || ""} ${el.getAttribute("aria-owns") || ""}`.split(/\s+/).filter(Boolean);
    const roots = ids.map((id) => document.getElementById(id)).filter((root) => root && visible(root));
    if (ids.length && !roots.length) return [];
    if (!roots.length) roots.push(...[...document.querySelectorAll("[role='listbox'],[role='menu'],[data-automation-id='promptOption'],.dropdown-menu")].filter(visible));
    const selector = "[role='option'],[role='menuitem'],[data-automation-id='promptOption'],[data-automation-id='menuItem'],li,button";
    const candidates = roots.length ? roots.flatMap((root) => [root, ...root.querySelectorAll(selector)]) : [...document.querySelectorAll("[role='option'],[data-automation-id='promptOption']")];
    return [...new Set(candidates)].filter((node) => visible(node) && enabled(node) && node !== el && clean(node.textContent).length < 300)
      .filter((node, _, nodes) => !nodes.some((other) => other !== node && node.contains(other)));
  }
  async function openChoice(el) {
    if (el.getAttribute("aria-expanded") !== "true") el.click();
    return (await until(() => { const options = optionNodes(el); return options.length ? options : null; })) || [];
  }
  function closeChoice(el) { el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true })); if (el.getAttribute("aria-expanded") === "true") el.click(); }
  async function optionTexts(el) {
    if (el.tagName === "SELECT") return [...el.options].filter((option) => !option.disabled && option.value).map((option) => clean(option.textContent)).filter((text) => text && !PLACEHOLDER.test(norm(text)));
    if (el.type === "radio") return radioGroup(el).map(radioLabel);
    if (currentRoleCheckbox(el)) return ["Yes", "No"];
    if (!isCustomChoice(el)) return [];
    const texts = [...new Set((await openChoice(el)).map((option) => clean(option.textContent)).filter(Boolean))]; closeChoice(el); return texts;
  }
  async function setValue(el, value) {
    if (!el.isConnected || !enabled(el) || value == null) return false;
    const wanted = norm(value);
    if (el.tagName === "SELECT") {
      const option = [...el.options].find((candidate) => !candidate.disabled && (norm(candidate.value) === wanted || norm(candidate.textContent) === wanted));
      if (!option) return false;
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, option.value);
    } else if (isCustomChoice(el)) {
      const option = (await openChoice(el)).find((candidate) => norm(candidate.textContent) === wanted || norm(candidate.getAttribute("data-value")) === wanted);
      if (!option) { closeChoice(el); return false; }
      option.click(); return !!await until(() => !el.isConnected || !empty(el), 1200);
    } else if (el.type === "radio") {
      const option = radioGroup(el).find((candidate) => norm(radioLabel(candidate)) === wanted || norm(candidate.value) === wanted);
      if (!option) return false; option.click(); return option.checked;
    } else if (el.type === "checkbox") {
      if (!/^(true|false|yes|no|1|0|on|off|agree|i agree)$/i.test(String(value))) return false;
      const checked = /^(true|yes|1|on|agree|i agree)$/i.test(String(value)); if (el.checked !== checked) el.click(); return el.checked === checked;
    } else {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, String(value));
    }
    el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); el.dispatchEvent(new FocusEvent("blur", { bubbles: true })); return !empty(el);
  }
  const ALIASES = {
    "full name": ["full name", "legal name", "name"], "email": ["email", "email address"], "phone": ["phone", "phone number", "mobile", "mobile number"],
    "current employer": ["current employer", "current company"], "current title": ["current title", "current job title"],
    "university": ["university", "college", "school", "school or university"], "graduation year": ["graduation year", "year of graduation"],
    "why this role": ["why this role", "cover letter", "why are you interested in this role"],
  };
  function findControl(label, exactName) {
    const all = controls().filter(empty), exact = exactName && all.find((el) => el.name === exactName || el.id === exactName);
    if (exact) return exact;
    const aliases = ALIASES[norm(label)] || [norm(label)]; return all.find((el) => !fieldContext(el) && aliases.includes(norm(labelOf(el))));
  }
  async function attachResume(url) {
    if (!url) return false;
    // Workday and other ATS products hide the native file input behind a widget.
    const files = [...document.querySelectorAll("input[type='file']")].filter((el) => enabled(el) && !el.files?.length);
    const target = files.find((el) => /\b(resume|cv)\b/i.test(labelOf(el))) || (files.length === 1 && /\b(resume|cv)\b/i.test(questionContainer(files[0])?.textContent) ? files[0] : null);
    if (!target || target.dataset.careerAgentUploaded === "true") return false;
    const data = await send({ type: "resume", url }), bytes = Uint8Array.from(atob(data.base64), (char) => char.charCodeAt(0)), dt = new DataTransfer();
    const type = data.type || "application/pdf";
    const extension = /wordprocessingml/i.test(type) ? "docx" : /msword/i.test(type) ? "doc" : "pdf";
    dt.items.add(new File([bytes], `resume.${extension}`, { type })); target.files = dt.files; target.dataset.careerAgentUploaded = "true";
    target.dispatchEvent(new Event("input", { bubbles: true })); target.dispatchEvent(new Event("change", { bubbles: true })); return true;
  }
  async function fill(packet) {
    let filled = 0; const fields = new Map((packet.fields || []).map((field) => [field.name, field]));
    for (const [key, value] of Object.entries(packet.answers || {})) {
      if (stopped || value === "__RESUME__") continue;
      const field = fields.get(key);
      if (norm(key) === "full name") {
        const parts = String(value).trim().split(/\s+/);
        for (const el of controls().filter(empty)) {
          const label = norm(labelOf(el));
          if (/^(first name|given names?)$/.test(label) && await setValue(el, parts[0])) filled++;
          if (/^(last name|family name|surname)$/.test(label) && parts.length > 1 && await setValue(el, parts.slice(1).join(" "))) filled++;
        }
      }
      const el = findControl(field?.label || key, field?.name || key); if (el && await setValue(el, value)) filled++;
    }
    if (await attachResume(packet.resume_url).catch(() => false)) filled++; return filled;
  }
  async function expandRecords(packet) {
    // Add only records actually present in the approved packet. Locate an Add
    // button inside a single, explicitly headed history section; never click a
    // generic page-wide Add button or synthesize empty history rows.
    const records = packet.profile_records || {};
    for (const [section, names] of [["experience", /^(work experience|employment history)$/], ["education", /^education$/]]) {
      const wanted = Math.min(Array.isArray(records[section]) ? records[section].length : 0, 20);
      if (!wanted) continue;
      const heading = [...document.querySelectorAll("h2,h3,h4,legend")].find((node) => visible(node) && names.test(norm(node.textContent)));
      if (!heading) continue;
      let scope = heading.parentElement;
      for (let depth = 0; scope && depth < 4; depth++, scope = scope.parentElement) {
        const foreign = [...scope.querySelectorAll("h2,h3,h4,legend")].some((node) => node !== heading && /^(education|work experience|employment history)$/.test(norm(node.textContent)) && !names.test(norm(node.textContent)));
        if (foreign) break;
        const add = [...scope.querySelectorAll("button,[role='button']")].find((node) => visible(node) && enabled(node) && /^add(?: (?:work )?experience| education| another)?$/.test(norm(node.textContent)));
        if (!add) continue;
        const count = () => new Set(controls().filter((el) => scope.contains(el)).map(fieldContext).filter((context) => context?.section === section).map((context) => context.index)).size;
        for (let added = count(); added < wanted && !stopped; added++) {
          const before = count();
          const currentAdd = [...scope.querySelectorAll("button,[role='button']")].find((node) => visible(node) && enabled(node) && /^add(?: (?:work )?experience| education| another)?$/.test(norm(node.textContent)));
          if (!currentAdd) break;
          currentAdd.click();
          if (!await until(() => count() > before, 2500)) break;
        }
        break;
      }
    }
  }
  const userAnswers = new Map();
  document.addEventListener("change", (event) => {
    if (!event.isTrusted || !(event.target instanceof Element)) return;
    const el = event.target, label = labelOf(el);
    if (!label || SENSITIVE.test(norm(label)) || /\b(agree|consent|acknowledge|privacy|terms|declaration)\b/.test(norm(label)) || ["password", "file", "hidden"].includes(el.type) || fieldContext(el)) return;
    const value = el.type === "radio" ? radioLabel(el) : el.type === "checkbox" ? (el.checked ? "Yes" : "No") : el.tagName === "SELECT" || isCustomChoice(el) ? choiceText(el) : el.value;
    if (value && !empty(el)) userAnswers.set(label.slice(0, 600), String(value).slice(0, 1000));
  }, true);
  async function rememberLearnedAnswers() {
    if (!userAnswers.size) return;
    const answers = Object.fromEntries([...userAnswers].slice(0, 30)); await send({ type: "save_answers", answers }); Object.keys(answers).forEach((key) => userAnswers.delete(key));
  }
  let nextFieldId = 0; const fieldIds = new WeakMap();
  function fieldId(el) { if (!fieldIds.has(el)) fieldIds.set(el, `field-${++nextFieldId}`); return fieldIds.get(el); }
  async function resolveVisibleQuestions() {
    const byId = new Map(), seenRadio = new Set(), questions = [];
    for (const el of controls()) {
      if (stopped || !empty(el) || ["file", "password"].includes(el.type) || (el.type === "checkbox" && !currentRoleCheckbox(el))) continue;
      if (el.type === "radio" && seenRadio.has(el.name)) continue;
      if (el.type === "radio") seenRadio.add(el.name);
      const label = labelOf(el).slice(0, 600); if (!label || SENSITIVE.test(norm(label))) continue;
      const options = await optionTexts(el); if (isCustomChoice(el) && !options.length) continue;
      const id = fieldId(el); questions.push({ id, label, options: options.slice(0, 50), required: requiredLike(el), context: fieldContext(el) }); byId.set(id, el);
    }
    let filled = 0;
    for (let start = 0; start < questions.length; start += 30) {
      const batch = questions.slice(start, start + 30), response = await send({ type: "resolve_questions", questions: batch });
      for (const answer of response?.data?.answers || []) {
        const matching = batch.filter((question) => question.label === answer.label);
        const el = byId.get(answer.id) || (matching.length === 1 ? byId.get(matching[0].id) : null);
        if (!stopped && el?.isConnected && empty(el) && await setValue(el, answer.value)) filled++;
      }
    }
    return filled;
  }
  function attentionNeeded() {
    if ([...document.querySelectorAll("input[type='password']")].some(visible)) return "Sign in to the employer account. Career Agent will continue after login.";
    if ([...document.querySelectorAll("input")].filter(visible).some((el) => /verification code|one time|two factor|\botp\b/.test(norm(labelOf(el))) || el.autocomplete === "one-time-code")) return "Complete the employer verification step. Career Agent will continue afterwards.";
    if ([...document.querySelectorAll("iframe[src*='recaptcha'],iframe[src*='hcaptcha'],iframe[title*='challenge' i]")].some((el) => visible(el) && el.getBoundingClientRect().height > 70)) return "Complete the visible CAPTCHA. Career Agent will continue afterwards.";
    return null;
  }
  function actionButton(pattern) {
    return [...document.querySelectorAll("button,input[type='submit'],input[type='button'],[role='button'],a")].filter((el) => visible(el) && enabled(el) && !isCustomChoice(el))
      .find((el) => pattern.test(norm(el.textContent || el.value || el.getAttribute("aria-label"))));
  }
  function confirmed() { return /thank you for applying|thanks for applying|application (has been )?(submitted|received)|we have received your application|application complete/.test(norm(document.body?.innerText)); }
  function fingerprint() { return JSON.stringify([location.href, controls().map((el) => [labelOf(el), el.type, choiceText(el), el.checked]), [...document.querySelectorAll("h1,h2,h3,[role='alert'],button,input[type='submit']")].filter(visible).map((el) => [clean(el.textContent || el.value), enabled(el)])]); }
  async function waitForChange(before, reason, timeout = 8 * 60 * 1000) { banner(reason); return !!await until(() => stopped || fingerprint() !== before || confirmed(), timeout, 500); }
  async function complete(outcome, extra = {}) { return send({ type: "complete", body: { outcome, url: location.href, provider: location.hostname, ...extra } }); }
  async function reconcile() {
    banner("Career Agent is checking the employer confirmation. It will not submit this application again.");
    if (await until(confirmed, 15000)) { await complete("submitted", { reference: "confirmed-by-employer-page" }); banner("Career Agent: employer confirmed the application.", "good"); }
    else { await complete("unknown", { reason: "Submit was dispatched but employer confirmation could not be verified." }).catch(() => {}); banner("Submission was attempted, but confirmation is unclear. Check the employer application history before retrying.", "bad"); }
  }
  async function run() {
    try {
      const hash = new URLSearchParams(location.hash.replace(/^#/, "")), token = hash.get("career-agent-session"), api = hash.get("career-agent-api");
      if (token && api) {
        await send({ type: "remember", token, api, host: location.hostname }); hash.delete("career-agent-session"); hash.delete("career-agent-api");
        history.replaceState(null, "", location.pathname + location.search + (hash.toString() ? "#" + hash : ""));
      }
      const remembered = await chrome.runtime.sendMessage({ type: "session", host: location.hostname }); if (!remembered?.ok) return;
      const packet = (await send({ type: "packet" })).data;
      dispatched = !!(packet.dispatched_at || packet.local_browser_dispatched_at || remembered.dispatched);
      if (packet.action_state === "Submitted") { banner("This application is already recorded as submitted.", "good"); return; }
      if (dispatched || packet.action_state === "OutcomeUnknown") { await reconcile(); return; }
      if (window.top !== window && !controls().length) return;
      if (window.top === window && [...document.querySelectorAll("iframe[src]")].some((frame) => /greenhouse|workday|lever|ashby|application|apply/i.test(frame.src))) { banner("Career Agent: continuing inside the embedded employer application…"); return; }
      banner(`Career Agent: preparing ${packet.title || "this application"}…`);
      await until(() => controls().length || actionButton(/^(apply|apply now|apply manually|continue|next|save and continue)$/) || attentionNeeded(), 12000);
      let requiredDeadline = 0;
      for (let step = 0; step < 80 && !stopped; step++) {
        const attention = attentionNeeded(); if (attention) { banner(attention); if (!await until(() => !attentionNeeded(), 8 * 60 * 1000, 500)) break; }
        if (stopped) break;
        if (!started) { await send({ type: "start" }); started = true; }
        if (confirmed()) { await complete("submitted", { reference: "confirmed-by-employer-page" }); banner("Career Agent: employer confirmed the application.", "good"); return; }
        await expandRecords(packet);
        const count = await fill(packet) + await resolveVisibleQuestions();
        if (count) banner(`Career Agent filled ${count} field${count === 1 ? "" : "s"} from your approved packet and verified profile.`, "good");
        await sleep(350); if (stopped) break;
        const required = unansweredRequired();
        if (required.length) {
          if (!requiredDeadline) requiredDeadline = Date.now() + 8 * 60 * 1000;
          const remaining = requiredDeadline - Date.now();
          if (remaining <= 0) break;
          // A saved answer may arrive through Profile while the employer DOM
          // remains unchanged. Re-check the server periodically, retaining the
          // original deadline so an unresolved question cannot loop forever.
          await waitForChange(fingerprint(), `Needs your answer: ${required.join("; ")}. Answer here or save it in Profile; I will check again automatically.`, Math.min(10000, remaining));
          if (Date.now() >= requiredDeadline) break;
          await rememberLearnedAnswers(); continue;
        }
        requiredDeadline = 0;
        await rememberLearnedAnswers();
        const final = actionButton(/^(submit application|submit|send application|complete application)$/);
        if (final) {
          await send({ type: "dispatch" }); dispatched = true;
          if (stopped) { await complete("unknown", { reason: "Paused after dispatch authorization; inspect employer status." }); return; }
          banner("Career Agent: submitting the approved application…"); final.click(); await reconcile(); return;
        }
        const next = actionButton(/^(continue|next|save and continue|save continue|continue application|review application|apply manually)$/);
        const apply = controls().length < 3 && actionButton(/^(apply|apply now|apply for this role|apply to this job|start application)$/);
        const action = next || apply, before = fingerprint();
        if (action) {
          banner("Career Agent: continuing to the next application step…");
          if (action.href && /^https:/i.test(action.href)) location.href = action.href; else action.click();
          if (await until(() => fingerprint() !== before || confirmed(), 7000)) { await sleep(450); continue; }
          if (!await waitForChange(before, "The employer has not advanced. Check highlighted validation messages or complete the current step; I will continue when it changes.")) break;
        } else if (!await waitForChange(before, "Career Agent is waiting for the application form. Open the next step or answer any highlighted question; I will continue automatically.")) break;
      }
      if (stopped && !started) {
        // Record an early Pause too, so a paired runner cannot reopen the same
        // unstarted application when its launch lease later expires.
        await send({ type: "start" }); started = true;
      }
      if (started && !dispatched) await complete("needs_user", { reason: stopped ? "Paused by the user." : "Waiting for employer form input or navigation." }).catch(() => {});
    } catch (error) {
      if (error.code === "already_dispatched" || /already dispatched/i.test(error.message || "")) { await reconcile().catch(() => {}); return; }
      if (started && !dispatched) await complete("needs_user", { reason: String(error.message || error).slice(0, 450) }).catch(() => {});
      banner(`Career Agent paused: ${String(error.message || error)}`, "bad");
    }
  }
  run();
})();
