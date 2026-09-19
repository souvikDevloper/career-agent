const KEY = (tabId) => `career-agent-tab-${tabId}`;
const RUNNER = "career-agent-browser-runner";
const RUNNER_ALARM = "career-agent-browser-runner-poll";
let polling = false;

async function pollRunner() {
  if (polling) return;
  polling = true;
  try {
    const runner = (await chrome.storage.local.get(RUNNER))[RUNNER];
    if (!runner || Date.now() >= runner.expiresAt) {
      await chrome.alarms.clear(RUNNER_ALARM);
      return;
    }
    let activeTab = null;
    if (runner.tabId != null) {
      try { activeTab = await chrome.tabs.get(runner.tabId); } catch { /* closed tab; backend decides whether the lease can resume */ }
    }
    const response = await fetch(`${runner.api}/api/public/browser-runner/${encodeURIComponent(runner.token)}/next`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if ([401, 403, 410].includes(response.status)) {
        await chrome.storage.local.remove(RUNNER);
        await chrome.alarms.clear(RUNNER_ALARM);
      }
      return;
    }
    const application = data.application;
    if (!application) return;
    const target = new URL(application.target_url);
    if (target.protocol !== "https:" || !/^[A-Za-z0-9_-]{20,}$/.test(application.token || "")) return;
    // Bind before navigation so a fast employer redirect cannot outrun session
    // storage. The runner grant never reaches the employer URL or page.
    const tab = activeTab && runner.appId === application.app_id ? activeTab : await chrome.tabs.create({ url: "about:blank", active: false });
    await remember(tab.id, application.token, runner.api, target.hostname);
    await chrome.storage.local.set({ [RUNNER]: { ...runner, tabId: tab.id, appId: application.app_id } });
    await chrome.tabs.update(tab.id, { url: target.href });
  } finally { polling = false; }
}

async function pairRunner(msg, sender) {
  const api = new URL(msg.api);
  const source = new URL(sender.url || "");
  if (source.protocol !== "https:" || api.origin !== source.origin || !/^\/app\/settings\/?$/.test(source.pathname) ||
      !/^[A-Za-z0-9_-]{20,}$/.test(msg.token || "")) throw new Error("Connect the browser from Career Agent Settings.");
  const requested = msg.expires_at ? Number(msg.expires_at) - Date.now() / 1000 : Number(msg.expires_in) || 7 * 86400;
  const duration = Math.min(Math.max(requested, 60), 7 * 86400);
  await chrome.storage.local.set({ [RUNNER]: { token: msg.token, api: api.origin, expiresAt: Date.now() + duration * 1000 } });
  await chrome.alarms.create(RUNNER_ALARM, { periodInMinutes: 1 });
  pollRunner().catch(() => {});
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RUNNER_ALARM) pollRunner().catch(() => {});
});
async function restoreRunner() {
  const runner = (await chrome.storage.local.get(RUNNER))[RUNNER];
  if (runner && runner.expiresAt > Date.now()) {
    await chrome.alarms.create(RUNNER_ALARM, { periodInMinutes: 1 });
    await pollRunner();
  }
}
chrome.runtime.onStartup.addListener(() => restoreRunner().catch(() => {}));
chrome.runtime.onInstalled.addListener(() => restoreRunner().catch(() => {}));

function employerFamily(host) {
  host = String(host || "").toLowerCase().replace(/^www\./, "");
  for (const suffix of [
    "amazon.jobs", "google.com", "microsoft.com"
  ]) {
    if (host === suffix || host.endsWith("." + suffix)) return suffix;
  }
  return host;
}

async function remember(tabId, token, api, host) {
  const session = { token, api, at: Date.now(), family: employerFamily(host) };
  await chrome.storage.session.set({
    [KEY(tabId)]: session,
  });
}

async function recalled(tabId, host, openerTabId, topHost) {
  const got = await chrome.storage.session.get([KEY(tabId), ...(openerTabId == null ? [] : [KEY(openerTabId)])]);
  const own = got[KEY(tabId)];
  if (own && Date.now() - Number(own.at || 0) <= 10 * 60 * 1000) {
    const sameEmployer = own.family === employerFamily(host);
    const employerEmbed = topHost && own.family === employerFamily(topHost) &&
      /(?:^|\.)(?:greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com)$/.test(host);
    return sameEmployer || employerEmbed ? own : null;
  }

  // A popup may inherit only its opener's session. A global pending session
  // allowed any unrelated employer tab to claim another application's packet.
  const pending = openerTabId == null ? null : got[KEY(openerTabId)];
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
  if (!res.ok) throw Object.assign(new Error(data?.error?.message || `Career Agent returned ${res.status}`), { code: data?.error?.code });
  return data;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    const tabId = sender.tab?.id;
    if (tabId == null) throw new Error("No browser tab");
    if (msg.type === "pair_runner") { await pairRunner(msg, sender); return { ok: true }; }
    if (msg.type === "remember") {
      await remember(tabId, msg.token, msg.api, msg.host);
      return { ok: true };
    }
    const senderHost = new URL(sender.url || sender.tab?.url || "https://invalid.local").hostname;
    const topHost = sender.frameId ? new URL(sender.tab?.url || "https://invalid.local").hostname : null;
    const session = await recalled(tabId, senderHost, sender.tab?.openerTabId, topHost);
    if (!session) return { ok: false, missing: true };
    if (msg.type === "session") return { ok: true, dispatched: !!session.dispatched };
    if (msg.type === "packet") return { ok: true, data: await call(session, "") };
    if (msg.type === "start") return { ok: true, data: await call(session, "/start", "POST", {}) };
    if (msg.type === "dispatch") {
      const data = await call(session, "/dispatch", "POST", {});
      await chrome.storage.session.set({ [KEY(tabId)]: { ...session, dispatched: true } });
      return { ok: true, data };
    }
    if (msg.type === "complete") {
      const data = await call(session, "/complete", "POST", msg.body || {});
      if (["submitted", "known_failure"].includes(msg.body?.outcome)) {
        const runner = (await chrome.storage.local.get(RUNNER))[RUNNER];
        if (runner?.tabId === tabId) {
          const { tabId: finishedTab, appId: finishedApp, ...grant } = runner;
          await chrome.storage.local.set({ [RUNNER]: grant });
        }
      }
      return { ok: true, data };
    }
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
  })().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e.message || e), code: e.code }));
  return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.remove(KEY(tabId)).catch(() => {});
});
