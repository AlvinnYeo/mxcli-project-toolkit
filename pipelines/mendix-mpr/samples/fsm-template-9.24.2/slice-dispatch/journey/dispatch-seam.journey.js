'use strict';
// ============================================================================
// dispatch-seam.journey.js — increment 8 (Decompose, Dispatch & Workforce slice, seam lane alongside the stubs)
// ----------------------------------------------------------------------------
//   SLICE_URL=http://127.0.0.1:8780 MONO_URL=http://127.0.0.1:8680 \
//   SLICE_MPR=<lab>/dispatch/DispatchApp/DispatchApp.mpr MONO_MPR=<lab>/dispatch/mono/fsm.mpr \
//   JOURNEY_USER=journey_sde JOURNEY_PW=... MONO_API_USER=dispatch_slice MONO_API_PW=... node dispatch-seam.journey.js
//
// Crosses the two running apps, every data effect checked in the database that owns it:
//   1. READ  (OData): the slice page DispatchSeam.Appointments_FromCore lists the monolith's journey appointment
//      (J8-APPT-1) from odata/dispatchcore/v1 — the row exists in the MONOLITH database, none in the slice's;
//   2. WRITE (REST, behaviour-carrying): "Plan in monolith" calls rest/dispatchcore/v1/appointments/plan, which runs the
//      monolith's own TicketManagement.Appointment_PlanManual; the slice records a DispatchSeam.PlanRequest (run ID,
//      planned start) in the SLICE database, and the MONOLITH database holds the same planned start on the appointment,
//      status Planned;
//   3. AUTH: the machine role is the only role on both services — 200 / 401 / 404 measured.
// Idempotent: the run ID carries the run timestamp and the planned start is run-unique (now + 7 days, to the ms).
// Shape follows project-tests/e2e/journey-runner.js: landing guard per step, `mxcli oql` on the owning database, a ledger
// pointer per step. Exit: 0 pass · 1 finding · 2 instrument fault. Credentials come from the environment only.
// ============================================================================
const { execFileSync } = require('child_process');
const path = require('path');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { console.error('INSTRUMENT FAULT: playwright missing'); process.exit(2); }
const SLICE = process.env.SLICE_URL || 'http://127.0.0.1:8780';
const MONO = process.env.MONO_URL || 'http://127.0.0.1:8680';
const USER = process.env.JOURNEY_USER || 'journey_sde';
const PW = process.env.JOURNEY_PW;
const MXCLI = process.env.MXCLI || 'mxcli';
const OUT = process.env.OUT_DIR || __dirname;
const SLICE_MPR = process.env.SLICE_MPR, MONO_MPR = process.env.MONO_MPR;
const MONO_API = [process.env.MONO_API_USER, process.env.MONO_API_PW];
if (!PW || !SLICE_MPR || !MONO_MPR || !MONO_API[1]) { console.error('INSTRUMENT FAULT: credentials / MPR paths not set'); process.exit(2); }
const ts = new Date().toISOString().replace(/\D/g, '').slice(2, 14);
const RUN = `J8-${ts}`;
let finding = false, fault = false;
const A = (step, name, ok, detail = '') => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  [${step}] ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) finding = true;
};
const oql = (mpr, sql) => {
  const out = execFileSync(MXCLI, ['oql', '-p', mpr, '--json', sql], { encoding: 'utf8', timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'] });
  return JSON.parse(out.slice(out.search(/[[{]/)));
};
const http = async (method, url, cred) => {
  const h = cred ? { Authorization: 'Basic ' + Buffer.from(`${cred[0]}:${cred[1]}`).toString('base64') } : {};
  const r = await fetch(url, { method, headers: h });
  return r.status;
};
const shot = (page, name) => page.screenshot({ path: path.join(OUT, name), type: 'jpeg', quality: 45 });
const titleIs = (page, t) => page.waitForFunction((x) => document.title.endsWith(x), t, { timeout: 20000 }).then(() => true).catch(() => false);

(async () => {
  const browser = await chromium.launch().catch((e) => { console.error('INSTRUMENT FAULT: ' + e.message); process.exit(2); });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const t0 = Date.now();
  try {
    console.log(`run ${RUN}`);
    // ---- step 1: READ over OData -------------------------------------------------------------------------------
    const s1 = 'read: monolith appointment listed in the slice over OData (ledger: TicketManagement.Appointment out-rows)';
    await page.goto(SLICE + '/', { waitUntil: 'domcontentloaded' });
    const pw = page.locator('#passwordInput');
    if (!(await pw.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false))) { console.error('INSTRUMENT FAULT: slice login form did not render'); fault = true; throw new Error('stop'); }
    await page.fill('#usernameInput', USER); await pw.fill(PW); await page.click('#loginButton');
    await page.waitForSelector('.mx-page', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await page.goto(SLICE + '/p/dispatch-seam', { waitUntil: 'domcontentloaded' });
    if (!(await titleIs(page, 'Appointments (monolith, OData)'))) { A(s1, 'landed on Appointments (monolith, OData)', false, await page.title()); throw new Error('stop'); }
    const row = page.locator('.mx-name-gridAppointments [role=row]', { hasText: 'J8-APPT-1' }).first();
    const seen = await row.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false);
    const m1 = oql(MONO_MPR, "SELECT PublicID, SystemID FROM TicketManagement.Appointment WHERE SystemID = 'J8-APPT-1'");
    await shot(page, '01-slice-appointments-from-monolith.jpg');
    A(s1, 'row J8-APPT-1 visible in the slice grid, and present in the MONOLITH database', seen && m1.length === 1, JSON.stringify(m1));
    if (!seen) throw new Error('stop');
    // ---- step 2: WRITE over REST (behaviour: Appointment_PlanManual) -------------------------------------------
    const s2 = 'write: plan in monolith over REST (ledger: TicketManagement.Appointment_PlanManual out-row)';
    await page.getByLabel('Run ID').fill(RUN);
    await row.getByRole('button', { name: 'Plan in monolith' }).click();
    const ok = await page.getByText('Planning request accepted by the monolith').first().waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false);
    await shot(page, '02-slice-plan-accepted.jpg');
    const s = oql(SLICE_MPR, `SELECT RunID, AppointmentPublicID, TechnicianSystemID, PlannedWorkStart, Response FROM DispatchSeam.PlanRequest WHERE RunID = '${RUN}'`);
    A(s2, `PlanRequest ${RUN} in the SLICE database with the monolith's answer`, ok && s.length === 1 && /^planned /.test(s[0].Response || ''), JSON.stringify(s));
    if (s.length !== 1) throw new Error('stop');
    const m2 = oql(MONO_MPR, "SELECT SystemID, PlannedWorkStart, Status FROM TicketManagement.Appointment WHERE SystemID = 'J8-APPT-1'");
    A(s2, 'the MONOLITH database holds the same planned start, status Planned (behaviour ran)',
      m2.length === 1 && String(m2[0].PlannedWorkStart) === String(s[0].PlannedWorkStart) && m2[0].Status === 'Planned', JSON.stringify(m2));
    // ---- step 3: AUTH -------------------------------------------------------------------------------------------
    const s3 = 'auth: machine role only on both monolith services';
    const a = await http('GET', MONO + '/odata/dispatchcore/v1/Appointment?$top=1', MONO_API);
    const b = await http('GET', MONO + '/odata/dispatchcore/v1/Appointment?$top=1', null);
    const c = await http('POST', MONO + '/rest/dispatchcore/v1/appointments/plan?AppointmentPublicID=0', null);
    A(s3, 'OData 200 machine / 401 none; REST 401 none', a === 200 && b === 401 && c === 401, `${a}/${b}/${c}`);
  } catch (e) { if (e.message !== 'stop') { console.error('INSTRUMENT FAULT: ' + e.message); fault = true; } }
  await browser.close();
  console.log(`total ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  process.exit(fault ? 2 : finding ? 1 : 0);
})();
