'use strict';
// ============================================================================
// core-seam.journey.js — increment 6 (Decompose), the slice reading from and writing to the monolith
// ----------------------------------------------------------------------------
//   SLICE_URL=http://127.0.0.1:8480 MONO_URL=http://127.0.0.1:8580 \
//   SLICE_MPR=<lab>/web-assets/AssetsApp/AssetsApp.mpr MONO_MPR=<lab>/web-assets/mono/fsm.mpr \
//   JOURNEY_USER=journey_fnadm JOURNEY_PW=... node core-seam.journey.js
//
// The seam in the NEW direction (increment 5 crossed it monolith -> slice): a FunctionalAdministrator in the
// Assets app (Mendix 11.13, the slice)
//   1. creates an asset and picks its preferred technician from a combo box whose data source is the external
//      entity Technician.Technician — served by the FSM monolith's (10.24 copy) published OData service CoreAPI;
//   2. adds opening times on the asset tab — the slice calls the monolith's published REST action
//      POST rest/core/v1/rosters; the roster row lands in the MONOLITH database, hung off the monolith's asset
//      mirror with the slice asset's SystemID;
//   3. sees that roster in the asset tab grid, read back over OData (external entity TicketManagement.Roster,
//      filtered over the navigation Roster_Asset/MonoAsset/SystemID);
//   4. deletes it from the grid — REST POST rest/core/v1/rosters/delete — and it is gone from the monolith.
//
// Shape follows project-tests/e2e/journey-runner.js: landing guard per step, data effects by `mxcli oql` on the
// database that OWNS the row (slice for the asset, monolith for the roster), a ledger pointer per step.
// The trace rung (otel) is NOT RUN: neither app has an OTel exporter configured.
// Exit: 0 pass · 1 finding · 2 instrument fault. Credentials come from the environment only.
// ============================================================================
const { execFileSync } = require('child_process');
const path = require('path');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { console.error('INSTRUMENT FAULT: playwright missing'); process.exit(2); }
const SLICE = process.env.SLICE_URL || 'http://127.0.0.1:8480';
const USER = process.env.JOURNEY_USER || 'journey_fnadm';
const PW = process.env.JOURNEY_PW;
const MXCLI = process.env.MXCLI || 'mxcli';
const OUT = process.env.OUT_DIR || __dirname;
const SLICE_MPR = process.env.SLICE_MPR, MONO_MPR = process.env.MONO_MPR;
if (!PW || !SLICE_MPR || !MONO_MPR) { console.error('INSTRUMENT FAULT: JOURNEY_PW / SLICE_MPR / MONO_MPR not set'); process.exit(2); }
const ts = new Date().toISOString().replace(/\D/g, '').slice(2, 14);
const ASSET_ID = `AJ-${ts}`, ASSET_NAME = `Journey asset ${ts}`, TECH = 'Journey Technician';
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
const titleIs = (page, t) => page.waitForFunction((x) => document.title.endsWith(x), t, { timeout: 15000 }).then(() => true).catch(() => false);
async function login(page) {
  await page.goto(SLICE + '/', { waitUntil: 'domcontentloaded' });
  const pw = page.locator('#passwordInput');
  if (!(await pw.waitFor({ state: 'visible', timeout: 25000 }).then(() => true).catch(() => false))) {
    console.error('INSTRUMENT FAULT: slice login form did not render'); fault = true; return false;
  }
  await page.fill('#usernameInput', USER); await pw.fill(PW); await page.click('#loginButton');
  return page.waitForSelector('.mx-page', { timeout: 30000 }).then(() => true).catch(() => false);
}
async function pickCombo(page, label, text) {
  const input = page.getByLabel(label, { exact: true }).first();
  await input.click(); await input.fill(text);
  const opt = page.locator('[role=option]', { hasText: text }).first();
  const ok = await opt.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false);
  if (ok) await opt.click();
  return ok;
}
const rosterRows = (page) => page.locator('.mx-name-grid3 [role=row]').filter({ has: page.locator('[role=gridcell]') });

