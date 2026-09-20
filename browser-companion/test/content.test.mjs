import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from '../../worker-browser/node_modules/playwright-core/index.mjs';

const source = (await readFile(new URL('../content.js', import.meta.url), 'utf8')).replace(/\r\n/g, '\n');
const exported = source.replace('  run();\n})();', '  window.forms = { labelOf, fieldContext, controls, unansweredRequired, fill, optionTexts, setValue, resolveVisibleQuestions, expandRecords, rememberLearnedAnswers, run };\n})();');
let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { await browser?.close(); });

async function pageFor(html, options = {}) {
  const page = await browser.newPage();
  await page.setContent(html);
  await page.evaluate((config) => {
    window.calls = [];
    window.profileAnswers = config.answers || {};
    window.packet = config.packet || { title: 'Software Engineer', answers: {}, fields: [] };
    window.chrome = { runtime: { sendMessage: (message, callback) => {
      window.calls.push(message);
      let response = { ok: true, data: {} };
      if (message.type === 'packet') response.data = window.packet;
      if (message.type === 'resume') response = { ok: true, base64: btoa('%PDF-1.4 fixture'), type: 'application/pdf' };
      if (message.type === 'resolve_questions') {
        response.data.answers = message.questions.flatMap((question) => {
          const date = question.context?.date_field ? `${question.context.date_field}:${question.context.date_part}:` : '';
          const key = question.context ? `${question.context.section}:${question.context.index}:${date}${question.label}` : question.label;
          const value = window.profileAnswers[key];
          return value === undefined ? [] : [{ id: question.id, label: question.label, value, source: 'fixture:verified_profile' }];
        });
      }
      if (callback) { callback(response); return; }
      return Promise.resolve(response);
    } } };
  }, options);
  await page.addScriptTag({ content: exported });
  return page;
}

test('Stripe cover-letter file and optional transcript never receive text; resume still uploads and submission continues', async () => {
  const page = await pageFor(`<div class="field"><label for="resume">Resume*</label><input id="resume" type="file" required hidden></div>
    <div class="field"><label for="cover_letter">Cover letter</label><input id="cover_letter" name="cover_letter" type="file"></div>
    <div class="field"><label for="transcript">Academic record (optional, not required)</label><input id="transcript" type="file"></div>
    <button onclick="document.body.innerHTML='Thank you for applying'">Submit application</button>`, {
    packet: { answers: { cover_letter: 'My truthful application note' }, fields: [{ name: 'cover_letter', label: 'Cover letter', type: 'file' }], resume_url: 'https://resume.example.test/file' }
  });
  await page.evaluate(() => forms.run());
  const messages = await page.evaluate(() => calls);
  assert.equal(messages.filter(m => m.type === 'dispatch').length, 1);
  assert.ok(messages.some(m => m.type === 'complete' && m.body.outcome === 'submitted'));
  await page.close();
});

