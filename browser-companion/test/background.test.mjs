import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../background.js', import.meta.url), 'utf8');
function worker(fetcher = async () => ({ ok: true, json: async () => ({}) })) {
  const session = {}, local = {}, tabs = new Map(), alarms = new Map();
  const storage = (data) => ({
    async get(keys) { return Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map((key) => [key, data[key]])); },
    async set(values) { Object.assign(data, values); },
    async remove(key) { delete data[key]; },
  });
  let handler, tabRemoved;
  const context = vm.createContext({ URL, Date, fetch: fetcher, btoa, Uint8Array, chrome: {
    storage: { session: storage(session), local: storage(local) },
    runtime: { onMessage: { addListener(fn) { handler = fn; } }, onStartup: { addListener() {} }, onInstalled: { addListener() {} } },
    alarms: { onAlarm: { addListener() {} }, async create(name, config) { alarms.set(name, config); }, async clear(name) { alarms.delete(name); } },
    tabs: {
      async create(value) { const tab = { id: tabs.size + 100, ...value }; tabs.set(tab.id, tab); return tab; },
      async update(id, value) { Object.assign(tabs.get(id), value); },
      async get(id) { if (!tabs.has(id)) throw new Error('closed'); return tabs.get(id); },
      onRemoved: { addListener(fn) { tabRemoved = fn; } },
    },
  } });
  vm.runInContext(`${source}\nthis.pollRunner = pollRunner;`, context);
  const message = (data, sender = { tab: { id: 1, url: 'https://adobe.wd5.myworkdayjobs.com/job/role' }, url: 'https://adobe.wd5.myworkdayjobs.com/job/role', frameId: 0 }) => new Promise((resolve) => handler(data, sender, resolve));
  return { message, session, local, tabs, alarms, poll: context.pollRunner, tabRemoved };
}
const token = 'capability_12345678901234567890';

test('sessions cannot leak to unrelated tabs, different Workday tenants, or a new host in the same tab', async () => {
  const w = worker();
  await w.message({ type: 'remember', token, api: 'https://career.example.test', host: 'adobe.wd5.myworkdayjobs.com' });
  assert.equal((await w.message({ type: 'session' })).ok, true);
  assert.equal((await w.message({ type: 'session' }, { tab: { id: 2 }, url: 'https://adobe.wd5.myworkdayjobs.com/job/other' })).ok, false);
  assert.equal((await w.message({ type: 'session' }, { tab: { id: 1 }, url: 'https://evil.example.test' })).ok, false);
  assert.equal((await w.message({ type: 'session' }, { tab: { id: 3, openerTabId: 1 }, url: 'https://other.wd5.myworkdayjobs.com/job/other' })).ok, false);
  assert.equal((await w.message({ type: 'session' }, { tab: { id: 4, openerTabId: 1 }, url: 'https://adobe.wd5.myworkdayjobs.com/job/role' })).ok, true);
});

test('API conflict codes reach content and successful dispatch remains remembered after navigation', async () => {
  let failed = true;
  const w = worker(async () => failed ? { ok: false, json: async () => ({ error: { code: 'already_dispatched', message: 'Already dispatched' } }) } : { ok: true, json: async () => ({ application: {} }) });
  await w.message({ type: 'remember', token, api: 'https://career.example.test', host: 'adobe.wd5.myworkdayjobs.com' });
  assert.equal((await w.message({ type: 'dispatch' })).code, 'already_dispatched');
  failed = false;
  assert.equal((await w.message({ type: 'dispatch' })).ok, true);
  assert.equal((await w.message({ type: 'session' })).dispatched, true);
});

test('paired runner opens one inactive employer tab with a session bound before navigation, without exposing grant', async () => {
  const requests = [];
  const w = worker(async (url) => { requests.push(url); return { ok: true, json: async () => ({ application: requests.length === 1 ? { app_id: 'app_one', token, target_url: 'https://adobe.wd5.myworkdayjobs.com/job/role' } : null }) }; });
  const result = await w.message({ type: 'pair_runner', token: 'runner_12345678901234567890', api: 'https://career.example.test', expires_in: 86400 }, { tab: { id: 10 }, url: 'https://career.example.test/app/settings' });
  assert.equal(result.ok, true);
  for (let i = 0; i < 20 && !w.tabs.size; i++) await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  await w.poll();
  assert.equal(w.tabs.size, 1);
  const tab = [...w.tabs.values()][0];
  assert.equal(tab.active, false);
  assert.equal(tab.url, 'https://adobe.wd5.myworkdayjobs.com/job/role');
  assert.equal(w.session[`career-agent-tab-${tab.id}`].token, token);
  assert.equal(w.alarms.size, 1);
  assert.equal(requests.length, 2); // Keep checking backend after a manual dashboard completion.
});

test('pairing rejects cross-origin API and non-settings pages', async () => {
  const w = worker();
  assert.equal((await w.message({ type: 'pair_runner', token, api: 'https://other.example.test' }, { tab: { id: 1 }, url: 'https://career.example.test/app/settings' })).ok, false);
  assert.equal((await w.message({ type: 'pair_runner', token, api: 'https://career.example.test' }, { tab: { id: 1 }, url: 'https://career.example.test/app/jobs' })).ok, false);
  assert.equal(w.alarms.size, 0);
});

test('runner rebinds an expired unstarted lease in the existing tab and advances only when the server returns a new application', async () => {
  let next = { app_id: 'app_one', token, target_url: 'https://adobe.wd5.myworkdayjobs.com/job/one' };
  const w = worker(async () => ({ ok: true, json: async () => ({ application: next }) }));
  await w.message({ type: 'pair_runner', token: 'runner_12345678901234567890', api: 'https://career.example.test' }, { tab: { id: 10 }, url: 'https://career.example.test/app/settings' });
  await new Promise((resolve) => setImmediate(resolve));
  next = { ...next, token: `${token}_renewed` };
  await w.poll();
  assert.equal(w.tabs.size, 1);
  assert.equal(w.session['career-agent-tab-100'].token, `${token}_renewed`);
  next = { app_id: 'app_two', token: `${token}_second`, target_url: 'https://adobe.wd5.myworkdayjobs.com/job/two' };
  await w.poll();
  assert.equal(w.tabs.size, 2);
  assert.equal(w.local['career-agent-browser-runner'].appId, 'app_two');
});
