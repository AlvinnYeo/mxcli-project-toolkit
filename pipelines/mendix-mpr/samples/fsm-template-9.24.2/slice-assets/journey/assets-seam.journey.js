'use strict';
// ============================================================================
// assets-seam.journey.js — increment 5 (Decompose), one journey across the seam
// ----------------------------------------------------------------------------
//   SLICE_URL=http://127.0.0.1:8480 MONO_URL=http://127.0.0.1:8580 \
//   SLICE_MPR=<lab>/web-assets/AssetsApp/AssetsApp.mpr MONO_MPR=<lab>/web-assets/mono/fsm.mpr \
//   JOURNEY_USER=journey_fnadm JOURNEY_PW=... node assets-seam.journey.js
//
// A FunctionalAdministrator creates a unit of measure and a part in the Assets app
// (Mendix 11.13, the slice), then opens the FSM monolith (Mendix 10.24 copy) and sees
// that part on a monolith page whose data source is the external entity
// AssetsSeam.Parts — read over the slice's published OData service with basic auth.
//
// Shape follows project-tests/e2e/journey-runner.js (the toolkit's journey convention):
//   1. LANDING GUARD  per step — assertions only after we know we arrived;
//   2. ORDER          — steps run in sequence, state carried (the ids made in step 2/3);
//   3. DATA EFFECTS   — OQL on the runtime that owns the row (the slice), and the
//                       association that must be set (Part_UnitOfMeasure) IS set;
//   4. REQUIREMENT    — each step names the cut-ledger edge / seam rule it exercises.
// The trace rung (otel) is NOT RUN: neither app has an OTel exporter configured.
// Exit: 0 pass · 1 finding · 2 instrument fault (no browser / app down / login form absent).
// Credentials come from the environment only; nothing is written to disk but screenshots.
// ============================================================================
const { execFileSync } = require('child_process');
const path = require('path');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { console.error('INSTRUMENT FAULT: playwright missing'); process.exit(2); }

const SLICE = process.env.SLICE_URL || 'http://127.0.0.1:8480';
const MONO = process.env.MONO_URL || 'http://127.0.0.1:8580';
const USER = process.env.JOURNEY_USER || 'journey_fnadm';
const PW = process.env.JOURNEY_PW;
const MXCLI = process.env.MXCLI || 'mxcli';
const OUT = process.env.OUT_DIR || __dirname;
if (!PW) { console.error('INSTRUMENT FAULT: JOURNEY_PW not set'); process.exit(2); }

