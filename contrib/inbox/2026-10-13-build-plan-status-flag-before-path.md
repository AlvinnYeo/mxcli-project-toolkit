# build-plan-status.sh: a flag before the project path is dropped and the path is refused

**From:** a field project (anonymised)
**Date:** 2026-10-13
**Kind:** bug
**Field evidence:** hit in the field as `build-plan-status.sh --json <root>`; reproduced on a scratch copy
of `project-bin/build-plan-status.sh` (blob a5cfc2a, identical at c1efcb3 and on master 0c62f6f).
**Proposed target:** `project-bin/build-plan-status.sh` (argument parsing, lines 46–62)

---

## What happens (finding, reproduced)

The usage line is `build-plan-status.sh [project-dir] [--html] [--json] [--quiet] [--refresh]`, but
every other toolkit script accepts flags anywhere, so agents write the flag first:

```
$ bash build-plan-status.sh --json /path/to/project
unknown arg: /path/to/project
exit=2
$ bash build-plan-status.sh --quiet /path/to/project
unknown arg: /path/to/project
exit=2
```

Cause (code reading):

```bash
ROOT="${1:-}"
[ -n "$ROOT" ] && [ "${ROOT#--}" = "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
shift 2>/dev/null || true
```

When `$1` is a flag, ROOT falls back to the git top level or `pwd`, and the unconditional `shift`
then throws the flag away. The real path is left for the flag loop, which rejects it. Our field note
first described this as "the flag's value is read as the project"; the reproduction shows the exact
behaviour above (flag lost, path refused, exit 2), which is at least loud.

**The quiet variant (finding, reproduced on a scratch project with one `### Phase 1` heading):** from
inside a project, `build-plan-status.sh --json` with no path runs on `pwd`, but `--json` has already
been shifted away. The table prints, no error is shown, and `architecture/build-plan.json` is not
written. The same project with `build-plan-status.sh . --json` prints `wrote architecture/build-plan.json`.

## Proposed fix

Parse every argument in one loop: a word starting with `--` is a flag, the first other word is the
project, a second one is an error.

```bash
ROOT=""
for a in "$@"; do
  case "$a" in
    --html) WRITE_HTML=1 ;; --refresh) WRITE_HTML=1; REFRESH=1; QUIET=1 ;;
    --json) WRITE_JSON=1 ;; --quiet) QUIET=1 ;;
    --*) echo "unknown arg: $a" >&2; exit 2 ;;
    *) [ -z "$ROOT" ] && ROOT="$a" || { echo "unexpected second path: $a" >&2; exit 2; } ;;
  esac
done
[ -n "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

Retest: the two commands above (today exit 2; after the fix exit 0), plus `--json` alone from inside
a project with a Phase heading (today no JSON; after the fix `wrote architecture/build-plan.json`).
