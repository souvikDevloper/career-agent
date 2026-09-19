const KEY = (tabId) => `career-agent-tab-${tabId}`;
const PENDING = "career-agent-pending-session";

function employerFamily(host) {
  host = String(host || "").toLowerCase();
  for (const suffix of [
    "amazon.jobs", "google.com", "microsoft.com", "myworkdayjobs.com",
    "lever.co", "ashbyhq.com", "oracle.com", "oraclecloud.com"
  ]) {
    if (host === suffix || host.endsWith("." + suffix)) return suffix;
  }
  return host;
}

async function remember(tabId, token, api, host) {
  const session = { token, api, at: Date.now(), family: employerFamily(host) };
  await chrome.storage.session.set({
    [KEY(tabId)]: session,
    [PENDING]: session,
  });
}

async function recalled(tabId, host) {
  const got = await chrome.storage.session.get([KEY(tabId), PENDING]);
  const own = got[KEY(tabId)];
  if (own) return own;

  // OAuth/login/application redirects can move the flow to another tab or
  // document before our first content script had a chance to bind it. Keep one
  // short-lived pending capability and allow only the same employer family to
  // claim it.
  const pending = got[PENDING];
  if (!pending || Date.now() - Number(pending.at || 0) > 10 * 60 * 1000) return null;
  if (pending.family && pending.family !== employerFamily(host)) return null;
  await chrome.storage.session.set({ [KEY(tabId)]: pending });
  return pending;
}

async function call(session, path, method = "GET", body) {
  const res = await fetch(`${session.api}/api/public/browser-session/${encodeURIComponent(session.token)}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message || `Career Agent returned ${res.status}`);
  return data;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    const tabId = sender.tab?.id;
    if (tabId == null) throw new Error("No browser tab");
    if (msg.type === "remember") {
      await remember(tabId, msg.token, msg.api, msg.host);
      return { ok: true };
    }
    const session = await recalled(tabId, msg.host);
    if (!session) return { ok: false, missing: true };
    if (msg.type === "session") return { ok: true, session };
    if (msg.type === "packet") return { ok: true, data: await call(session, "") };
    if (msg.type === "start") return { ok: true, data: await call(session, "/start", "POST", {}) };
    if (msg.type === "dispatch") return { ok: true, data: await call(session, "/dispatch", "POST", {}) };
    if (msg.type === "complete") return { ok: true, data: await call(session, "/complete", "POST", msg.body || {}) };
    if (msg.type === "save_answers") return { ok: true, data: await call(session, "/answers", "PUT", { answers: msg.answers || {} }) };
    if (msg.type === "resolve_questions") return {
      ok: true,
      data: await call(session, "/resolve-questions", "POST", { questions: msg.questions || [] })
    };
    if (msg.type === "resume") {
      const res = await fetch(msg.url);
      if (!res.ok) throw new Error(`Resume download failed (${res.status})`);
      const buf = new Uint8Array(await res.arrayBuffer());
      let binary = "";
      for (let i = 0; i < buf.length; i += 0x8000) binary += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      return { ok: true, base64: btoa(binary), type: res.headers.get("content-type") || "application/pdf" };
    }
    return { ok: false };
  })().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
  return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.remove(KEY(tabId)).catch(() => {});
});