const ts = new Date().toISOString().replace(/\D/g, '').slice(2, 14);
const UNIT = `Box-${ts}`, PART_ID = `PW-${ts}`, PART_NAME = `Journey part ${ts}`;
const results = []; let finding = false, fault = false;
const A = (step, name, ok, detail = '') => {
  results.push({ step, name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  [${step}] ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) finding = true;
};
const oql = (mpr, sql) => {
  const out = execFileSync(MXCLI, ['oql', '-p', mpr, '--json', sql], { encoding: 'utf8', timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'] });
  return JSON.parse(out.slice(out.search(/[[{]/)));
};
const shot = (page, name) => page.screenshot({ path: path.join(OUT, name), type: 'jpeg', quality: 45 });

async function login(page, base, appName) {
  // Mendix's login.html (slice) and FSM's anonymous login page General.Login_Web (monolith) differ:
  // locate by role of the field, not by the starter's ids.
  await page.context().clearCookies();
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  const pw = page.locator('#passwordInput, input[type=password]').first();
  if (!(await pw.waitFor({ state: 'visible', timeout: 25000 }).then(() => true).catch(() => false))) {
    console.error(`INSTRUMENT FAULT: ${appName} login form did not render`); fault = true; return false;
  }
  await page.locator('#usernameInput, input.form-control[type=text], input[type=text]').first().fill(USER);
  await pw.fill(PW);
  await page.locator('#loginButton, button.mx-name-signInButton2, button[type=submit]').first().click();
  return page.waitForFunction(() => !/login\.html/.test(location.href) && !/Login$/.test(document.title)
      && !document.querySelector('input[type=password]') && !!document.querySelector('.mx-page'),
    null, { timeout: 30000 }).then(() => true).catch(() => false);
}
async function logout(page) {   // xas logout with the CSRF token (helpers.js: GET /logout leaves the session alive)
  return page.evaluate(async () => {
    const s = (window.mx && mx.session) || {};
    const token = s.getCSRFToken ? s.getCSRFToken() : ((s.sessionData && s.sessionData.csrftoken) || '');
    if (!token) return 'no-token';
    const r = await fetch('/xas/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Csrf-Token': token },
      body: JSON.stringify({ action: 'logout', params: {} }) });
    return r.status;
  }).catch(() => 'error');
}
const titleIs = (page, t) => page.waitForFunction((x) => document.title.endsWith(x), t, { timeout: 15000 }).then(() => true).catch(() => false);

(async () => {
  const browser = await chromium.launch().catch((e) => { console.error('INSTRUMENT FAULT: ' + e.message); process.exit(2); });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const t0 = Date.now();
  try {
    // ---- step 1: slice login ------------------------------------------------------------
    const s1 = 'slice login';
    if (!(await login(page, SLICE, 'slice'))) { if (!fault) A(s1, `logged in to the slice as ${USER}`, false); throw new Error('stop'); }
    if (!(await titleIs(page, 'Parts'))) A(s1, 'landed on the slice home page (Parts)', false, await page.title());
    else A(s1, `logged in to the slice as ${USER}; home page is Parts`, true, 'ledger: in Navigation.Responsive -> slice menu (handoff)');

    // ---- step 2: create a unit of measure in the slice ----------------------------------
    const s2 = 'slice: new unit of measure';
    await page.getByText('Units of measure', { exact: true }).first().click();
    await page.getByRole('button', { name: 'New Unit Of Measure' }).click();
    if (!(await titleIs(page, 'Unit of Measure edit'))) { A(s2, 'landed on Unit of Measure edit', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Unit name *').fill(UNIT);
    await page.getByLabel('Abbreviation *').fill('bx');
    await page.getByRole('button', { name: 'Save' }).click();
    await titleIs(page, 'Unit of measure');
    const u = oql(process.env.SLICE_MPR, `SELECT UnitName, SystemID FROM Part.UnitOfMeasure WHERE UnitName = '${UNIT}'`);
    A(s2, `unit ${UNIT} committed in the slice database`, u.length === 1 && !!u[0].SystemID, JSON.stringify(u));

    // ---- step 3: create a part with that unit -------------------------------------------
    const s3 = 'slice: new part';
    await page.getByText('Parts', { exact: true }).first().click();
    await titleIs(page, 'Parts');
    await page.getByRole('button', { name: 'New Part' }).click();
    if (!(await titleIs(page, 'New part'))) { A(s3, 'landed on New part', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Part ID *').fill(PART_ID);
    await page.getByLabel('Name *').fill(PART_NAME);
    await page.getByLabel('Vendor').fill('ACME');
    await page.getByLabel('Price *').fill('12.50');
    const combo = page.locator('input[id*="referenceSelector1"]').first();   // the Combo box input (its label also names the menu)
    await combo.click();
    await combo.fill(UNIT);
    await page.locator('[role=option]', { hasText: UNIT }).first().click();
    await shot(page, '01-slice-new-part.jpg');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForFunction(() => !document.title.endsWith('New part'), null, { timeout: 15000 }).catch(() => {});
    const p = oql(process.env.SLICE_MPR,
      `SELECT P.PartID, P.Name, U.UnitName FROM Part.Part AS P LEFT JOIN P/Part.Part_UnitOfMeasure/Part.UnitOfMeasure AS U WHERE P.PartID = '${PART_ID}'`);
    A(s3, `part ${PART_ID} committed in the slice with Part_UnitOfMeasure = ${UNIT}`, p.length === 1 && p[0].UnitName === UNIT, JSON.stringify(p));
    await logout(page);

    // ---- step 4: the monolith shows it, read over OData ---------------------------------
    const s4 = 'monolith: part visible over OData';
    if (!(await login(page, MONO, 'monolith'))) { if (!fault) A(s4, `logged in to the monolith as ${USER}`, false); throw new Error('stop'); }
    await page.goto(MONO + '/p/parts-from-slice', { waitUntil: 'domcontentloaded' });
    const landed = await page.getByText('Parts (served by the Assets app over OData)').first()
      .waitFor({ state: 'visible', timeout: 20000 }).then(() => true).catch(() => false);
    if (!landed) { A(s4, 'landed on AssetsSeam.Parts_FromSlice', false, await page.title()); throw new Error('stop'); }
    const row = page.locator('.widget-datagrid [role=row]', { hasText: PART_ID });
    const seen = await row.first().waitFor({ state: 'visible', timeout: 20000 }).then(() => true).catch(() => false);
    const rowText = seen ? (await row.first().innerText()).replace(/\s+/g, ' ').trim() : '';
    await shot(page, '02-monolith-part-from-slice.jpg');
    A(s4, `monolith page lists ${PART_ID} from external entity AssetsSeam.Parts`, seen && rowText.includes(PART_NAME) && rowText.includes('ACME'),
      `row: "${rowText}" — ledger: in-edge read of Part.Part rewired to OData (seam-mono-rewire.mdl)`);
    await logout(page);
  } catch (e) {
    if (e.message !== 'stop') { console.error('INSTRUMENT FAULT: ' + e.message.split('\n')[0]); fault = true; }
  } finally {
    await browser.close();
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const passed = results.filter((r) => r.ok).length;
  console.log(`\nassets-seam journey: ${passed}/${results.length} assertions passed in ${secs} s` +
    (fault ? ' — INVALID RUN (instrument fault)' : finding ? ' — FINDING' : ' — PASS') +
    `\n  ids: unit=${UNIT} part=${PART_ID}\n  trace rung: NOT RUN (no OTel exporter on either app)`);
  process.exit(fault ? 2 : finding ? 1 : 0);
})();
