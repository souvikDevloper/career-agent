const KEY = (tabId) => `career-agent-tab-${tabId}`;

async function remember(tabId, token, api) {
  await chrome.storage.session.set({ [KEY(tabId)]: { token, api, at: Date.now() } });
}

async function recalled(tabId) {
  const got = await chrome.storage.session.get(KEY(tabId));
  return got[KEY(tabId)] || null;
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
      await remember(tabId, msg.token, msg.api);
      return { ok: true };
    }
    const session = await recalled(tabId);
    if (!session) return { ok: false, missing: true };
    if (msg.type === "session") return { ok: true, session };
    if (msg.type === "packet") return { ok: true, data: await call(session, "") };
    if (msg.type === "start") return { ok: true, data: await call(session, "/start", "POST", {}) };
    if (msg.type === "dispatch") return { ok: true, data: await call(session, "/dispatch", "POST", {}) };
    if (msg.type === "complete") return { ok: true, data: await call(session, "/complete", "POST", msg.body || {}) };
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
