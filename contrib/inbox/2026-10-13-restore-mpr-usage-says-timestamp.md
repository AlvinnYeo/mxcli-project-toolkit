# restore-mpr.sh: usage says `[timestamp]`, but a bare timestamp is refused; it needs the snapshot's full path

**From:** a field project (anonymised)
**Date:** 2026-10-13
**Kind:** bug
**Field evidence:** hit during recovery from an mxbuild crash (see the inbox note "exec.sh keeps an
MDL write when mxbuild crashes"); reproduced afterwards on a scratch project with the toolkit's
`project-bin/restore-mpr.sh` (blob c7ae37b, identical at c1efcb3 and on master 0c62f6f).
**Proposed target:** `project-bin/restore-mpr.sh`

---

## What happens (finding, reproduced)

The header says:

```
# Usage: ./bin/restore-mpr.sh [timestamp]    (defaults to the newest snapshot)
```

`snapshot-mpr.sh` names snapshots by timestamp (`.mpr-snapshots/20261013-120000/`), so the natural
call is the folder name. On a scratch project with exactly that snapshot:

```
$ ./bin/restore-mpr.sh 20261013-120000
ERROR: snapshot 20261013-120000 is missing App.mpr
exit=1
```

The full path works:

```
$ ./bin/restore-mpr.sh /path/to/project/.mpr-snapshots/20261013-120000/
Restoring from: /path/to/project/.mpr-snapshots/20261013-120000/
  Restored: App.mpr
  Restored: mprcontents/ (1 units verified)
Restore complete. Verify with: ./mxcli docker check -p App.mpr --no-update-widgets
```

Cause (code reading): `SNAP="${1:-...}"` is used as given, after `cd "$MODEL_DIR"`. A bare name is
therefore looked up relative to the model directory, not under `$SNAP_DIR`. A relative path such as
`.mpr-snapshots/<ts>` works only when the model directory is the project root, so on a two-tree
checkout (`app/` holding the `.mpr`) it fails too (that part is a hypothesis, not tested).

The error message is also misleading: it says the snapshot is *missing the .mpr*, which sends you to
inspect a healthy snapshot instead of fixing the argument. In a recovery, under pressure, that cost
a few minutes.

## Proposed fix

```bash
SNAP="${1:-$(ls -dt "$SNAP_DIR"/*/ 2>/dev/null | head -1)}"
# accept a bare timestamp or a path relative to the caller
[ -n "${1:-}" ] && [ ! -d "$SNAP" ] && [ -d "$SNAP_DIR/$1" ] && SNAP="$SNAP_DIR/$1"
```

(resolve a caller-relative path before the `cd`, as exec.sh does for its script argument), and make
the usage line say `[timestamp | snapshot path]`. When the argument resolves to no directory at all,
say `no snapshot named <arg> in $SNAP_DIR` and list the three newest.

Retest: the two commands above on a scratch project. Today: exit 1 and exit 0. After: exit 0 and exit 0.