test('nested Workday education uses actual backend degree/date/GPA mapping and never adds a duplicate', async () => {
  const page = await pageFor(`<section><h2>Education</h2><div class="record"><div><h3>Education 1</h3></div>
    <div class="field"><label for="school">School or University*</label><input id="school"></div>
    <div class="field"><label>Degree*</label><button id="degree" aria-label="Degree Select One Required" aria-haspopup="listbox" aria-controls="degrees">Select One</button><ul id="degrees" role="listbox" hidden><li role="option">Bachelor's Degree</li><li role="option">Master's Degree</li></ul></div>
    <div class="field"><label for="major">Field of Study</label><input id="major"></div>
    <div class="field"><label for="gpa">Overall Result (GPA)</label><input id="gpa"></div>
    <div class="field"><label>From</label><input id="from" placeholder="YYYY"></div>
    <div class="field"><label>To (Actual or Expected)</label><input id="to" placeholder="YYYY"></div>
    </div><button id="add" onclick="window.adds=(window.adds||0)+1">Add</button></section>`);
  const facts = { education: [{ school: 'Example Institute', degree: 'Bachelor of Technology', field: 'Computer Science & Engineering', graduation_year: 2027, verified: true, evidence: 'July 2023 - May 2027 Bachelor of Technology (CGPA: 8.67 / 10)' }] };
  await page.evaluate(() => {
    const el = document.getElementById('degree'), list = document.getElementById('degrees');
    el.onclick = () => { list.hidden = !list.hidden; el.setAttribute('aria-expanded', String(!list.hidden)); };
    list.querySelectorAll('li').forEach(node => node.onclick = () => { el.textContent = node.textContent; list.hidden = true; el.setAttribute('aria-expanded', 'false'); });
  });
  const questions = await page.evaluate(async () => {
    await forms.resolveVisibleQuestions();
    return calls.filter(m => m.type === 'resolve_questions').flatMap(m => m.questions);
  });
  const src = fileURLToPath(new URL('../../backend/src', import.meta.url));
  const answers = JSON.parse(execFileSync('python', ['-c', 'import json,sys; from career_agent.applying import resolve_live_questions; x=json.load(sys.stdin); print(json.dumps(resolve_live_questions(x["profile"],x["questions"])))'], {
    input: JSON.stringify({ profile: { facts }, questions }), env: { ...process.env, PYTHONPATH: src }, encoding: 'utf8'
  }));
  assert.equal(answers.length, 6);
  await page.evaluate(async ({ answers, records }) => {
    for (const answer of answers) {
      const question = calls.filter(m => m.type === 'resolve_questions').flatMap(m => m.questions).find(q => q.id === answer.id);
      const ctx = question.context, date = ctx?.date_field ? `${ctx.date_field}:${ctx.date_part}:` : '';
      profileAnswers[`${ctx.section}:${ctx.index}:${date}${question.label}`] = answer.value;
    }
    for (let i=0;i<4;i++) { await forms.expandRecords({ profile_records: records }); await forms.fill({ answers: { University: 'WRONG GENERIC SCHOOL' } }); await forms.resolveVisibleQuestions(); }
  }, { answers, records: facts });
  assert.equal(await page.inputValue('#school'), 'Example Institute');
  assert.equal(await page.textContent('#degree'), "Bachelor's Degree");
  assert.equal(await page.inputValue('#from'), '2023');
  assert.equal(await page.inputValue('#to'), '2027');
  assert.equal(await page.inputValue('#gpa'), '8.67');
  assert.equal(await page.evaluate(() => window.adds || 0), 0);
  await page.close();
});

test('unknown repeated wrappers count existing schools and failed Add detection cannot multiply rows on retries', async () => {
  const page = await pageFor(`<section><h2>Education</h2><div><label for="school">School or University*</label><input id="school"></div>
    <button onclick="window.adds=(window.adds||0)+1">Add</button></section>`);
  await page.evaluate(async () => { for(let i=0;i<3;i++) await forms.expandRecords({ profile_records: { education: [{school:'A'}] } }); });
  assert.equal(await page.evaluate(() => window.adds || 0), 0);
  await page.evaluate(async () => { for(let i=0;i<3;i++) await forms.expandRecords({ profile_records: { education: [{school:'A'},{school:'B'}] } }); });
  assert.equal(await page.evaluate(() => window.adds || 0), 1);
  await page.close();
});

test('search-backed field of study selects a returned suggestion and never treats unmatched search text as a selected value', async () => {
  const page = await pageFor(`<label for="major">Field of Study</label><input id="major" role="combobox" aria-controls="subjects"><ul id="subjects" role="listbox" hidden></ul>`);
  await page.evaluate(() => {
    const input=document.getElementById('major'), menu=document.getElementById('subjects');
    input.oninput=()=>{ menu.innerHTML=''; menu.hidden=true; if(input.value==='Computer Science') setTimeout(()=>{
      menu.innerHTML='<li role="option">Computer Science</li>'; menu.hidden=false;
      menu.firstChild.onclick=()=>{window.selected=input.value;menu.hidden=true;};
    },100); };
  });
  assert.equal(await page.evaluate(()=>forms.setValue(document.getElementById('major'),'Computer Science')),true);
  assert.equal(await page.evaluate(()=>window.selected),'Computer Science');
  assert.equal(await page.evaluate(()=>forms.setValue(document.getElementById('major'),'Unknown subject')),false);
  assert.equal(await page.inputValue('#major'),'');
  await page.close();
});

test('Workday labels are semantic, required, and separated from generated IDs and neighboring questions', async () => {
  const page = await pageFor(`<div data-automation-id="formField-legalNameSection_firstName"><label for="input-8372">Given Name(s)*</label><input id="input-8372" name="opaque-uuid"></div>
    <div data-automation-id="formField-email"><label for="email">Email*</label><input id="email"></div>`);
  assert.deepEqual(await page.evaluate(() => forms.controls().map(forms.labelOf)), ['Given Name(s)', 'Email']);
  assert.deepEqual(await page.evaluate(() => forms.unansweredRequired()), ['Given Name(s)', 'Email']);
  await page.evaluate(() => forms.fill({ answers: { 'Full name': 'Asha Rao', Email: 'asha@example.test' } }));
  assert.equal(await page.inputValue('#email'), 'asha@example.test');
  assert.equal(await page.inputValue('#input-8372'), 'Asha');
  await page.close();
});

