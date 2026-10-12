'use strict';
// ============================================================================
// strangled.journey.js — increment 7 (Decompose, level 3): AssetManagement, Part, WarehouseManagement and Tool are
// DELETED from the FSM monolith; the monolith reads them from the Assets & Parts slice and writes to it over REST.
// ----------------------------------------------------------------------------
//   SLICE_URL=http://127.0.0.1:8480 MONO_URL=http://127.0.0.1:8580 \
//   SLICE_MPR=<lab>/web-assets/AssetsApp/AssetsApp.mpr MONO_MPR=<lab>/web-assets/mono/fsm.mpr \
//   JOURNEY_USER=journey_fnadm JOURNEY_PW=... MONO_API_USER=assets_slice MONO_API_PW=... \
//   SLICE_API_USER=fsm_monolith SLICE_API_PW=... node strangled.journey.js
//
// Crosses the two running apps both ways, every data effect checked in the database that owns it:
//   1. slice UI: a FunctionalAdministrator creates an asset (preferred technician from the monolith's CoreAPI),
//      a part, a warehouse and an inventory of that part (amount 10) — rows in the SLICE database;
//   2. monolith server flows, invoked headlessly (POST rest/core/v1/nativesync, .../nativesync/reference): the
//      native-sync feed reads the new asset, part, warehouse and inventory from the slice's OData AssetsAPIv2 and
//      writes the monolith's native copies (NativeAsset, NativePart, NativeWarehouse, NativeInventory) — rows in the
//      MONOLITH database. Before the
//      cut these were pushed from the monolith's own Asset/Part commit flows; those tables no longer exist;
//   3. the monolith's published read model is consistent with the slice: odata/core/v1 has no MonoAsset set any
//      more and the native copy carries the slice's values (CustomerName key copy, part name);
//   4. slice UI -> monolith REST -> monolith DB -> slice UI: opening times on the asset create a roster in the
//      MONOLITH, which now references the slice's asset (external) and carries AssetSystemID; the slice reads it
//      back over OData filtered by that key;
//   5. monolith -> slice write at the service boundary: the REST action the monolith's offline used-part flow and
//      its "Add used part" page call (POST rest/assets/v2/usedparts, monolith machine account) creates a used part
//      in the SLICE database; delete reverses it.
// Idempotent: every id carries the run timestamp; no step relies on an empty grid.
// Shape follows project-tests/e2e/journey-runner.js: landing guard per step, `mxcli oql` on the owning database,
// a ledger pointer per step. Trace rung NOT RUN (no OTel exporter). Exit: 0 pass · 1 finding · 2 instrument fault.
// Credentials come from the environment only.
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
const SLICE_MPR = process.env.SLICE_MPR, MONO_MPR = process.env.MONO_MPR;
const MONO_API = [process.env.MONO_API_USER, process.env.MONO_API_PW];
const SLICE_API = [process.env.SLICE_API_USER, process.env.SLICE_API_PW];
if (!PW || !SLICE_MPR || !MONO_MPR || !MONO_API[1] || !SLICE_API[1]) { console.error('INSTRUMENT FAULT: credentials / MPR paths not set'); process.exit(2); }
const ts = new Date().toISOString().replace(/\D/g, '').slice(2, 14);
const ASSET_ID = `AS-${ts}`, ASSET_NAME = `Strangled asset ${ts}`, PART_ID = `PS-${ts}`, PART_NAME = `Strangled part ${ts}`, WH_ID = `WS-${ts}`;
const TECH = 'Journey Technician';
const results = []; const timings = []; let finding = false, fault = false;
const A = (step, name, ok, detail = '') => {
  results.push({ step, name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  [${step}] ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) finding = true;
};
// mxcli oql --json returns numbers as strings ("10"): compare with Number()
const oql = (mpr, sql) => {
  const out = execFileSync(MXCLI, ['oql', '-p', mpr, '--json', sql], { encoding: 'utf8', timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'] });
  return JSON.parse(out.slice(out.search(/[[{]/)));
};
const http = async (method, url, [u, p]) => {
  const r = await fetch(url, { method, headers: { Authorization: 'Basic ' + Buffer.from(`${u}:${p}`).toString('base64') } });
  return { status: r.status, body: await r.text() };
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
const lap = (label, t) => timings.push(`${label} ${((Date.now() - t) / 1000).toFixed(1)} s`);

(async () => {
  const browser = await chromium.launch().catch((e) => { console.error('INSTRUMENT FAULT: ' + e.message); process.exit(2); });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const t0 = Date.now();
  let SYS, PSYS, INV;
  try {
    // ---- step 1: slice UI — asset and part -----------------------------------------------------------------
    let t = Date.now();
    const s1 = 'slice: asset and part created in the slice';
    if (!(await login(page))) { if (!fault) A(s1, `logged in to the slice as ${USER}`, false); throw new Error('stop'); }
    await page.waitForTimeout(1500);
    await page.goto(SLICE + '/p/asset', { waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Assets');
    await shot(page, '00-slice-assets.jpg');
    // the grid's sticky column header overlaps the header button once the grid holds enough rows (the increment 5
    // journey's non-idempotency, capture inc5-rerun): dispatch the click on the resolved, visible button (a forced click lands on the header)
    await page.getByRole('button', { name: 'New Asset' }).filter({ visible: true }).first().dispatchEvent('click');
    if (!(await titleIs(page, 'New asset'))) { A(s1, 'landed on New asset', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Asset ID *').fill(ASSET_ID);
    await page.getByLabel('Name *').fill(ASSET_NAME);
    await page.getByLabel('Address *').fill('Strangler lane 7');
    await page.getByLabel('City *').fill('Den Haag');
    const picked = await pickCombo(page, 'Preferred technician', TECH);
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForFunction(() => !document.title.endsWith('New asset'), null, { timeout: 15000 }).catch(() => {});
    const a = oql(SLICE_MPR, `SELECT AssetID, SystemID, PreferredTechnicianID FROM AssetManagement.Asset WHERE AssetID = '${ASSET_ID}'`);
    A(s1, `asset ${ASSET_ID} in the SLICE database, preferred technician picked from the monolith (key copy PreferredTechnicianID set before commit)`,
      picked && a.length === 1 && !!a[0].SystemID && a[0].PreferredTechnicianID != null, JSON.stringify(a));
    if (a.length !== 1) throw new Error('stop');
    SYS = a[0].SystemID;
    await page.goto(SLICE + '/', { waitUntil: 'domcontentloaded' });
    await page.getByText('Parts', { exact: true }).first().click();
    await titleIs(page, 'Parts');
    await page.getByRole('button', { name: 'New Part' }).filter({ visible: true }).first().dispatchEvent('click');
    if (!(await titleIs(page, 'New part'))) { A(s1, 'landed on New part', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Part ID *').fill(PART_ID);
    await page.getByLabel('Name *').fill(PART_NAME);
    await page.getByLabel('Vendor').fill('ACME');
    await page.getByLabel('Price *').fill('7.25');
    const uom = oql(SLICE_MPR, 'SELECT UnitName FROM Part.UnitOfMeasure ORDER BY UnitName ASC LIMIT 1');   // any existing unit
    if (uom.length === 1) {
      const combo = page.locator('input[id*="referenceSelector1"]').first();
      await combo.click(); await combo.fill(uom[0].UnitName);
      await page.locator('[role=option]', { hasText: uom[0].UnitName }).first().click();
    }
    await shot(page, '01-slice-new-part.jpg');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForFunction(() => !document.title.endsWith('New part'), null, { timeout: 15000 }).catch(() => {});
    const p = oql(SLICE_MPR, `SELECT PartID, SystemID, Name FROM Part.Part WHERE PartID = '${PART_ID}'`);
    A(s1, `part ${PART_ID} in the SLICE database`, p.length === 1 && !!p[0].SystemID, JSON.stringify(p));
    if (p.length !== 1) throw new Error('stop');
    PSYS = p[0].SystemID;
    // warehouse + inventory of the new part (stock the monolith books against in step 5)
    await page.goto(SLICE + '/p/warehouse', { waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Warehouses');
    await page.getByRole('button', { name: 'New Warehouse' }).filter({ visible: true }).first().dispatchEvent('click');
    if (!(await titleIs(page, 'New warehouse'))) { A(s1, 'landed on New warehouse', false, await page.title()); throw new Error('stop'); }
    await page.getByLabel('Warehouse ID *').fill(WH_ID);
    await page.getByLabel('Description *').fill(`Strangled warehouse ${ts}`);
    await page.getByRole('button', { name: 'Save' }).click();
    await titleIs(page, 'Warehouses');
    const wrow = page.locator('.widget-datagrid [role=row], .mx-datagrid tr', { hasText: WH_ID }).first();
    await wrow.waitFor({ state: 'visible', timeout: 20000 });
    await wrow.getByRole('button', { name: 'Open' }).click({ force: true });
    if (!(await titleIs(page, 'Warehouse details'))) { A(s1, 'landed on Warehouse details', false, await page.title()); throw new Error('stop'); }
    await page.getByRole('tab', { name: 'Inventory' }).click();
    await page.getByRole('button', { name: 'New Inventory' }).filter({ visible: true }).first().dispatchEvent('click');
    if (!(await page.getByLabel('Amount *').waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false))) { A(s1, 'inventory form opened', false, await page.title()); throw new Error('stop'); }
    const pc = page.locator('input[id*="referenceSelector2"]').first();
    await pc.click(); await pc.fill(PART_NAME);
    await page.locator('[role=option]', { hasText: PART_NAME }).first().click();
    await page.getByLabel('Amount *').fill('10');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForFunction(() => !document.title.endsWith('New inventory'), null, { timeout: 15000 }).catch(() => {});
    const iv = oql(SLICE_MPR, `SELECT I.SystemID, I.InventoryID, I.Amount FROM WarehouseManagement.Inventory AS I JOIN I/WarehouseManagement.Inventory_Part/Part.Part AS P WHERE P.PartID = '${PART_ID}'`);
    A(s1, `inventory of ${PART_ID} (amount 10) in warehouse ${WH_ID}, SLICE database`, iv.length === 1 && Number(iv[0].Amount) === 10, JSON.stringify(iv));
    if (iv.length !== 1) throw new Error('stop');
    INV = iv[0];
    lap('step 1 (slice UI, asset + part + warehouse inventory)', t);

    // ---- step 2: monolith native-sync feed reads the slice (headless server flow) ---------------------------
    t = Date.now();
    const s2 = 'monolith server flow: native copies fed from the slice';
    const ns = await http('POST', `${MONO}/rest/core/v1/nativesync?AssetSystemID=${encodeURIComponent(SYS)}&PartSystemID=${encodeURIComponent(PSYS)}`, MONO_API);
    A(s2, 'POST rest/core/v1/nativesync answers', ns.status === 200 && /assets 1, parts 1/.test(ns.body), `HTTP ${ns.status} ${ns.body}`);
    const na = oql(MONO_MPR, `SELECT AssetID, Description, SystemID FROM NativeMobileAsset.NativeAsset WHERE SystemID = '${SYS}'`);
    A(s2, 'native asset copy written in the MONOLITH database from the slice OData (AssetsClient.Asset -> Synchronization.AssetList_UpdateNativeAssets)',
      na.length === 1 && na[0].AssetID === ASSET_ID && na[0].Description === ASSET_NAME, JSON.stringify(na) + ' — ledger: in Synchronization.* -> resolved:rebind + pull feed');
    const np = oql(MONO_MPR, `SELECT Name, SystemID FROM NativeMobilePart.NativePart WHERE SystemID = '${PSYS}'`);
    A(s2, 'native part copy written in the MONOLITH database from the slice OData', np.length === 1 && np[0].Name === PART_NAME, JSON.stringify(np));
    const nr = await http('POST', `${MONO}/rest/core/v1/nativesync/reference`, MONO_API);
    A(s2, 'POST rest/core/v1/nativesync/reference answers (units, warehouses, inventories, BOM)', nr.status === 200, `HTTP ${nr.status} ${nr.body}`);
    const ni = oql(MONO_MPR, `SELECT I.Amount, P.SystemID AS PartSystemID, W.WarehouseID FROM NativeMobileWarehouse.NativeInventory AS I ` +
      `JOIN I/NativeMobileWarehouse.NativeInventory_NativePart/NativeMobilePart.NativePart AS P ` +
      `JOIN I/NativeMobileWarehouse.NativeInventory_NativeWarehouse/NativeMobileWarehouse.NativeWarehouse AS W WHERE I.SystemID = '${INV.SystemID}'`);
    A(s2, 'native inventory copy in the MONOLITH database, linked to the native part and warehouse (navigations over the slice OData)',
      ni.length === 1 && Number(ni[0].Amount) === 10 && ni[0].PartSystemID === PSYS && ni[0].WarehouseID === WH_ID, JSON.stringify(ni));
    lap('step 2 (monolith native-sync pull)', t);

    // ---- step 3: the monolith keeps no asset table and no mirror -------------------------------------------
    t = Date.now();
    const s3 = 'monolith: no local asset tables';
    const mono = await http('GET', `${MONO}/odata/core/v1/MonoAsset?$top=1`, MONO_API);
    A(s3, 'the monolith no longer publishes an asset mirror (odata/core/v1/MonoAsset)', mono.status === 404, `HTTP ${mono.status}`);
    let gone = false;
    try { oql(MONO_MPR, 'SELECT COUNT(*) AS n FROM AssetManagement.Asset'); } catch (e) { gone = true; }
    A(s3, 'OQL on AssetManagement.Asset fails in the monolith (module deleted)', gone);
    lap('step 3 (monolith has no asset tables)', t);

    // ---- step 4: slice UI -> monolith REST roster -> monolith DB -> slice UI over OData ---------------------
    t = Date.now();
    const s4 = 'slice -> monolith -> slice: roster on the slice asset';
    await page.goto(SLICE + '/p/asset', { waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Assets');
    const arow = page.locator('.widget-datagrid [role=row]', { hasText: ASSET_ID }).first();
    await arow.waitFor({ state: 'visible', timeout: 20000 });
    await arow.getByRole('button', { name: 'Open' }).click({ force: true });
    if (!(await titleIs(page, 'Asset details'))) { A(s4, 'landed on Asset details', false, await page.title()); throw new Error('stop'); }
    await page.getByRole('tab', { name: 'Opening times' }).click();
    await page.locator('.mx-name-grid3').waitFor({ state: 'visible', timeout: 15000 });
    const before = await rosterRows(page).count();
    await page.locator('.mx-name-grid3').getByRole('button', { name: 'New' }).click();
    const popup = page.locator('.mx-name-dvDraft');
    if (!(await popup.waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false))) { A(s4, 'popup New opening times opened', false); throw new Error('stop'); }
    await page.locator('.mx-name-btnSaveDraft').click();
    await popup.waitFor({ state: 'hidden', timeout: 20000 }).catch(() => {});
    const r = oql(MONO_MPR, `SELECT PublicID, AssetSystemID FROM RosterManagement.Roster WHERE AssetSystemID = '${SYS}'`);
    A(s4, 'roster in the MONOLITH database on the slice asset (external entity), key copy AssetSystemID set before commit', r.length === 1, JSON.stringify(r));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await titleIs(page, 'Asset details');
    await page.getByRole('tab', { name: 'Opening times' }).click();
    await page.locator('.mx-name-grid3').waitFor({ state: 'visible', timeout: 15000 });
    const appeared = await page.waitForFunction((n) => document.querySelectorAll('.mx-name-grid3 [role=row] [role=gridcell]').length > n, 0, { timeout: 20000 })
      .then(() => true).catch(() => false);
    const after = await rosterRows(page).count();
    await shot(page, '02-slice-roster-from-strangled-monolith.jpg');
    A(s4, 'the slice reads it back over OData by the published key copy (Roster.AssetSystemID)', appeared && after === before + 1, `rows ${before} -> ${after}`);
    await rosterRows(page).first().getByRole('button', { name: 'Delete' }).click();
    await page.waitForTimeout(1500);
    const r2 = oql(MONO_MPR, `SELECT PublicID FROM RosterManagement.Roster WHERE AssetSystemID = '${SYS}'`);
    A(s4, 'deleted from the slice grid -> gone from the MONOLITH database', r2.length === 0, JSON.stringify(r2));
    lap('step 4 (roster round trip)', t);

    // ---- step 5: monolith -> slice write (the REST action behind the monolith's used-part flows) ------------
    t = Date.now();
    const s5 = 'monolith -> slice: used part over REST';
    const inv = [INV];
    const UP = `UJ-${ts}`;
    const up = await http('POST', `${SLICE}/rest/assets/v2/usedparts?SystemID=${UP}&InventorySystemID=${encodeURIComponent(inv[0].SystemID)}&AppointmentPublicID=0&Quantity=2&IsFromWarehouse=true`, SLICE_API);
    const u = oql(SLICE_MPR, `SELECT U.Quantity, U.IsFromWarehouse, I.Amount FROM Part.UsedPart AS U JOIN U/Part.UsedPart_Inventory/WarehouseManagement.Inventory AS I WHERE U.SystemID = '${UP}'`);
    A(s5, `used part ${UP} created in the SLICE database by the monolith machine account, stock booked (Amount ${inv[0].Amount} -> ${Number(inv[0].Amount) - 2})`,
      up.status === 200 && u.length === 1 && Number(u[0].Amount) === Number(inv[0].Amount) - 2, `HTTP ${up.status} ${up.body} ${JSON.stringify(u)} — ledger: in Synchronization.OfflineUsedPartAction_Process -> resolved:rest`);
    const del = await http('POST', `${SLICE}/rest/assets/v2/usedparts/delete?SystemID=${UP}`, SLICE_API);
    const i2 = oql(SLICE_MPR, `SELECT Amount FROM WarehouseManagement.Inventory WHERE SystemID = '${inv[0].SystemID}'`);
    const u2 = oql(SLICE_MPR, `SELECT SystemID FROM Part.UsedPart WHERE SystemID = '${UP}'`);
    A(s5, 'delete through the slice\'s own UsedPart_Delete restores the stock (P7)', del.status === 200 && u2.length === 0 && Number(i2[0].Amount) === Number(inv[0].Amount),
      `HTTP ${del.status} ${del.body} amount ${i2[0].Amount}`);
    const anon = await http('POST', `${SLICE}/rest/assets/v2/usedparts?SystemID=x`, ['nobody', 'wrong']);
    A(s5, 'the REST action refuses wrong credentials', anon.status === 401, `HTTP ${anon.status}`);
    lap('step 5 (used part REST)', t);
  } catch (e) {
    if (e.message !== 'stop') { console.error('INSTRUMENT FAULT: ' + e.message.split('\n').slice(0,12).join(' | ') + ' @' + (e.stack.match(/journey.js:(\d+)/) || [])[1]); fault = true; }
  } finally {
    await browser.close();
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const passed = results.filter((x) => x.ok).length;
  console.log(`\nstrangled journey: ${passed}/${results.length} assertions passed in ${secs} s` +
    (fault ? ' — INVALID RUN (instrument fault)' : finding ? ' — FINDING' : ' — PASS') +
    `\n  ids: asset=${ASSET_ID} part=${PART_ID}\n  timings: ${timings.join('; ')}\n  trace rung: NOT RUN (no OTel exporter on either app)`);
  process.exit(fault ? 2 : finding ? 1 : 0);
})();
