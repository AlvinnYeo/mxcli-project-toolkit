# Mendix MPR pipeline — the Rehost extractor

**Source platform:** an existing Mendix app (`.mpr`, Mendix 9 and above, MPR v1 or v2).
**Plan:** `process/decompose-and-rehost-plan-2026-10-12.md` §4 (Rehost) — read a model with
`mxcli describe`, regenerate it as MDL into a fresh target app, and write a **fidelity ledger**
(one row per source document; the denominator in the header) instead of claiming 100 %.

This is the only pipeline whose extractor reads a Mendix model. Downstream of the ledger nothing
here is Mendix-source-specific: the slice loop of the Decompose track reuses it to move a
module into a new app, and Stages 2–6 of the runbook apply unchanged.

## Run

```
MXCLI=/path/to/mxcli pipelines/mendix-mpr/rehost-extract.sh <source.mpr> <target.mpr> <out-dir> [Module ...]
```

- The target must exist: `mxcli new <App> --version <same as source> --theme none`. The script
  writes model content only; run the mxbuild gate (`project-bin/exec.sh`, or
  `~/.mxcli/mxbuild/<ver>/modeler/mx check`) afterwards.
- Modules default to every own module (empty Source column in `list modules`, System excluded).
  Marketplace modules are recorded by name and version on the ledger, never regenerated.