test('native select updates the displayed choice, preserves existing input, and does not put phone in device type', async () => {
  const page = await pageFor(`<label for="phone">Phone Number*</label><input id="phone"><label for="device">Phone Device Type*</label><input id="device">
    <label for="email">Email</label><input id="email" value="preferred@example.test"><label for="country">Country*</label><select id="country"><option value="">Select an option</option><option value="IND">India</option></select>`);
  await page.evaluate(() => forms.fill({ answers: { Phone: '+919876543210', Email: 'old@example.test', Country: 'India' } }));
  assert.equal(await page.inputValue('#phone'), '+919876543210');
  assert.equal(await page.inputValue('#device'), '');
  assert.equal(await page.inputValue('#email'), 'preferred@example.test');
  assert.equal(await page.inputValue('#country'), 'IND');
  await page.close();
});

test('Amazon and Workday custom choices wait for delayed menus and use scoped exact options', async () => {
  const page = await pageFor(`<div class="field"><div id="question">Do you have programming language experience? *</div>
    <button id="choice" aria-labelledby="question" aria-haspopup="true" aria-expanded="false" aria-controls="options">Select an option</button><ul id="options" role="listbox" hidden></ul></div>
    <ul role="listbox"><li role="option" onclick="window.wrong=true">Yes</li></ul>`, { answers: { 'Do you have programming language experience?': 'Yes' } });
  await page.evaluate(() => {
    const button = document.getElementById('choice'), menu = document.getElementById('options');
    button.onclick = () => {
      if (button.getAttribute('aria-expanded') === 'true') { menu.hidden = true; button.setAttribute('aria-expanded', 'false'); return; }
      button.setAttribute('aria-expanded', 'true');
      setTimeout(() => { menu.innerHTML = '<li role="option">Yes</li><li role="option">No</li>'; menu.hidden = false;
        menu.querySelectorAll('li').forEach((option) => option.onclick = () => { button.textContent = option.textContent; menu.hidden = true; button.setAttribute('aria-expanded', 'false'); });
      }, 400);
    };
  });
  assert.deepEqual(await page.evaluate(() => forms.unansweredRequired()), ['Do you have programming language experience?']);
  await page.evaluate(() => forms.resolveVisibleQuestions());
  assert.equal(await page.textContent('#choice'), 'Yes');
  assert.equal(await page.evaluate(() => window.wrong || false), false);
  await page.close();
});

test('hidden resume upload receives the actual PDF once', async () => {
  const page = await pageFor('<label for="resume">Resume*</label><input id="resume" type="file" required style="display:none">');
  assert.deepEqual(await page.evaluate(() => forms.unansweredRequired()), ['Resume']);
  await page.evaluate(async () => { await forms.fill({ resume_url: 'https://resume.example.test/file' }); await forms.fill({ resume_url: 'https://resume.example.test/file' }); });
  assert.deepEqual(await page.evaluate(() => [...document.getElementById('resume').files].map((file) => [file.name, file.type])), [['resume.pdf', 'application/pdf']]);
  assert.equal(await page.evaluate(() => calls.filter((call) => call.type === 'resume').length), 1);
  assert.deepEqual(await page.evaluate(() => forms.unansweredRequired()), []);
  await page.close();
});

test('repeated Workday history records resolve by stable field ID and record index', async () => {
  const page = await pageFor(`<section><h3>Work Experience 1</h3><div class="field"><label for="job1">Job Title*</label><input id="job1"></div></section>
    <section><h3>Work Experience 2</h3><div class="field"><label for="job2">Job Title*</label><input id="job2"></div></section>`, { answers: { 'experience:0:Job Title': 'Engineer', 'experience:1:Job Title': 'Intern' } });
  await page.evaluate(() => forms.resolveVisibleQuestions());
  assert.equal(await page.inputValue('#job1'), 'Engineer');
  assert.equal(await page.inputValue('#job2'), 'Intern');
  await page.evaluate(() => forms.rememberLearnedAnswers());
  assert.equal(await page.evaluate(() => calls.filter((call) => call.type === 'save_answers').length), 0);
  await page.close();
});

