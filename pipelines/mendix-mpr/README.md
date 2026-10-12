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

Not yet exercised: nanoflows, Java/JavaScript actions, snippets, workflows, REST/OData services,
`marketplace install` on a target that lacks the source's modules, and the regenerate step on a
Mendix 9/10 source (the read works; the write into Mendix 11 is increment 2).

## mxcli findings from the first run (filed in `contrib/inbox/2026-10-12-decompose-rehost-increment-1-mxcli-findings.md`)

The subcommand `mxcli describe module <M>` emits only the module and its roles; the whole-module
emitter is the MDL statement `describe module <M> with all` via `-c`. Describe output is in catalog
order and the tool's own `check` refuses it (MDL-ORDER01). Image collections are omitted by
`with all`. `describe userrole` drops `CheckSecurity: false`. Demo-user passwords describe as
`'***'` and project security level describes as a report, not MDL — both are ledger hand-off rows.
