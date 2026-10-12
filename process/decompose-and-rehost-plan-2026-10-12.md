# Plan: monolith decomposition and MPR-to-MDL rehost — two new pipelines

**Status:** 2026-10-12, increment 1 done on both tracks (results in §5); increment 2 next.
**Decisions since the draft:** no Event Broker licence → Business Events is **not** an integration lane,
a crossing edge becomes OData or REST or it blocks. The FSM template reads on Mendix 9.24.2 (MPR v1).
**Decisions already taken in the conversation that produced it:** Mendix version upgrades are
out of scope (apps on Mendix 9 and above only; the upgrade hop itself is the customer's job).
Two tracks remain and run in parallel: **Decompose** (split one app into several) and
**Rehost** (read an existing `.mpr`, regenerate it as MDL into a fresh Mendix 11 app).

---

## 1. What the research established

### Decompose — the platform facts that bound every cut

| Fact | Consequence for a cut |
|---|---|
| Mendix apps cannot share a database; integration is OData (external entities), REST or Business Events | Every edge across the cut becomes an HTTP call. Edge weight is the cost of the cut |
| External entities cannot own associations, cannot aggregate, and every *Send External Object* is its own transaction | An edge carrying an association, an aggregate, or a shared transaction scores as a bad cut |
| No cross-app workflow; no shared user table (OIDC Provider module brokers identity; Mendix SSO deprecated May 2026) | A workflow or a security role that spans the cut is a blocker, not a cost |
| Business Events need a paid Event Broker licence and carry flat payloads | **Not a lane here** (decided 2026-10-12: no licence). Async edges are out of the table |
| Every app is a cloud node; pricing is per app | The number of target apps is a licensing decision before an architecture one |
| ~~Module export to `.mpk` works only for a self-contained module and the same Studio Pro version~~ **Contradicted 2026-10-12 by the MPK probe** (`pipelines/mendix-mpr/export-module-mpk.py`): a headless export from an MPR v1 app works for any module, Mendix's importer takes it with only missing-module errors, and entity/unit IDs survive 9.24 → 11.13. Constraint that does hold: Mendix refuses a 9.x package into 11.x, so a 9 → 11 move hops through `mx convert` to 10.24 first | **Hybrid, MPK as the mover**: each slice module moves by export + `marketplace install --file`; MDL handles the crossing edges (stubs, later OData/REST) and the app-level settings the package drops; MDL regeneration stays for full re-platforms |

Mendix's own position (Lennevi): start monolithic, keep domains in modules, break up when team
size or release cadence demands. Nobody has published a Mendix-specific decomposition order or a
cut-scoring method. The toolkit already has the measurement half: `bin/app-facts.sh`
(`dependencies.json`), `skills/module-dependency-review.md` (tangles, pairs, cohesion, hubs) and
`skills/layering-review.md` + `bin/app-layer-map.sh` (the edges that point the wrong way, with a
cut ladder). The missing half is **scoring a proposed cut and executing it**.

### Rehost — what mxcli can and cannot do today (v0.26.0, probed in a cloud container 2026-10-12)

- The MDL statement `describe module <M> with all` (via `-c`) emits a whole module as re-executable MDL
  (`mdl 1;` header); the *subcommand* `mxcli describe module <M>` emits only the module and its roles
  (found in increment 1a, `pipelines/mendix-mpr/README.md`). 25
  document types are covered, including nanoflows, Java actions (signature only — the body is a
  stub, `migrate-general.md`), JavaScript actions, scheduled events, queues, REST and OData
  services, mappings, JSON structures.
- mxcli reads MPR v1 (single SQLite, Mendix 9 and 10 before 10.21) and MPR v2 directly. It claims
  Mendix 8 to 11 but is **tested only against 11.x**. Reading a Mendix 9/10 `.mpr` is the first
  probe, not an assumption.
- `mxcli new --version 10.24.0` creates Mendix 10 fixtures headless; MxBuild for any version downloads
  from the CDN in the cloud container (verified HTTP 206 on `mxbuild-11.12.0.tar.gz`).
- Known non-expressible (`skills/learned-mdl-cannot-express.md`): pluggable widgets with
  list-valued properties, page-variable writes, file upload widgets, Java action bodies, custom
  Dojo widgets (no React target anyway), theme/CSS (not in the model). Every rehost therefore ends
  with a **fidelity ledger**, never a claim of 100 %.

### Target apps (public, free)

| Target | Mendix | Fits | Caveat |
|---|---|---|---|
| **Maintenance & Field Service Management template** (Marketplace 204718, v1.1.1) | 9.24.2 | The only free, business-domain, plausibly multi-domain monolith: assets, scheduling, work orders, mobile client | Account needed to download; depends on Mendix SSO (removed from Marketplace 1 Nov 2026 — pull it before then); module/entity counts unpublished |
| **GenAI Showcase App** (github.com/mendix/genai-showcase-app) | 11.12 (older releases 9.24.2 / 10.24 on Marketplace 220475) | 48 modules, MIT, `git clone` — the scale test for `describe module` round-trip | Modules are deliberately independent: good for Rehost, weak for Decompose |
| Siemens manufacturing templates (Paperless SOP 120142, Smart Warehousing, Quality Inspection, Workforce Mgmt, …) | 9.x | Candidate pool for a second Mendix 9 target | Versions not indexed; each smaller than FSM |
| User's own large Mendix 11 project | 11 | The honest fidelity ledger — real widgets, Java, theme | Private; read-only runs only; never a public fixture |
| ako/mxcli-banking, -timeregistration, -ledger (GitHub, Apache-2.0) | 11.13/11.14 | Single-module round-trip smoke tests | Too small for Decompose |

Everything else on GitHub is single-module scale. Marketplace pages need SSO even to read.

---

## 2. Where the work lands (authoring rule, `CLAUDE.md` → "Writing in this toolkit")

| Piece | Home | Reads |
|---|---|---|
| MPR reader / MDL emitter wrapper (`describe module` per module, fidelity ledger) | `pipelines/mendix-mpr/` | a source (the `.mpr`) |
| Cut scoring | `bin/cut-score.sh` (+ `bin/lib/`) | `analysis/app-facts/dependencies.json`, catalog | 
| Decompose judgement, landscape blueprint, slice loop | `skills/decompose-app.md` | the score, the dossier |
| Rehost judgement (what to regenerate, what to hand-fix, done criteria) | `skills/rehost-app.md` | the fidelity ledger |
| Entry-mode rows | `skills/conversion-runbook.md` → Entry Modes; `bin/lib/skill-routing.tsv` | — |

Rehost is a **migration whose extractor reads a Mendix model**: upstream of the BRD it lives in
`pipelines/`, downstream it reuses Stages 2–6 unchanged. Decompose is **existing-app-change
mode with a new Stage 3 instrument and a per-slice Stage 5 loop**.

---

## 3. Decompose pipeline — stages

| Stage | Reuses | New |
|---|---|---|
| 0a Map | `app-facts.sh`, `app-report.sh`, dossier §3, layer map | — |
| 0b Scope ✋ | interview protocol | The three questions: why split (team, cadence, licence, risk), how many apps may exist (licensing), which integration lanes are allowed (OData/REST only — no Event Broker licence) |
| 3 Cut scoring ✋ | `layering-review.md` cut ladder | `bin/cut-score.sh`: for each candidate partition (from the layer map's levels, or user-named), score every crossing edge by ref kind: `associate` (external-entity rewrite, no aggregates), `call` (OData action or REST), workflow crossing (blocker), security role crossing (blocker), shared `System.FileDocument` (REST, binaries), scheduled event ownership. Output: `analysis/cut-score.html|json`, one row per edge with a lane and a cost class; a partition's total is the sum. User picks or amends; decision in `PROJECT.md` |
| 4 Landscape blueprint | `architecture-blueprint.md` | A target-landscape section: apps, published services per edge, identity broker, the data ownership per entity |
| 5 Slice loop (strangler) | `iterative-build-loop.md`, `existing-app-change.md` | Per slice: (1) regenerate the slice's module(s) into the new app with the Rehost extractor; (2) replace each crossing edge in the monolith by a consumed service and in the new app by a published one; (3) regression baseline from Track B on both sides; (4) data copy per owned entity; (5) retire the module in the monolith. The monolith stays live throughout — the "keep the core and phase out" answer |
| 6 Verify | journeys, e2e | Cross-app journeys: one journey crosses each cut edge at least once (denominator: all scored edges) |

**Answer to "take apart or rebuild":** take apart, by slice, each slice regenerated with the
Rehost extractor. Rebuild-from-scratch is only the right call when the fidelity ledger of a
Rehost dry run says the model carries more non-expressible content than expressible — that is a
number the Rehost track produces, not an opinion.

---

## 4. Rehost pipeline — stages

| Stage | What |
|---|---|
| 0 Read probe | `mxcli -p old.mpr -c "list modules"` on the real Mendix 9/10 file. Pass/fail is the first field result; a failure is a bug report to mendixlabs/mxcli and the track stops until it reads |
| 1 Extract | `describe module` per own module → `mdlsource/rehost/<Module>.mdl`; marketplace modules are recorded by name and version, never regenerated (reinstalled via `marketplace install`) |
| 1b Fidelity ledger | Per document: `emitted` / `stub` (Java body) / `not-expressible` (from the cannot-express list, detected by `check` or by a widget inventory) / `marketplace`. Denominator: every document in the source catalog. This is the artifact that decides rebuild-vs-split and sizes the hand-fix work |
| 2–4 | BRD/architecture only where the user wants to redesign; the default is a 1:1 regenerate, so these stages are WAIVED with a reason |
| 5 Regenerate | `mxcli new --version 11.x`, reinstall marketplace modules, exec the module scripts in dependency order (layer map order), mxbuild gate |
| 6 Verify | `diff --format struct` old vs regenerated per module (zero structural drift target); Track B regression baseline recorded on the old app replayed on the new one |

Theme, Java bodies, custom widgets and data migration are hand-off items on the ledger, never
silent.

---

## 5. Increments — small first, parallel tracks

| # | Track | Target | Deliverable | Runs where |
|---|---|---|---|---|
| 1 | Rehost | ako/mxcli-banking (11.x, one module) | **DONE 2026-10-12** — `pipelines/mendix-mpr/rehost-extract.sh`: 155/155 docs, 154 identical, mx check 0, mxbuild green, struct diff empty; ledger format set | cloud |
| 1 | Decompose | Tier 0 synthetic: 4 modules, one tangle, built in Mendix **10.24** with `mxcli new` | **DONE 2026-10-12** — `bin/cut-score.sh` + `tests/wave2/test-cut-score.sh` (56 checks): tangle → blocker, foreign aggregate → costly, association-only → acceptable, all found. Not yet in a skill or the routing table | cloud |
| 2 | Rehost | GenAI Showcase (48 modules, 11.12) | scale: time per module, ledger over a real widget mix | cloud |
| 2 | Decompose | FSM template (9.24.2) | **Read probe PASSED 2026-10-12** (MPR v1, 45 own modules, 1896 microflows; captures in `pipelines/mendix-mpr/samples/fsm-template-9.24.2/`). **Cut scoring DONE 2026-10-12** (`samples/fsm-template-9.24.2/cut-score-findings.md`): best landscape Planner (25) \| Mobile+Sync+Utils (14) \| retire 3; classifier gaps found: client-side `call` sub-types, missing `sync` kind. First slice: `NativeNote` | cloud |
| 3 | both | FSM (a copy; the original stays read-only) | first actual slice: `NativeNote` + its `Synchronization_Note` flows out into a fresh **Mendix 11** app, crossing edges rewired, journeys across the cut. Decided 2026-10-12: target is Mendix 11, monolith side is a copy. Route decided 2026-10-12 by the probe (merged): **hybrid, MPK mover + MDL edges**, 9.24 copy → `mx convert` 10.24 → export → install into 11.x | cloud |
| 4 | both | user's Mendix 11 project | fidelity ledger and cut score on a real customer-shaped app; read-only | user's container |

Field-proof rules apply (`CLAUDE.md` → "Shipping an instrument"): captured fixtures, both
layouts, a cited field run per instrument, a producer for every artifact consumed.

---

## 6. Open questions (answers go to `PROJECT.md` of the first field project)

1. Target landscape: Mendix apps only, or may a slice leave Mendix? (changes the lane table in cut scoring)
2. ~~Event Broker licence?~~ **Answered 2026-10-12: no.** Business Events is not a lane.
3. Rehost done-criterion: model builds clean, or parity proven by the Track B regression baseline?
4. ~~FSM download~~ **Done in the cloud container 2026-10-12** (`MENDIX_PAT`). Still: keep a copy on a user machine before 1 Nov 2026 — the container is ephemeral.
5. Data migration during a slice (copy per owned entity): in scope of the toolkit, or always a customer job?