test('split Workday dates keep start/end and record indices separate; only the explicit current-role checkbox is resolved', async () => {
  const record = (index) => `<section><h3>Work Experience ${index + 1}</h3>
    <div data-automation-id="formField-startDate"><label>From*</label><input id="start-month-${index}" aria-label="Month" data-automation-id="dateSectionMonth"><input id="start-year-${index}" aria-label="Year" data-automation-id="dateSectionYear"></div>
    <div class="field"><label>To*</label><input id="end-month-${index}" aria-label="Month"><input id="end-year-${index}" aria-label="Year"></div>
    <label><input id="current-${index}" type="checkbox">I currently work here</label>
    <label><input id="consent-${index}" type="checkbox">I agree to all statements</label></section>`;
  const page = await pageFor(record(0) + record(1), { answers: {
    'experience:0:start:month:Month': '01', 'experience:0:start:year:Year': '2025',
    'experience:0:I currently work here': 'Yes',
    'experience:1:start:month:Month': '09', 'experience:1:start:year:Year': '2023',
    'experience:1:end:month:Month': '06', 'experience:1:end:year:Year': '2024',
    'experience:1:I currently work here': 'No',
  } });
  await page.evaluate(() => forms.resolveVisibleQuestions());
  assert.deepEqual(await page.evaluate(() => ['start-month-0', 'start-year-0', 'end-month-0', 'end-year-0', 'start-month-1', 'start-year-1', 'end-month-1', 'end-year-1'].map((id) => document.getElementById(id).value)), ['01', '2025', '', '', '09', '2023', '06', '2024']);
  assert.equal(await page.isChecked('#current-0'), true);
  assert.equal(await page.isChecked('#current-1'), false);
  assert.equal(await page.isChecked('#consent-0'), false);
  assert.equal(await page.isChecked('#consent-1'), false);
  const questions = await page.evaluate(() => calls.filter((call) => call.type === 'resolve_questions').flatMap((call) => call.questions));
  assert.ok(questions.every((question) => !question.label.includes('agree')));
  assert.deepEqual(questions.find((question) => question.context.index === 1 && question.context.date_field === 'end' && question.label === 'Year').context, { section: 'experience', index: 1, date_field: 'end', date_part: 'year' });
  await page.close();
});

test('unknown required questions and consents stay blank; radio options use visible labels instead of numeric values', async () => {
  const page = await pageFor(`<fieldset><legend>Have you worked for this employer? *</legend><label><input name="worked" type="radio" value="0">Yes</label><label><input name="worked" type="radio" value="1">No</label></fieldset>
    <label for="certification">Certification ID*</label><input id="certification"><label><input id="consent" type="checkbox" required>I agree to the terms</label>`, { answers: { 'Have you worked for this employer?': 'No' } });
  await page.evaluate(() => forms.resolveVisibleQuestions());
  assert.equal(await page.isChecked('input[value="1"]'), true);
  assert.equal(await page.inputValue('#certification'), '');
  assert.equal(await page.isChecked('#consent'), false);
  assert.ok((await page.evaluate(() => forms.unansweredRequired())).includes('Certification ID'));
  await page.close();
});

test('approved record count expands only the appropriate history section', async () => {
  const page = await pageFor('<section id="work"><h2>Work Experience</h2><button id="addWork">Add</button></section><section id="edu"><h2>Education</h2><button id="addEducation">Add</button></section>');
  await page.evaluate(() => {
    let count = 0;
    document.getElementById('addWork').onclick = () => { const node = document.createElement('div'); node.innerHTML = `<h3>Work Experience ${++count}</h3><label for="work${count}">Job Title*</label><input id="work${count}">`; document.getElementById('work').appendChild(node); };
    document.getElementById('addEducation').onclick = () => { window.wrong = true; };
  });
  await page.evaluate(() => forms.expandRecords({ profile_records: { experience: [{ title: 'Engineer' }, { title: 'Intern' }], education: [] } }));
  assert.equal(await page.locator('#work input').count(), 2);
  assert.equal(await page.evaluate(() => window.wrong || false), false);
  await page.close();
});

test('full flow recovers a delayed next button, fills the second page, and dispatches exactly once', { timeout: 25000 }, async () => {
  const page = await pageFor('<h1>Application</h1><label for="name">First Name*</label><input id="name" required>', { packet: { answers: { 'Full name': 'Asha Rao' } }, answers: { 'Job Title': 'Engineer' } });
  await page.evaluate(() => {
    setTimeout(() => { const next = document.createElement('button'); next.textContent = 'Save & Continue';
      next.onclick = () => { document.body.innerHTML = '<h1>Experience</h1><label for="title">Job Title*</label><input id="title" required><button id="submit">Submit Application</button>';
        document.getElementById('submit').onclick = () => { window.submitCount = (window.submitCount || 0) + 1; document.body.innerHTML = '<h1>Thank you for applying</h1>'; };
      }; document.body.appendChild(next);
    }, 1400);
    forms.run();
  });
  await page.waitForFunction(() => calls.some((call) => call.type === 'complete' && call.body.outcome === 'submitted'), { timeout: 20000 });
  assert.equal(await page.evaluate(() => calls.filter((call) => call.type === 'dispatch').length), 1);
  assert.equal(await page.evaluate(() => window.submitCount), 1);
  await page.close();
});

