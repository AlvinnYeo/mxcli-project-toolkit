#!/usr/bin/env bash
# install-project-hooks.sh — the commit-time backstop for the mxbuild gate.
#
#   ./bin/install-project-hooks.sh           # install/refresh the pre-commit + revision-note hooks
#   ./bin/install-project-hooks.sh --check   # exit 1 if any is missing or stale
#
# Two jobs. (1) pre-commit: the mxbuild-gate backstop below. (2) post-commit + post-rewrite: the
# Studio Pro revision note (2026-10-12, field project). Studio Pro's History pane lists a commit's
# changed documents from refs/notes/mx_metadata "ModelChanges", which only Studio Pro filled; CLI
# commits showed "Model changes 0". These hooks run bin/mx-metadata-note.py write HEAD after every
# commit, amend and rebase; they never block (a missing note costs a History entry, nothing
# more). The installer also adds the notes ref to each Team Server remote's push refspecs, so a
# plain `git push <remote>` carries the notes with the branch.
#
# WHY (2026-09-17, field project). A model can change without the mxbuild gate ever running — a
# bare `./mxcli exec`, an exec.sh run on a machine with no mxbuild, a Studio Pro save —
# and until now every such change committed and pushed like any other. The hook refuses
# a commit that stages model files (the .mpr and mprcontents/) unless bin/model-stamp.sh
# holds a PASS stamp for exactly that staged content. Commits that touch no model file
# are untouched. It runs on every machine, cloud or laptop, with no toolkit clone needed.
#
# Guard rules (toolkit CLAUDE.md, "Shipping an instrument" rules 6/7):
#   * rule 7 — it never blocks the remedy: ./bin/verify-model.sh is not itself a commit, so
#     there is always a way to earn the stamp without going through this hook.
#   * rule 6 — a missing/stale bin/model-stamp.sh stamp is not the only evidence accepted.
#     A recent PASS row in docs/BUILD-LOG.md (written by exec.sh on every exec, independently
#     of the stamp file — the two share no code path) lets the commit through, with a warning
#     naming which row it trusted. A stale or non-pass row does not count. Absent BOTH the
#     stamp and a qualifying BUILD-LOG row, MODEL_UNVERIFIED_OK=1 lets one commit through,
#     out loud, when someone decides to.
#
# An existing pre-commit hook that is not ours is kept and chained (moved to
# pre-commit.pre-mxtk, called first). A repo with core.hooksPath set is reported, not
# edited — its hooks live somewhere this script must not write to.
set -e
. "$(dirname "$0")/_common.sh"

cd "$PROJECT_ROOT"
git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "install-project-hooks.sh: $PROJECT_ROOT is not in a git repository"; exit 2; }
HOOKS="$(git rev-parse --git-path hooks)"
HOOK="$HOOKS/pre-commit"
MARK="# mxtk-model-stamp hook v1"
# bin/ relative to the git top level, so the hook works when the project root is a subdir.
BIN_REL="$(git rev-parse --show-prefix)bin"

if [ -n "$(git config --get core.hooksPath 2>/dev/null)" ]; then
  echo "⚠ core.hooksPath is set ($(git config --get core.hooksPath)) — add this to that pre-commit yourself:"
  echo "    \"\$(git rev-parse --show-toplevel)/$BIN_REL/model-stamp.sh\" check --staged || exit 1"
  echo "  and this to its post-commit (revision notes for Studio Pro History):"
  echo "    MXTK_HOOK=1 python3 \"\$(git rev-parse --show-toplevel)/$BIN_REL/mx-metadata-note.py\" write HEAD || true"  # portability-ok: advice text
  exit 1
fi

NOTE_MARK="# mxtk-mx-metadata hook v1"
# Team Server remotes: the platform's git host, plus any remote named in MXTK_TS_REMOTES.
ts_remotes() {
  git remote -v 2>/dev/null | awk '$2 ~ /git\.api\.mendix\.com/ {print $1}' | sort -u
  for r in ${MXTK_TS_REMOTES:-}; do echo "$r"; done
}

