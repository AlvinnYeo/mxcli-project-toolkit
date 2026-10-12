#!/usr/bin/env bash
# rehost-extract.sh — read an existing Mendix .mpr, emit each own module as MDL, replay it into a
# fresh target .mpr of the same Mendix version, and write the fidelity ledger.
#
#   pipelines/mendix-mpr/rehost-extract.sh <source.mpr> <target.mpr> <out-dir> [Module ...]
#
#   <out-dir>/captures/   verbatim mxcli output (golden fixtures: list modules, show <type> <Module>,
#                         project-tree.json, check/exec logs)
#   <out-dir>/mdl/        <Module>.mdl (source describe), <Module>.ordered.mdl (what was executed),
#                         target-<Module>.mdl (describe of the target afterwards), _settings/_userroles
#   <out-dir>/fidelity-ledger.tsv   one row per source document (denominator in the header)
#
# Modules default to every module `list modules` shows with an empty Source column except System.
# The target must already exist (`mxcli new <App> --version <same> --theme none`); this script
# creates nothing but model content. It does NOT run the build gate — run project-bin/exec.sh's
# mxbuild gate or `~/.mxcli/mxbuild/<ver>/modeler/mx check <target.mpr>` afterwards.
#
# Field run (2026-10-12, mxcli v0.26.0, Linux container): ako/mxcli-banking RRNetBanking.mpr
# (Mendix 11.13.0, modules Banking 151 documents + MyFirstModule 4) -> `mxcli new --version 11.13.0`.
# 155/155 catalog documents emitted, 154 identical on target describe, 1 documentation drift,
# `mx check` and `mxbuild --target=deploy` clean. Everything in here was exercised on that run:
#   - the whole-module emitter is the MDL statement `describe module <M> with all` run through -c;
#     the `mxcli describe module <M>` SUBCOMMAND emits only the module and its roles (0.26.0).
#   - describe emits microflows in catalog order, so `check` reported 14 MDL-ORDER01 (callee
#     created after caller) and exec refused the file; lib/topo-order-mdl.py reorders flow units
#     (create + its grant execute statements) and the reordered file checked clean.
#   - `describe module … with all` omits image collections (MyFirstModule.Images) — described
#     separately below so the ledger has the row.
#   - demo users describe with Password: '***' and exec refuses the placeholder; project security
#     level describes as a report, not MDL. Both are ledger hand-off rows, never executed here.
# Not exercised: nanoflows, Java/JavaScript actions, snippets, workflows, REST/OData, marketplace
# install (the blank template already carried the source's seven modules at the same versions).
set -euo pipefail

SRC="${1:?usage: rehost-extract.sh <source.mpr> <target.mpr> <out-dir> [Module ...]}"
TGT="${2:?target.mpr}"
OUT="${3:?out-dir}"
shift 3
HERE="$(cd "$(dirname "$0")" && pwd)"
MXCLI="${MXCLI:-$(command -v mxcli || true)}"
[ -x "$MXCLI" ] || { echo "mxcli not found: set MXCLI=/path/to/mxcli" >&2; exit 2; }
PY="${PYTHON:-python3}"
mkdir -p "$OUT/captures" "$OUT/mdl"
mx() { "$MXCLI" "$@" 2>&1 | grep -v 'vibe-coded PoC'; }   # one warning line per call, drop it
log() { printf '%s\n' "$*" >&2; }