test('reload after dispatch only reconciles confirmation and never fills or submits again', async () => {
  const page = await pageFor('<h1>Application received</h1><button id="submit">Submit</button>', { packet: { dispatched_at: '2026-09-19T12:00:00Z', action_state: 'Submitting' } });
  await page.evaluate(() => forms.run());
  assert.equal(await page.evaluate(() => calls.filter((call) => ['start', 'dispatch', 'resolve_questions'].includes(call.type)).length), 0);
  assert.equal(await page.evaluate(() => calls.find((call) => call.type === 'complete')?.body.outcome), 'submitted');
  await page.close();
});

test('required-question wait rechecks saved Profile answers without employer DOM interaction before submitting', { timeout: 20000 }, async () => {
  const page = await pageFor('<h1>Screening</h1><label for="certificate">Certification ID*</label><input id="certificate" required><button id="submit">Submit Application</button>');
  await page.evaluate(() => {
    document.getElementById('submit').onclick = () => { window.sentCertificate = document.getElementById('certificate').value; document.body.innerHTML = '<h1>Application received</h1>'; };
    forms.run();
  });
  await page.waitForFunction(() => calls.some((call) => call.type === 'resolve_questions'));
  assert.equal(await page.evaluate(() => calls.filter((call) => call.type === 'dispatch').length), 0);
  // This represents saving the answer through Profile. No form field, text,
  // route, or other DOM state changes before the companion's periodic retry.
  await page.evaluate(() => { window.profileAnswers['Certification ID'] = 'CERT-verified-123'; });
  await page.waitForFunction(() => calls.some((call) => call.type === 'complete' && call.body.outcome === 'submitted'), { timeout: 16000 });
  assert.equal(await page.evaluate(() => window.sentCertificate), 'CERT-verified-123');
  assert.equal(await page.evaluate(() => calls.filter((call) => call.type === 'dispatch').length), 1);
  assert.ok(await page.evaluate(() => calls.filter((call) => call.type === 'resolve_questions').length >= 2));
  await page.close();
});

test('Settings pairing requires a real user click and survives an asynchronous connection response', async () => {
  const page = await browser.newPage();
  await page.route('https://career.example.test/app/settings', (route) => route.fulfill({ contentType: 'text/html', body: '<button id="connect">Connect browser</button>' }));
  await page.addInitScript(() => {
    window.calls = []; window.acks = [];
    window.chrome = { runtime: { sendMessage(message, callback) { calls.push(message); callback({ ok: true }); } } };
    window.addEventListener('message', (event) => { if (event.data.type === 'CAREER_AGENT_BROWSER_PAIRED') acks.push(event.data); });
  });
  await page.addInitScript({ content: exported });
  await page.goto('https://career.example.test/app/settings');
  const protocol = await page.context().newCDPSession(page);
  await protocol.send('Runtime.evaluate', { expression: "window.postMessage({ type: 'CAREER_AGENT_PAIR_BROWSER', token: 'runner_12345678901234567890', api: location.origin, requestId: 'without-click' }, location.origin)", userGesture: false });
  await page.waitForFunction(() => acks.length === 1);
  assert.equal(await page.evaluate(() => acks[0].ok), false);
  assert.equal(await page.evaluate(() => calls.length), 0);
  await page.evaluate(() => {
    document.getElementById('connect').onclick = async () => {
      await new Promise((resolve) => setTimeout(resolve, 250));
      window.postMessage({ type: 'CAREER_AGENT_PAIR_BROWSER', token: 'runner_12345678901234567890', api: location.origin, requestId: 'clicked', expires_at: Math.floor(Date.now() / 1000) + 604800 }, location.origin);
    };
  });
  await page.click('#connect');
  await page.waitForFunction(() => acks.length === 2);
  assert.equal(await page.evaluate(() => acks[1].ok), true);
  assert.equal(await page.evaluate(() => calls[0].type), 'pair_runner');
  await page.close();
});