- Output: `captures/` (verbatim mxcli output — the golden fixtures), `mdl/` (describe output,
  the topologically ordered file that was executed, the target's describe for the diff),
  `fidelity-ledger.tsv`.

`lib/topo-order-mdl.py` reorders the flow statements of a `describe module … with all` script so
every callee is created before its caller (a flow and its `grant execute` lines move as one unit).
`lib/compare-mdl.py` normalises two describe outputs for the per-document identical/drift verdict.
Both read and write with `newline=''`: Studio Pro stores annotation text with CRLF inside MDL string
literals, and a tool that normalises it changes the flow and `exec` refuses the splice.

## Field runs

| Date | Source | Result |
|---|---|---|
| 2026-10-12 | ako/mxcli-banking `RRNetBanking.mpr` (Mendix 11.13.0, Banking 151 docs + MyFirstModule 4) → `mxcli new --version 11.13.0` | 155/155 documents emitted, 154 identical on target describe, 1 doc-comment drift; `mx check` 0 errors, mxbuild BUILD SUCCEEDED, `diff --format struct` empty. 35 s end to end |
| 2026-10-12 | FSM template v1.1.1 (Mendix 9.24.2, MPR v1, 64 MB) — **read probe only** | `list modules` 1.6 s, `graph-report` 18 s. Captures in `samples/fsm-template-9.24.2/` |
| 2026-10-12 | mendix/genai-showcase-app `GenAI Showcase App.mpr` (Mendix 11.12.0, 48 modules: 32 own + 15 marketplace; 456 entities, 1622 microflows, 180 pages, 204 Java actions) → `mxcli new --version 11.12.0` | **Measured, not build-green** — run 4, 36 modules regenerated, 36 min wall time (describes reused; 30 min more when fresh). Ledger over 2776 catalog documents: 579 identical, 271 drift, 1993 failed-exec, 43 not-emitted, 4 not-expressible, 2 target-extra. 1520 of the failures are 7 whole modules the extractor dropped: `lib/quarantine-mdl.py` cannot map lint-form check errors or mxcli's statement numbers, and `check_exec` then discards the rest of the module. Gates: the target first failed to load (`mx check` ArgumentNullException; mxcli wrote 3 microflows with a null `import from mapping` result entity, repaired by drop + create). After that, `mx check` gave 14 × CE1613 (Java action type parameters `.Entity`, missing message-definition export mappings, inherited-attribute sort) and mxbuild `BUILD FAILED`. Regression parity is not reachable headlessly (no message definitions, no rules, mutual recursion refused). Captures, ledger and verdict: `samples/genai-showcase-11.12.0/FINDINGS.md` |
| 2026-10-12 | FSM template v1.1.1 — **MPK route** (`export-module-mpk.py`): FeatureToggle, Utils, Visualizations → 10.24 and 11.13 | All installed; every residual `mx check` error a crossing edge; Utils with edges satisfied: `mx check` 0, mxbuild BUILD SUCCEEDED on 11.13 after 3 Java edits. Captures in `samples/mpk-export-probe/` |
| 2026-10-12 | FSM template v1.1.1 — **first slice (increment 3)**: `NativeNote` + 26 Synchronization_Note documents → Blank Native Mobile App 11.13.0 (9.24 copy → `mx convert` 10.24 → export → `install --file`; edges in MDL) | NativeNote 66/66 documents describe-identical on target; `mx check` 0, mxbuild BUILD SUCCEEDED; cut ledger (`bin/cut-ledger.sh`) 308 rows, 0 unresolved — 26 stubs (incl. `Synchronization.Synchronize`, synced work-order/technician entities), 98 hand-offs. A native slice cannot target `mxcli new` (no native profile). Captures in `samples/fsm-template-9.24.2/slice-nativenote/` |

Not yet exercised: workflows, REST/OData services, and the MDL regenerate step on a Mendix 9/10 source
(the read works; increment 3 moved NativeNote into Mendix 11 by MPK, not by regeneration).

## The MPK route — `export-module-mpk.py` (moving a module without regenerating it)

```
python3 -I pipelines/mendix-mpr/export-module-mpk.py <source.mpr> <Module> <out.mpk> [--no-widgets] [--json]
mxcli marketplace install --file <out.mpk> -p <target.mpr>      # new modules only; no PAT
```

The exporter writes a module package in Mendix's own format: a zip with `package.xml` and a
`project.mpr`. That `project.mpr` holds the source schema and `_MetaData` verbatim, the module's
unit subtree byte for byte, the project root, the conversion unit and four project documents. Two
of those documents are **scrubbed of secrets** (demo users, passwords, constants, credentials,
certificates), and so is navigation. The zip also carries the module's `javasource/`,
`javascriptsource/`, `themesource/` and `resources/` folders, the userlib jars that have a
`.<Module>.RequiredLib` marker, and the widget `.mpk` files its pages reference. The script header
lists what it cannot know. It refuses MPR v2 sources and schemas that differ from the reference.

**Version window (Mendix's, not ours).** `mxcli marketplace install` imports through the target's
`mx module-import`:

- 9.24's `mx` has no `module-import`.
- 11.13 refuses packages older than 10.21.
- So a 9.x → 11.x move has two hops: `mx convert` a copy of the source to 10.24, export, then install.

On Mendix 10 and 11, `mx create-module-package <mpr> <Module>` is the vendor's headless export.
It refuses modules that have errors, and it **regenerates every unit and entity ID**. This
exporter keeps them, and mxcli's install keeps them too: measured from 9.24 through 10.24 to 11.13.

**Field run 2026-10-12, FSM template 9.24.2:**

- FeatureToggle, Utils and Visualizations each installed into 10.24 and into 11.13.
- Every `mx check` error (2 / 7 / 134) was a crossing edge to a module the target lacks. There
  were 0 version-conversion errors and 0 package-format errors.
- Utils with its edges satisfied (3 Marketplace modules, 1 constant in MDL) reached `mx check`
  0 errors. After three Java hand-off edits, mxbuild BUILD SUCCEEDED on 11.13.0. The edits:
  `this.context()` is a Mendix 9 API; two orphan action files used `CustomJavaAction`; one jar's
  RequiredLib marker names a former module.
- The Java bodies arrive byte-identical.

Verbatim captures: `samples/mpk-export-probe/captures/`. The `R*` files are the final run with
the committed script. For Mendix 9 `mx` on Linux, the container needs `libgdiplus` and JDK 17.

## mxcli findings from the first run (filed in `contrib/inbox/2026-10-12-decompose-rehost-increment-1-mxcli-findings.md`)

The subcommand `mxcli describe module <M>` emits only the module and its roles; the whole-module
emitter is the MDL statement `describe module <M> with all` via `-c`. Describe output is in catalog
order and the tool's own `check` refuses it (MDL-ORDER01). Image collections are omitted by
`with all`. `describe userrole` drops `CheckSecurity: false`. Demo-user passwords describe as
`'***'` and project security level describes as a report, not MDL — both are ledger hand-off rows.
