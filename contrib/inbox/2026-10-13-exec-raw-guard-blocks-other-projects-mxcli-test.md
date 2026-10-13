# Field confirmation of #228 case 3: another project's `mxcli test` blocks exec.sh

**From:** a field project (anonymised)
**Date:** 2026-10-13
**Kind:** bug
**Field evidence:** on 2026-10-13 a `mxcli test` run in a second toolkit project on the same machine
(writing only to that project's own `.mpr`) made this project's `bin/exec.sh` refuse a page script;
it recurred several times that day. Toolkit commit c1efcb3; `project-bin/exec.sh` is unchanged on
master 0c62f6f.
**Proposed target:** `project-bin/exec.sh` step 3 — already addressed by open PR #257 (and the
per-project lock in open PR #304). This note is evidence for those PRs, not a new design.

---

Issue #228 lists three false positives of the raw-exec guard

```bash
if pgrep -fl "mxcli exec" 2>/dev/null | grep -qv "$$"; then
  echo "✗ A raw 'mxcli exec' is already running elsewhere — refusing to write concurrently."
```

and says of case 3 ("another project's `mxcli test` execs temp scripts"): *"This one has not been
independently verified."* This project verified it:

- Project B (a separate app, separate folder, separate `.mpr`) was running `mxcli test` against its own
  model. `mxcli test` adds and removes its `MxTest` microflows through `mxcli exec`, so its process
  list contains the substring.
- In project A, `./bin/exec.sh mdlsource/3-module/03a-....mdl` refused with the message above and
  wrote nothing. Waiting for B's test run to finish and re-running A's exec applied cleanly.
- As #228 says, nothing reached A's BUILD-LOG: the guard exits before `log_build`, so the only trace is
  the agent transcript. That is why this note has no BUILD-LOG row to quote.

Two projects cannot share one `.mpr`, so the cross-project refusal protects nothing. #228's acceptance
check "`mxcli test --local` running in project B does not block A" is the right test; this is one
field case for it.

Workaround until #257 or #304 merges: wait for the other project's process to end. `FORCE_EXEC=1`
also passes the guard, but it skips the Studio Pro and uncommitted-model refusals too, so it is not
a safe workaround.
