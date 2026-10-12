**From:** toolkit lab runs for `process/decompose-and-rehost-plan-2026-10-12.md`, increments 1a (Rehost, ako/mxcli-banking 11.13.0) and 1b (Decompose fixture, Mendix 10.24.0)
**Date:** 2026-10-12
**Kind:** bug / learning candidates
**Field evidence:** verbatim captures in the lab trees (`lab/rehost/captures`, `lab/decompose/captures`, not shipped); each item below quotes the message seen
**Proposed target:** `bug-logs/mxcli-bugs.md` (items 1–8), `skills/learned-mdl-preflight.md` (items 9–11; item 9 already promoted in the same commit)

mxcli v0.26.0 (2026-10-11), Linux cloud container, no Studio Pro.

## mxcli defects / doc gaps (report upstream to mendixlabs/mxcli)

1. **`mxcli describe module <M>` subcommand emits only the module and its roles.** Help text says "Describe a module (all contents)". Output is `mdl 1; create or modify module Banking; create or modify module role …` and nothing else, for `--mdl 0` and `--format json` too. The whole-module emitter is the MDL statement `describe module <M> with all`, reachable only via `-c`, and documented only in `mxcli changelog`.
2. **`describe module … with all` emits flows in catalog order, and `mxcli check` refuses its own output**: 14× `MDL-ORDER01 … references microflow Banking.SUB_SeedBillers before it is created (statement 145)`; `exec` then `Refusing to execute: 14 unresolved reference(s). Nothing was written.` (correct refusal). mxcli knows the call graph (`callers`/`callees`) and could emit in call order. Workaround shipped: `pipelines/mendix-mpr/lib/topo-order-mdl.py`.
3. **`with all` omits image collections** — `MyFirstModule.Images` is `describable` in `project-tree --json` and `describe imagecollection` emits it, but the module-level emitter leaves it out.
4. **`describe userrole` drops `CheckSecurity: false`** — replaying the output re-creates the role with the default, a silent security change.
5. **`describe` of a doc comment loses a markdown `* ` bullet** (the one drift row of 155 on the banking round trip).
6. **Set-mode `check` prints "Check passed!" after an earlier failure in the same invocation.**
7. **`mxcli new --version 10.24.0` ships a layout that cannot build**: `App_Default` uses Atlas design properties (`Flex container`, `Align items Y`, `Disable row wrap`, `Grow / shrink (self)`) that the bundled Atlas_Core 3.17.0 does not know; mxbuild in step 6/7 ends `BUILD FAILED` but `new` still prints "Project created" and exits 0. Workaround: `ALTER PAGES SET LAYOUT = Atlas_Core.Atlas_Default WHERE LAYOUT = MyFirstModule.App_Default; DROP LAYOUT MyFirstModule.App_Default;`. Fine on 11.13.0.
8. **CE0463 on every mxcli-written DATAGRID on a 10.24 target** ("The definition of this widget has changed. Update this widget…"): mxcli writes Data grid 2 against a newer DataWidgets definition than the 2.31.0 the 10.24 scaffold carries. `mxcli fix widgets -p <app>.mpr` resolves it (15 units changed, MPR v2 preserved). Rule for 10.x targets: after any page exec, `fix widgets` before mxbuild. `bin/bug-lookup.sh CE0463` currently returns nothing.

## MDL learnings (preflight candidates)

9. **CRLF inside string literals is load-bearing.** Studio Pro stores annotation text with `\r\n`; `describe` emits it verbatim; a tool that reads the file in text mode and writes `\n` changes the flow, and `check` says `this change cannot be spliced into the stored flow: the free annotations change … [MDL-V1-REBUILD]`. Byte-preserving I/O (`newline=''`) only.
10. **`RETURNS Boolean AS $Closed` does not declare `$Closed`.** `$Closed = true;` → "a reassignment says 'set' under mdl 1"; `SET $Closed = true;` alone → "variable 'Closed' is not declared". An aggregate or a retrieve declares; a plain return variable needs `DECLARE $Closed Boolean = false;` first.
11. **`LOG INFO NODE 'Util' $Message;` is not grammar.** The message is a template: `LOG INFO NODE 'Util' '{1}' WITH ({1} = $Message);`, and a non-String argument must be wrapped (`toString($Count)`).

## Toolkit items (ours, not mxcli's)

12. `project-bin/app-facts.sh` hard-requires the `sqlite3` CLI (`command -v sqlite3 || exit 2`) for seven one-column guard queries while the facts come from Python's `sqlite3` module. The CLI is not installable in the cloud container (`apt-get`: `Unable to locate package sqlite3`). Route the guards through `$PY`.
13. `project-bin/app-facts.sh` joins `refs` to `objects` by qualified name, so attribute-level refs (`member`, `xpath`) never reach `dependencies.json`; `bin/cut-score.sh`'s `member`/`xpath` lanes cannot fire until the producer carries them.
14. `mxcli marketplace download <id> --output` takes a file path; a directory fails with `rename … file exists`.