if [ "${1:-}" = "--check" ]; then
  rc=0
  if [ -f "$HOOK" ] && grep -q "^$MARK" "$HOOK"; then echo "  ✓ pre-commit hook installed ($HOOK)"
  else echo "  ✗ pre-commit model-verification hook missing — run ./bin/install-project-hooks.sh"; rc=1; fi
  for h in post-commit post-rewrite; do
    if [ -f "$HOOKS/$h" ] && grep -q "^$NOTE_MARK" "$HOOKS/$h"; then echo "  ✓ $h revision-note hook installed"
    else echo "  ✗ $h revision-note hook missing — run ./bin/install-project-hooks.sh"; rc=1; fi
  done
  for r in $(ts_remotes | sort -u); do
    if git config --get-all "remote.$r.push" 2>/dev/null | grep -q 'refs/notes/mx_metadata'; then echo "  ✓ $r pushes refs/notes/mx_metadata"
    else echo "  ✗ $r does not push refs/notes/mx_metadata — run ./bin/install-project-hooks.sh"; rc=1; fi
  done
  exit $rc
fi

mkdir -p "$HOOKS"
if [ -f "$HOOK" ] && ! grep -q "^$MARK" "$HOOK"; then
  mv "$HOOK" "$HOOK.pre-mxtk"
  echo "  existing pre-commit hook kept as $(basename "$HOOK").pre-mxtk and chained first"
fi
cat > "$HOOK" <<HOOKEOF
#!/usr/bin/env bash
$MARK — written by bin/install-project-hooks.sh (mxcli-project-toolkit). Re-run it to refresh.
top="\$(git rev-parse --show-toplevel)"
[ -x "\$(dirname "\$0")/pre-commit.pre-mxtk" ] && { "\$(dirname "\$0")/pre-commit.pre-mxtk" || exit 1; }
stamp="\$top/$BIN_REL/model-stamp.sh"
if [ ! -x "\$stamp" ]; then
  echo "⚠ $BIN_REL/model-stamp.sh is missing — the model-verification hook cannot check this commit (re-run the toolkit's sync-project.sh)" >&2
  exit 0
fi
if ! "\$stamp" check --staged; then
  alt=""
  blog="\$top/docs/BUILD-LOG.md"
  max_age="\${MODEL_EVIDENCE_MAX_AGE:-14400}"
  if [ -f "\$blog" ]; then
    bmtime="\$(stat -c %Y "\$blog" 2>/dev/null || stat -f %m "\$blog" 2>/dev/null || echo 0)"
    case "\$bmtime" in ''|*[!0-9]*) bmtime=0 ;; esac
    now="\$(date +%s)"
    lastrow="\$(grep '^| 20' "\$blog" 2>/dev/null | tail -1)"
    if [ "\$bmtime" -gt 0 ] && [ \$(( now - bmtime )) -le "\$max_age" ] && printf '%s' "\$lastrow" | grep -q '| pass |'; then
      alt="a recent docs/BUILD-LOG.md row (gate: pass, \$(( (now - bmtime) / 60 )) min ago)"
    fi
  fi
  if [ -n "\$alt" ]; then
    echo "⚠ no local model-stamp, but accepting \$alt as evidence the model was mxbuild-gated." >&2
    echo "  (this is NOT a guarantee the staged content matches that row — verify-model.sh is the strong check)" >&2
  elif [ "\${MODEL_UNVERIFIED_OK:-0}" = "1" ]; then
    echo "⚠ MODEL_UNVERIFIED_OK=1 — committing a model the mxbuild gate has not verified." >&2
  else
    echo "" >&2
    echo "✗ commit refused: the staged model has not passed the mxbuild gate on this machine." >&2
    echo "  Run   ./bin/verify-model.sh   (one mxbuild, stamps the model when clean), then commit again." >&2
    echo "  Deliberate override, once:   MODEL_UNVERIFIED_OK=1 git commit ..." >&2
    exit 1
  fi
