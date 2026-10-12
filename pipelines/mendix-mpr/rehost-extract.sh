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
  for t in entities associations enumerations microflows nanoflows pages snippets javaactions; do
    mx -p "$SRC" show "$t" "$M" | grep -v '^Connected to' > "$OUT/captures/show-$t-$M.txt"
  done
done

# ---- 2. extract -------------------------------------------------------------------------------
# describe_module <mpr> <Module> <out.mdl>: `describe module … with all` plus every describable
# document of the module that the whole-module emitter omits, described one by one from the
# project tree. On 0.26.0 `with all` omits image collections (increment 1) and, on the GenAI
# Showcase (increment 2), nanoflows, snippets, JavaScript actions, JSON structures, import/export
# mappings, task queues, scheduled events and some pages. Used for the source and, in step 4, for
# the target, so both sides carry the same document set.
describe_module() {
  local mpr="$1" M="$2" out="$3"
  "$MXCLI" -p "$mpr" -c "describe module $M with all" 2>/dev/null | grep -v 'vibe-coded PoC' > "$out"
  # 0.26.0 cuts `-c` output at 10 000 lines without saying so (AgentCommons and ConversationalUI on the
  # GenAI Showcase both ended mid-page at line 10 001). Keep only complete statements; the tree fill-in
  # below then describes every document the cut swallowed, one by one.
  "$PY" -I - "$out" "$HERE/lib" <<'PYEOF' >&2
import sys; sys.path.insert(0, sys.argv[2])
from mdlsplit import split_statements
text = open(sys.argv[1], encoding='utf-8', newline='').read()
stmts, tail = split_statements(text)
if tail.strip():
    open(sys.argv[1], 'w', encoding='utf-8', newline='').write('\n'.join(stmts) + '\n')
    print('describe module truncated at %d lines (incomplete last statement dropped: %s)' % (text.count('\n'), tail.strip().split('\n')[0][:80]))
PYEOF
  "$MXCLI" -p "$mpr" project-tree --json 2>/dev/null > "$out.tree.json"
  "$PY" -I - "$M" "$out" "$out.tree.json" <<'PYEOF' | while read -r t q; do
import json,re,sys
M, out, tree = sys.argv[1], sys.argv[2], sys.argv[3]
have = set(re.findall(r'^create or modify [a-z -]+? (' + re.escape(M) + r'\.[A-Za-z0-9_]+)', open(out, encoding='utf-8', newline='').read(), re.M))
def walk(n):
    for x in n:
        q = x.get('qualifiedName', '')
        if x.get('describable') and q.startswith(M + '.') and q not in have and x.get('type') not in ('modulerole',):
            print(x['type'], q)
        walk(x.get('children', []))
walk(json.load(open(tree)))
PYEOF
    "$MXCLI" -p "$mpr" describe "$t" "$q" 2>/dev/null | grep -v 'vibe-coded PoC' | sed '1{/^mdl 1;$/d}' >> "$out"
  done
  rm -f "$out.tree.json"
}
now() { date +%s.%N; }
TIMES="$OUT/captures/timings.tsv"
printf 'module\tdescribe_s\ttopo_s\tcheck_s\texec_s\tdescribe_target_s\n' > "$TIMES"
declare -A T_DESC T_TOPO T_CHECK T_EXEC T_TDESC
for M in "${MODULES[@]}"; do
  t0=$(now); describe_module "$SRC" "$M" "$OUT/mdl/$M.mdl"; t1=$(now)
  "$PY" -I "$HERE/lib/topo-order-mdl.py" "$OUT/mdl/$M.mdl" "$OUT/mdl/$M.ordered.mdl" 2>>"$OUT/captures/describe-$M.stderr"
  T_DESC[$M]=$(echo "$t1-$t0" | bc); T_TOPO[$M]=$(echo "$(now)-$t1" | bc)
done
# module order: replay the modules so that each is created after every listed module it references
# (qualified-name mention in its describe output); REHOST_KEEP_ORDER=1 keeps the order given. A cycle
# between modules is reported and left in the given order — exec then fails on the forward reference
# and the ledger says so.
if [ "${REHOST_KEEP_ORDER:-0}" = 0 ]; then
  mapfile -t MODULES < <("$PY" -I - "$OUT/mdl" "${MODULES[@]}" <<'PYEOF'
import re,sys
d, mods = sys.argv[1], sys.argv[2:]
body = {m: open('%s/%s.mdl' % (d, m), encoding='utf-8', newline='').read() for m in mods}
deps = {m: {o for o in mods if o != m and re.search(r'\b' + re.escape(o) + r'\.[A-Za-z0-9_]', body[m])} for m in mods}
order, placed, rest = [], set(), list(mods)
while rest:
    ready = [m for m in rest if deps[m] <= placed]
    if not ready:
        sys.stderr.write('module cycle among: %s (left in catalog order)\n' % ', '.join(rest)); order += rest; break
    for m in ready: order.append(m); placed.add(m); rest.remove(m)
print('\n'.join(order))
PYEOF
  )
  log "replay order: ${MODULES[*]}"
fi
"$MXCLI" -p "$SRC" describe settings Settings 2>/dev/null | grep -v 'vibe-coded PoC' > "$OUT/mdl/_settings.mdl"
mx -p "$SRC" -c "show user roles" > "$OUT/captures/show-userroles.txt"
: > "$OUT/mdl/_userroles.mdl"
awk -F'|' 'NR>3 && NF>3 { gsub(/ /,"",$2); if ($2!="") print $2 }' "$OUT/captures/show-userroles.txt" | while read -r r; do
  "$MXCLI" -p "$SRC" describe userrole "$r" 2>/dev/null | grep -v 'vibe-coded PoC' >> "$OUT/mdl/_userroles.mdl"
done

# ---- 3. check, then exec into the target (modules in replay order) ---------------------------
status=0
for M in "${MODULES[@]}"; do
  t0=$(now)
  if mx check -p "$TGT" "$OUT/mdl/$M.ordered.mdl" > "$OUT/captures/check-$M.txt"; then
    T_CHECK[$M]=$(echo "$(now)-$t0" | bc); t0=$(now)
    mx exec -p "$TGT" "$OUT/mdl/$M.ordered.mdl" > "$OUT/captures/exec-$M.txt" || { log "exec $M FAILED — see captures/exec-$M.txt"; status=1; }
    T_EXEC[$M]=$(echo "$(now)-$t0" | bc)
  else
    T_CHECK[$M]=$(echo "$(now)-$t0" | bc); T_EXEC[$M]=skipped
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
  t0=$(now); describe_module "$TGT" "$M" "$OUT/mdl/target-$M.mdl"; T_TDESC[$M]=$(echo "$(now)-$t0" | bc)
  "$PY" -I "$HERE/lib/compare-mdl.py" "$OUT/mdl/$M.mdl" "$OUT/mdl/target-$M.mdl" "$M" 2>/dev/null >> "$OUT/fidelity-ledger.tsv"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$M" "${T_DESC[$M]:-}" "${T_TOPO[$M]:-}" "${T_CHECK[$M]:-}" "${T_EXEC[$M]:-}" "${T_TDESC[$M]:-}" >> "$TIMES"
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