(async () => {
  const browser = await chromium.launch().catch((e) => { console.error('INSTRUMENT FAULT: ' + e.message); process.exit(2); });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const t0 = Date.now();
  try {
    // ---- step 1: login --------------------------------------------------------------------
    const s1 = 'slice login';
    if (!(await login(page))) { if (!fault) A(s1, `logged in to the slice as ${USER}`, false); throw new Error('stop'); }
    A(s1, `logged in to the slice as ${USER}`, true);

    // ---- step 2: new asset, preferred technician picked from the monolith --------------------
    const s2 = 'slice: technician served by the monolith';
    await page.getByText('Assets', { exact: true }).first().click();
    await titleIs(page, 'Assets');
    await page.getByRole('button', { name: 'New Asset' }).click();
    if (!(await titleIs(page, 'New asset'))) { A(s2, 'landed on New asset', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Asset ID *').fill(ASSET_ID);
    await page.getByLabel('Name *').fill(ASSET_NAME);
    await page.getByLabel('Address *').fill('Seam street 6');
    await page.getByLabel('City *').fill('Den Haag');
    const picked = await pickCombo(page, 'Preferred technician', TECH);
    await shot(page, '01-slice-technician-from-monolith.jpg');
    A(s2, `combo box lists "${TECH}" from external entity Technician.Technician (monolith OData CoreAPI)`, picked,
      'ledger: out Technician.Technician -> resolved:odata (slice-core-external.mdl)');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForFunction(() => !document.title.endsWith('New asset'), null, { timeout: 15000 }).catch(() => {});
    const a = oql(SLICE_MPR, `SELECT AssetID, SystemID FROM AssetManagement.Asset WHERE AssetID = '${ASSET_ID}'`);
    A(s2, `asset ${ASSET_ID} committed in the slice database`, a.length === 1 && !!a[0].SystemID, JSON.stringify(a));
    if (a.length !== 1) throw new Error('stop');
    const SYS = a[0].SystemID;

    // ---- step 3: opening times created from the asset tab -> monolith REST -------------------
    const s3 = 'slice -> monolith: roster created over REST';
    await page.goto(SLICE + '/p/asset', { waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Assets');
    const arow = page.locator('.widget-datagrid [role=row]', { hasText: ASSET_ID }).first();
    await arow.waitFor({ state: 'visible', timeout: 20000 });
    await arow.getByRole('button', { name: 'Open' }).click();
    if (!(await titleIs(page, 'Asset details'))) { A(s3, 'landed on Asset details', false, await page.title()); throw new Error('stop'); }
    const techShown = await page.getByText(TECH).first().waitFor({ state: 'visible', timeout: 10000 }).then(() => true).catch(() => false);
    A(s3, `asset details show preferred technician "${TECH}" (local -> external association, slice-owned)`, techShown);
    await page.getByRole('tab', { name: 'Opening times' }).click();
    await page.locator('.mx-name-grid3').waitFor({ state: 'visible', timeout: 15000 });
    const before = await rosterRows(page).count();
    await page.locator('.mx-name-grid3').getByRole('button', { name: 'New' }).click();
    const popup = page.locator('.mx-name-dvDraft');
    if (!(await popup.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false))) { A(s3, 'popup New opening times opened', false); throw new Error('stop'); }
    await page.locator('.mx-name-btnSaveDraft').click();
    await popup.waitFor({ state: 'hidden', timeout: 20000 }).catch(() => {});
    const r = oql(MONO_MPR, `SELECT R.PublicID, R.StartDate, M.SystemID, M.AssetID FROM RosterManagement.Roster AS R ` +
      `JOIN R/RosterManagement.Roster_Asset/AssetManagement.Asset AS M WHERE M.SystemID = '${SYS}'`);
    A(s3, `roster committed in the MONOLITH database on its asset mirror (SystemID = slice asset)`, r.length === 1 && r[0].AssetID === ASSET_ID,
      JSON.stringify(r) + ' — ledger: out RosterManagement.Roster -> resolved:rest (CoreSeam.Roster_CreateRemote)');

    // ---- step 4: the roster is read back over OData in the asset tab -------------------------
    const s4 = 'monolith -> slice: roster read over OData';
    await page.reload({ waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Asset details');
    await page.getByRole('tab', { name: 'Opening times' }).click();
    await page.locator('.mx-name-grid3').waitFor({ state: 'visible', timeout: 15000 });
    const appeared = await page.waitForFunction((n) => document.querySelectorAll('.mx-name-grid3 [role=row] [role=gridcell]').length > n, 0, { timeout: 20000 })
      .then(() => true).catch(() => false);
    const after = await rosterRows(page).count();
    await shot(page, '02-slice-roster-from-monolith.jpg');
    A(s4, `asset tab grid lists the roster from external entity TicketManagement.Roster (Roster_Asset/MonoAsset/SystemID filter)`,
      appeared && after === before + 1, `rows ${before} -> ${after}`);

    // ---- step 5: delete from the grid -> monolith REST ---------------------------------------
    const s5 = 'slice -> monolith: roster deleted over REST';
    await rosterRows(page).first().getByRole('button', { name: 'Delete' }).click();
    await page.waitForTimeout(1500);
    const r2 = oql(MONO_MPR, `SELECT R.PublicID FROM RosterManagement.Roster AS R JOIN R/RosterManagement.Roster_Asset/AssetManagement.Asset AS M WHERE M.SystemID = '${SYS}'`);
    A(s5, 'roster gone from the monolith database (RosterManagement.ACT_Roster_Delete -> POST rosters/delete)', r2.length === 0,
      JSON.stringify(r2) + ' — ledger: check-only RosterManagement.ACT_Roster_Delete -> resolved:rest');

    // ---- step 6: the other external tabs render without a runtime error ----------------------
    const s6 = 'monolith -> slice: tickets and contacts tabs over OData';
    for (const [tab, grid] of [['Tickets', 'grid1'], ['Contacts', 'grid2']]) {
      await page.getByRole('tab', { name: tab }).click();
      const shown = await page.locator(`.mx-name-${grid}`).first().waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false);
      const err = await page.locator('.mx-dialog-error, .alert-danger, [role=alertdialog]').count();
      A(s6, `${tab} tab grid (external entity, filtered over a navigation to MonoAsset) renders with no error dialog`, shown && err === 0,
        `error dialogs: ${err} (monolith holds no tickets/contacts for this asset: an empty grid is the expected content)`);
    }
  } catch (e) {
    if (e.message !== 'stop') { console.error('INSTRUMENT FAULT: ' + e.message.split('\n')[0]); fault = true; }
  } finally {
    await browser.close();
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const passed = results.filter((x) => x.ok).length;
  console.log(`\ncore-seam journey: ${passed}/${results.length} assertions passed in ${secs} s` +
    (fault ? ' — INVALID RUN (instrument fault)' : finding ? ' — FINDING' : ' — PASS') +
    `\n  ids: asset=${ASSET_ID}\n  trace rung: NOT RUN (no OTel exporter on either app)`);
  process.exit(fault ? 2 : finding ? 1 : 0);
})();