fi
exit 0
HOOKEOF
chmod +x "$HOOK"
echo "  ✓ pre-commit hook installed -> $HOOK"
echo "    (refuses to commit .mpr/mprcontents changes that have no mxbuild-gate PASS stamp; ./bin/verify-model.sh writes one)"

# --- revision notes for Studio Pro History (post-commit + post-rewrite) -------------------------
# Both hooks find Python through bin/_common.sh's resolve_py (executes each candidate, skips the
# Windows Store alias stub). No Python, or no _common.sh: one warning, the commit stands.
for h in post-commit post-rewrite; do
  HF="$HOOKS/$h"
  if [ -f "$HF" ] && ! grep -q "^$NOTE_MARK" "$HF"; then
    mv "$HF" "$HF.pre-mxtk"
    echo "  existing $h hook kept as $h.pre-mxtk and chained first"
  fi
  if [ "$h" = post-commit ]; then
    RUN='MXTK_HOOK=1 $py "$note" write HEAD || true'
    CHAIN='[ -x "$(dirname "$0")/post-commit.pre-mxtk" ] && "$(dirname "$0")/post-commit.pre-mxtk"'
  else
    # stdin: "<old> <new> [extra]" per rewritten commit (amend, rebase). Read it once, feed both.
    RUN='printf "%s\n" "$input" | while read -r _old new _rest; do [ -n "$new" ] && MXTK_HOOK=1 $py "$note" write "$new"; done || true'
    CHAIN='[ -x "$(dirname "$0")/post-rewrite.pre-mxtk" ] && printf "%s\n" "$input" | "$(dirname "$0")/post-rewrite.pre-mxtk" "$@"'
  fi
  cat > "$HF" <<HOOKEOF
#!/usr/bin/env bash
$NOTE_MARK — written by bin/install-project-hooks.sh (mxcli-project-toolkit). Re-run it to refresh.
# Writes the Studio Pro revision note (refs/notes/mx_metadata, with ModelChanges) for model commits.
# Never fails the git operation: every problem is one warning on stderr.
$( [ "$h" = post-rewrite ] && echo 'input="$(cat)"' )
$CHAIN
note="\$(git rev-parse --show-toplevel)/$BIN_REL/mx-metadata-note.py"
[ -f "\$note" ] || exit 0
py=""
[ -f "\$(dirname "\$note")/_common.sh" ] && py="\$(PROJECT_ROOT="\$(dirname "\$(dirname "\$note")")" bash -c '. "\$1/_common.sh" >/dev/null 2>&1 && resolve_py' _ "\$(dirname "\$note")" 2>/dev/null)"
[ -z "\$py" ] && { echo "⚠ no python found — Studio Pro History will show 'Model changes 0' for this commit (bin/mx-metadata-note.py backfill fixes it later)" >&2; exit 0; }  # portability-ok: resolve_py above is the probe
$RUN
exit 0
HOOKEOF
  chmod +x "$HF"
done
echo "  ✓ post-commit + post-rewrite revision-note hooks installed (Studio Pro History lists each commit's changed documents)"

for r in $(ts_remotes | sort -u); do
  if git config --get-all "remote.$r.push" 2>/dev/null | grep -q 'refs/notes/mx_metadata'; then
    echo "  ✓ $r already pushes refs/notes/mx_metadata"
    continue
  fi
  # Once remote.<r>.push is set it REPLACES git's default, so keep the default (current branch)
  # explicitly. An existing push config is extended, never replaced.
  git config --get-all "remote.$r.push" >/dev/null 2>&1 || git config --add "remote.$r.push" HEAD
  git config --add "remote.$r.push" "refs/notes/mx_metadata:refs/notes/mx_metadata"
  echo "  ✓ $r: 'git push $r' now carries refs/notes/mx_metadata with the branch"
  echo "    (rejected as non-fast-forward = a colleague's Studio Pro noted commits too: ./bin/mx-metadata-note.py sync $r)"
done
