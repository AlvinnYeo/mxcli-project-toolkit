# Decompose App — Splitting a Mendix Monolith into Several Apps

**Applies to:** any mxcli project — an existing Mendix app (9 or later) being split into several
Mendix apps, one slice at a time, with the monolith staying live (strangler).
**Purpose:** Pick cuts that are both a business capability and cheap to wire, move each slice by
module package (MPK), account for every crossing edge, and report the level each slice reached.
This is the Change-an-existing-app mode (`existing-app-change.md`) with a cut-scoring Stage 3 and a
per-slice Stage 5 loop.
**Evidence:** `process/decompose-and-rehost-plan-2026-10-12.md` (decisions, increments 1–5) and the
FSM template field runs under `pipelines/mendix-mpr/samples/fsm-template-9.24.2/`.

**Not this skill:** regenerating a whole `.mpr` as MDL into a clean app → `rehost-app.md`.
Module boundaries *inside* one app → `modularize-domain.md` / `layering-review.md`.

---

## Stage 0 — Preconditions and scope

Bound: every line below is a `PROJECT.md` register line, `CONFIRMED` or `ASSUMED`.

1. **Mendix 9 or later.** Earlier versions are out of scope; the upgrade hop is the customer's job.
2. **Work on a copy.** The original `.mpr` is read-only for the whole decomposition.
3. **A 9.x monolith is converted to 10.24 first** (`mx convert`, on the copy) — a means, not a
   deliverable. Why: mxcli 0.26 cannot create or alter a microflow in a 9.x project, `mxcli run`
   cannot run a 9.x app, and Mendix refuses a 9.x package into 11.x. Budget the one-time fixes
   (marketplace and widget updates, Java API edits): on FSM they cost more than the seam itself
   (`seam-probe/FINDINGS.md`).
4. **Lanes are OData and REST only.** No Event Broker licence, so Business Events is not a lane; an
   edge that is neither OData nor REST blocks.
5. **Scope interview** (`interview-protocol.md`; ask, then stop): why split (team, cadence, licence,
   risk); how many apps may exist (each app is a licensed cloud node); may a slice leave Mendix;
   is data migration of existing rows in scope (the toolkit has not measured it).

## Stage 1 — Read and score

Bound: `analysis/cut-score.json` exists for the chosen cut, and each slice has a written business
reason beside its coupling numbers.

1. Facts: `project-bin/app-facts.sh` (writes `dependencies.json` and the catalog), then
   `bin/app-layer-map.sh`.
2. Score candidate cuts: `bin/cut-score.sh --cut "A,B|C|D"` (read its header for flags). Every cut
   on a tangled monolith reads `blocked`; compare crossing refs and blocker rows, not the verdict.
   Retire test modules; copy utility modules a slice pulls on.
3. **Choose on business fit AND coupling.** The failure: on FSM, `NativeNote` was the cheapest cut
   the score found and became the first slice — and it is a poor business slice. Notes belong to
   work orders: 238 in-edges stayed behind, 26 behaviour stubs went out
   (`slice-nativenote/FINDINGS.md`). The recipe: build a capability table per
   `web-slice-candidates.md` — modules, entities, roles using it, in/out refs by lane, biggest
   no-lane calls, one sentence of business fit — and rank. A slice that is mostly inbound reads
   (OData-able) and a plausible separate system of record (Assets & Parts, Insights) beats a cheap
   fragment of the core.
4. Known score blind spots (`cut-score-findings.md`): `call` mixes server and client-side calls
   (a nanoflow/JS-action call lanes *copy*, not OData); `sync` refs never reach
   `dependencies.json`, so an entity synced to the device that lands in the other app is an
   unseen blocker. Check both by hand.
5. **Native and web slices differ.** A native slice needs a native profile: target the Blank
   Native Mobile starter. An offline profile cannot sync an external entity, so data the device
   needs from the other app arrives as REST-fed local copies, not OData.

## Stage 2 — Sequence the cuts by dependency direction

Bound: for each planned slice, every out-edge target is either moving with it, copied, platform,
or already published by the monolith.

A slice can only go seam-live when what it depends on answers over HTTP. The failure: Assets &
Parts reached build-green with **120 out-stub rows** (Technician, Customer, Ticket, Roster pickers
empty) that the seam work could not reduce, because every seam call went *in* and the core it reads
stayed unpublished in the monolith (`slice-assets/FINDINGS.md` → "Stub count").

Recipe — pick one, record it in `PROJECT.md`:
- **Monolith publishes first.** Before cutting a leaf, publish the core services its out-edges need
  (OData for reads, REST for writes) from the 10.24 monolith copy; the slice consumes them.
- **Cut in dependency order.** Cut what the leaf depends on before the leaf, so out-edges point at
  an app that already publishes.

## Stage 3 — Move the slice (MPK route)

Bound: every slice module installed; target `mx check` errors are crossing edges only.

1. Create the target. Web: `mxcli new <App> --version 11.x`. Native: download the Blank Native
   Mobile starter and `mx create-project` with an **absolute** `--output-dir` (relative fails).
2. Export each module from the 10.24 copy:
   `python3 -I pipelines/mendix-mpr/export-module-mpk.py <src.mpr> <Module> <out.mpk> --json`.
   It keeps unit and entity IDs, scrubs secrets, and refuses MPR v2 sources (read its header).