# ---- 1. inventory (golden captures) ---------------------------------------------------------
mx -p "$SRC" list modules > "$OUT/captures/list-modules.txt"
"$MXCLI" -p "$SRC" project-tree --json 2>/dev/null > "$OUT/captures/project-tree.json"
if [ $# -eq 0 ]; then
  # own module = empty Source column, not System
  mapfile -t MODULES < <(awk -F'|' 'NR>3 && NF>3 { gsub(/ /,"",$2); gsub(/ /,"",$3); if ($3=="" && $2!="System" && $2!="") print $2 }' "$OUT/captures/list-modules.txt")
else
  MODULES=("$@")
fi
log "own modules: ${MODULES[*]}"
for M in "${MODULES[@]}"; do
  for t in entities associations enumerations microflows nanoflows pages snippets; do
    mx -p "$SRC" show "$t" "$M" | grep -v '^Connected to' > "$OUT/captures/show-$t-$M.txt"
  done
done

# ---- 2. extract -------------------------------------------------------------------------------
# describe_module <mpr> <Module> <out.mdl>: `describe module … with all` plus the image collections
# it omits (0.26.0), from the project tree. Used for the source and, in step 4, for the target.
describe_module() {
  local mpr="$1" M="$2" out="$3"
  "$MXCLI" -p "$mpr" -c "describe module $M with all" 2>/dev/null | grep -v 'vibe-coded PoC' > "$out"
  "$MXCLI" -p "$mpr" project-tree --json 2>/dev/null | "$PY" -I -c '
import json,sys
def walk(n):
    for x in n:
        if x.get("type")=="imagecollection" and x.get("qualifiedName","").startswith(sys.argv[1]+"."): print(x["qualifiedName"])
        walk(x.get("children",[]))
walk(json.load(sys.stdin))' "$M" | while read -r ic; do
    "$MXCLI" -p "$mpr" describe imagecollection "$ic" 2>/dev/null | grep -v 'vibe-coded PoC' | sed '1{/^mdl 1;$/d}' >> "$out"
  done
}
for M in "${MODULES[@]}"; do
  describe_module "$SRC" "$M" "$OUT/mdl/$M.mdl"
  "$PY" -I "$HERE/lib/topo-order-mdl.py" "$OUT/mdl/$M.mdl" "$OUT/mdl/$M.ordered.mdl" 2>>"$OUT/captures/describe-$M.stderr"
done
"$MXCLI" -p "$SRC" describe settings Settings 2>/dev/null | grep -v 'vibe-coded PoC' > "$OUT/mdl/_settings.mdl"
mx -p "$SRC" -c "show user roles" > "$OUT/captures/show-userroles.txt"
: > "$OUT/mdl/_userroles.mdl"
awk -F'|' 'NR>3 && NF>3 { gsub(/ /,"",$2); if ($2!="") print $2 }' "$OUT/captures/show-userroles.txt" | while read -r r; do
  "$MXCLI" -p "$SRC" describe userrole "$r" 2>/dev/null | grep -v 'vibe-coded PoC' >> "$OUT/mdl/_userroles.mdl"
done

# ---- 3. check, then exec into the target (modules in the order given) ---------------------------
status=0
for M in "${MODULES[@]}"; do
  if mx check -p "$TGT" "$OUT/mdl/$M.ordered.mdl" > "$OUT/captures/check-$M.txt"; then
    mx exec -p "$TGT" "$OUT/mdl/$M.ordered.mdl" > "$OUT/captures/exec-$M.txt" || { log "exec $M FAILED — see captures/exec-$M.txt"; status=1; }
  else
    log "check $M FAILED — see captures/check-$M.txt (nothing executed for $M)"; status=1
  fi
done
mx exec -p "$TGT" "$OUT/mdl/_settings.mdl"  > "$OUT/captures/exec-_settings.txt"  || status=1
mx exec -p "$TGT" "$OUT/mdl/_userroles.mdl" > "$OUT/captures/exec-_userroles.txt" || status=1

# ---- 4. compare and ledger ---------------------------------------------------------------------
{
  echo "# Fidelity ledger — $(basename "$SRC") -> $(basename "$TGT"), $(mx --version | head -1), $(date +%F)"
  echo "# verdicts: emitted-identical | emitted-drift | failed-exec | not-emitted | target-extra | not-expressible (app-level hand-offs)"
  echo "module	document	type	verdict	evidence"
} > "$OUT/fidelity-ledger.tsv"
for M in "${MODULES[@]}"; do
  describe_module "$TGT" "$M" "$OUT/mdl/target-$M.mdl"
  "$PY" -I "$HERE/lib/compare-mdl.py" "$OUT/mdl/$M.mdl" "$OUT/mdl/target-$M.mdl" "$M" 2>/dev/null >> "$OUT/fidelity-ledger.tsv"
done
# app-level rows the model export cannot carry — always hand-off, never silent
printf '(app)\tDemoUsers\tdemouser\tnot-expressible\tdescribe prints Password: '"'"'***'"'"' and exec refuses it — recreate by hand with real passwords (describe demouser <name> for the role/entity)\n' >> "$OUT/fidelity-ledger.tsv"
printf '(app)\tProjectSecurity\tprojectsecurity\tnot-expressible\tdescribe projectsecurity is a report; write `alter app security (SecurityLevel: …)` by hand and drop the blank template'"'"'s user role User + demo users before mx check under Production\n' >> "$OUT/fidelity-ledger.tsv"
printf '(app)\ttheme\ttheme\tnot-expressible\tnot in the model: copy theme/ and themesource/<module>/ by hand\n' >> "$OUT/fidelity-ledger.tsv"
# denominator: describable documents of the own modules in the source tree
"$PY" -I - "$OUT/captures/project-tree.json" "$OUT/fidelity-ledger.tsv" "${MODULES[@]}" <<'PYEOF'
import json,sys
tree=json.load(open(sys.argv[1])); mods=sys.argv[3:]
def walk(n):
    for x in n:
        if x.get('describable') and any(x.get('qualifiedName','').startswith(m+'.') for m in mods): yield x['qualifiedName']
        yield from walk(x.get('children',[]))
cat=set(walk(tree))
rows=[l.split('\t') for l in open(sys.argv[2]) if not l.startswith('#') and not l.startswith('module\t')]
covered={r[1] for r in rows}
missing=sorted(cat-covered)
with open(sys.argv[2],'a') as f:
    for q in missing: f.write('%s\t%s\t?\tnot-emitted\tin source catalog, no describe statement on either side\n'%(q.split('.')[0],q))
    f.write('# denominator: %d describable documents in the source catalog for %s; %d covered by rows, %d listed as not-emitted\n'%(len(cat),','.join(mods),len(cat&covered),len(missing)))
print('catalog=%d covered=%d not-emitted=%d'%(len(cat),len(cat&covered),len(missing)))
PYEOF
log "ledger: $OUT/fidelity-ledger.tsv"
exit $status
