# Rehost App — Regenerating an Existing Mendix App as MDL into a Fresh App

**Applies to:** migration — a Mendix model (`.mpr`, Mendix 9 or later) is the legacy source, and the
whole app is regenerated as MDL into a clean target app.
**Purpose:** Run the Rehost extractor, drive its check → quarantine → exec → resume loop to a
fidelity ledger, and report the CONFIRMED done-criterion — *build-green with hand-offs* — instead of
a fidelity percentage. Upstream of the ledger this is a pipeline (`pipelines/mendix-mpr/`);
downstream, runbook Stages 2–6 apply unchanged (Stages 2–4 are WAIVED with a reason for a 1:1
regenerate).
**Evidence:** `pipelines/mendix-mpr/README.md` (field runs), `pipelines/mendix-mpr/samples/genai-showcase-11.12.0/FINDINGS.md`,
`process/decompose-and-rehost-plan-2026-10-12.md` §4 and §6 Q3.

---

## Step 0 — Rehost or MPK move?

Bound: the choice and its reason are a `PROJECT.md` register line.

| You want | Route |
|---|---|
| The whole app re-platformed into a clean project; MDL source you own afterwards | **Rehost** (this skill) |
| One or a few modules moved into another app, Java bodies and IDs intact | **MPK move** — `decompose-app.md` Stage 3 |
| Split a monolith into several apps | `decompose-app.md` (it moves slices by MPK, not by regeneration) |

Measured scope: Rehost has run same-version only (11.13 → 11.13, 11.12 → 11.12). A 9/10 source read
works (FSM 9.24 read probe), but regeneration from 9/10 into 11 is **not yet exercised**
(`pipelines/mendix-mpr/README.md` → "Not yet exercised"). Say so in the plan; do not promise it.

## Step 1 — Prepare the target

Bound: the target opens in `mx check`, and every marketplace module of the source is installed or a
hand-off row.

1. `mxcli new <App> --version <target> --theme none`.
2. Marketplace modules are **never regenerated**: install them by name and version
   (`mxcli marketplace install`). Expect gaps and record each as a hand-off:
   - Mendix-9-built packages refuse to install into 11 (`created with version 9.24.2 … open it in
     … 10.21.0 to 10.24.99 first`): three of them on GenAI.
   - Versions no longer listed (`version "1.5.1" not found`).
   - The blank template's own modules at different versions; reinstalling a present module is not
     automatic.
3. Install the widget `.mpk` files the source pages use.

## Step 2 — Run the extractor

Bound: `fidelity-ledger.tsv` exists and its header states the denominator (every describable
document in the source catalog for the modules run).

```
MXCLI=<path to mxcli> pipelines/mendix-mpr/rehost-extract.sh <source.mpr> <target.mpr> <out-dir> [Module ...]
```

Read the script header for outputs. Defaults: every own module (empty Source column), System
excluded. Switches:
- `REHOST_REUSE_MDL=1` — reuse `<out>/mdl/<M>.mdl` from an earlier run; use it on every rerun after
  fixing the check/exec side, because the describes are the slow part.
- `REHOST_KEEP_ORDER=1` — replay modules in the order given instead of reference order (use when
  you have resolved a module cycle by hand).

**Budget** (GenAI, 36 modules): source describes ~30 min fresh with fill-in; first check/exec pass
~14 min summed; a full rerun with reused describes 36 min. A one-module app took 35 s.

## Step 3 — Understand the loop the script runs

Bound: for every module, either it landed or the run log says why it did not.

Per module, in order:
1. `describe module <M> with all` via `-c`, plus every document `with all` omits (nanoflows,
   snippets, JS actions, JSON structures, mappings, task queues, image collections), described one
   by one from the project tree.
2. `lib/topo-order-mdl.py` — callees before callers; a flow and its grants move as one unit.
3. `lib/fix-describe-output.py` — repairs the Java-action parameter comma mxcli emits inside a
   `--` comment.