3. Install **dependencies first**: marketplace modules the slice needs (`marketplace install`),
   then copied modules, then the slice: `mxcli marketplace install --file <out.mpk> -p <target.mpr>`.
4. Mendix 10 targets: `mxcli fix widgets` after page exec. 10.x packages into 11.x: legacy widgets
   become CE0582 on the React client with no warning at install. Workaround (increment 5):
   `mxcli bson dump` plus the generators in `slice-assets/tools/` (`legacy-extract.py`,
   `gen-widgets.py`); converted pages are `not-expressible` drift on the fidelity check.
5. Java bodies arrive byte-identical; Mendix 9 API calls are hand-edits
   (`pipelines/mendix-mpr/README.md` → "The MPK route").

## Stage 4 — Account for every edge

Bound: `bin/cut-ledger.sh` exits 0 (0 unresolved rows).

1. Write `slice.txt` (modules, plus `Module.Doc` lines for documents that move alone) and a
   `cut-rules.tsv` — model it on `slice-assets/cut-rules.tsv`; every rule carries evidence.
2. `bin/cut-ledger.sh --catalog <catalog.db> --slice slice.txt --rules cut-rules.tsv
   --check-log <mx-check.txt> --exporter-json <export.json> -o cut-ledger.tsv`. Exit 1 while any row
   is unresolved.
3. Resolutions: `resolved[:how]` (moved, copied, starter, marketplace, odata), `stub` (green but
   carries no behaviour — evidence says what is missing), `handoff` (named human work), `retire`,
   `platform`. **The stub count is the progress measure**; a stub is never a resolution.

## Stage 5 — Build the seam

Bound: every behaviour-carrying stub is replaced by a working call, or is still counted.

- **Reads: OData.** Publish entities from the owning app, consume as external entities. A published
  entity needs a key, and the key needs a unique validation rule (CE6624 otherwise).
  Local → external associations pass `mx check` (10.24), so consumers can be re-pointed.
- **Writes: a published REST action** backed by an upsert microflow; primitive parameters become
  query parameters, so no JSON structures or mappings are needed. Base URL in a per-environment
  constant.
- **Error handler is mandatory.** The failure: the first seam call had no `on error` handler, so a
  slice outage would roll back the monolith's own commit (`seam-probe/FINDINGS.md` → "Failure
  coupling"). Use `on error without rollback` plus a log, and a retry flag or queue.
- **Security Production on both sides.** A machine role is the only role granted on the services
  (a human role gets 404 on OData); basic-auth credentials in machine-local constants, never git.
  Stub entities need module roles too (CE2729 otherwise).
- Monolith edits: ALTER cannot replace a decision — replace the call at the actual write one level
  down.

## Stage 6 — Prove and report the level

Bound: the slice report names exactly one level (CONFIRMED 2026-10-12, plan §6 Q3).

| Level | Criteria |
|---|---|
| 1 build-green | `cut-ledger.sh` 0 unresolved, `mx check` 0, `BUILD SUCCEEDED`, moved documents describe-identical |
| 2 seam-live | every behaviour-carrying stub replaced by a working REST/OData call; security Production, roles mapped |
| 3 strangled | monolith in-edges rewired; one journey per crossing edge passes; module deleted from the monolith |

Calling level 1 "done" hides the stubs. Run at least one Playwright journey across the seam in the
shape of `project-tests/e2e/journey-runner.js`: landing guard per step, data effects verified by
`mxcli oql` in the owning database, a ledger pointer per step, exit 2 for an instrument fault. Model:
`slice-assets/journey/assets-seam.journey.js`.

## Stage 7 — Learnings

Bound: every finding of the run is in exactly one place.

- mxcli defect with verbatim repro → `contrib/inbox/`, triaged into `bug-logs/mxcli-bugs.md`.
- MDL rule an author would trip on → `contrib/inbox/`, promoted to `skills/learned-mdl-preflight.md`.
- Judgement about cutting, sequencing, seams → this skill. Instrument gap → `bin/` with a fixture.

`CHANGELOG.md` line in the same commit, crediting the source project.

---

## mxcli 0.26 traps on this route

Each line: trap → workaround → where it is written up (`contrib/inbox/2026-10-12-*`).

- Microflow create/alter refused on 9.x; `mxcli run` fails on 9.x → convert to 10.24 (`increment-4-seam-probe`).
- exec is not atomic; a recommended drop + create can stop after the drop → copy first, `mx check` after every exec (`increment-3-nativenote`, `increment-4-seam-probe`).
- No `-p` silently picks any `.mpr` in the working directory → always pass `-p` (`increment-3-nativenote`).
- `with all` omits nanoflows → describe them one by one (`increment-3-nativenote`).
- JS/Java action type parameters describe as entity `.Entity` → hand-off row (`increment-3-nativenote`).
- No native navigation profile can be created → native starter as target (`increment-3-nativenote`).
- OData publish passes `check` with no key or a non-unique key → add a unique rule; expose bare attribute names, not quoted (`increment-5-web-assets`).
- Combo box on an association passes `check`, fails exec or `mx check` → wrap in a data view (`increment-5-web-assets`).
- `marketplace update` needs `--force` on a converted copy and leaves CE0463 → `mx update-widgets` with an absolute path (`increment-4-seam-probe`, `increment-5-web-assets`).
- `limit 1` retrieve is a list but `check` accepts object operations → use `first`, then drop + create (`increment-4-seam-probe`).