4. **check → quarantine**: `mxcli check` is all-or-nothing per file; `lib/quarantine-mdl.py` moves
   the statements it rejects (with their same-module closure) to `<M>.deferred.mdl`.
5. **exec → resume**: exec stops at the first statement it cannot write; `lib/exec-resume.py`
   defers that statement with the verbatim error and continues with the rest.
6. Deferred statements retry in fixed-point passes (most are forward references into modules not
   yet created); what still fails reaches the ledger with its error.

The failure this loop exists for: the first full GenAI run executed **1 of 36 modules** — one
emitter defect plus all-or-nothing check sank the other 35 (commit a1b59bc).

Still open (GenAI `FINDINGS.md` E1–E3): when quarantine can map nothing, the rest of the module is
dropped silently — 7 modules, 1520 ledger rows, recorded only as `absent from target describe`. A
module missing from the target is an extractor fault, not 100 failed documents; and the
`never executed` counts in `run-log.txt` overstate by about 7×. Count distinct statements in
`<M>.deferred.mdl`.

## Step 4 — Read the fidelity ledger

Bound: every row is landed or a named hand-off; the hand-off count is reported.

| Verdict | Means | Action |
|---|---|---|
| `emitted-identical` | target describe equals source | none — the build still decides |
| `emitted-drift` | landed, describe differs | read the evidence; on GenAI ~190 of 271 were microflow layout (#923) or doc whitespace |
| `failed-exec` | not in the target | find the first error naming it: a dropped module, a deferred dependency, or a root cause |
| `not-emitted` | in the catalog, no describe statement | hand-off or extractor gap |
| `not-expressible` | MDL cannot carry it (NOT re-executable widgets, #923 decisions, app-level rows) | hand-off |
| `target-extra` | only in the target | check it is the template's, not a stray |

**The ledger does not decide done; the build gate does.** The failure: a sort on an inherited
attribute was `emitted-identical` on the ledger and still CE1613 in `mx check` (GenAI M4).

## Step 5 — Gate and report

Bound: the report states `mx check` errors, mxbuild result, and the hand-off count by class.

**Done = build-green with hand-offs** (CONFIRMED 2026-10-12): `mx check` 0, `BUILD SUCCEEDED`,
every ledger row landed or a named hand-off. Run the gate yourself — the script does not
(`project-bin/exec.sh`'s mxbuild gate, or `mx check <target.mpr>`).

Hand-off classes by construction in mxcli 0.26 — record each document, fix in Studio Pro:

| Class | Why |
|---|---|
| Java action type parameters | described with no type parameter; exec writes entity `.Entity` (CE1613) |
| Message definitions | no document type; every export mapping and flow on one fails |
| Rules | cannot be described or created; also missing from the denominator |
| Mutual recursion | exec refuses forward references, so both flows and their callers stay deferred |
| NOT re-executable widgets | describe marks them; e.g. `Forms$FileManager` |
| Marketplace version gaps | not installable at the source's version |
| Mendix-9-built packages into 11 | Mendix refuses them; convert through 10.24 or replace |
| Demo users, project security, theme | not carried by describe |

If the model will not load (`ArgumentNullException … EntityType.set_EntityId`), mxcli wrote a
microflow whose `import from mapping` result has a null entity: `drop microflow` then the source
`create or modify` in one script (GenAI M1).

Regression parity is **not** a Rehost gate — not reachable headlessly (message definitions, rules,
mutual recursion, live credentials). It is a separate, human-run level; say which was reached.

## Step 6 — Learnings

mxcli defects → `contrib/inbox/` (triaged into `bug-logs/mxcli-bugs.md`); extractor defects → the
pipeline with a captured fixture; judgement about what to regenerate or hand off → this skill. GenAI's
emitter defects are in `contrib/inbox/2026-10-12-rehost-increment-2-genai-mxcli-findings.md` — read it
rather than re-diagnosing. `CHANGELOG.md` line in the same commit, crediting the source app.
