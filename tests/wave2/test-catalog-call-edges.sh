#!/usr/bin/env bash
# Usage: bash test-catalog-call-edges.sh [path-to-graph-sweep.sh]
#
# Fixture for the catalog guard in project-bin/graph-sweep.sh and project-bin/app-facts.sh
# (app-facts.sh is taken from beside the subject).
#
# The defect (issue #259, field report 2026-10-11, mxcli v0.24.0, Mendix 11.14.0): both scripts
# refused any catalog whose catalog_meta.build_mode was not the literal 'full'. mxcli v0.24.0
# writes 'source' even after `REFRESH CATALOG FULL`, on a catalog holding 5,368 typed refs rows,
# so every sweep on that mxcli ended in (verbatim from the report — the golden input):
#   FAULT: catalog build_mode is 'source'; reference edges require 'full'.
# The fix tests what the scripts read instead of the label: a non-empty refs table with at
# least one RefKind='call' edge.
#
# Cases, each on BOTH layouts (single-tree, and two-tree with the .mpr and catalog under app/):
#   1. build_mode 'source' + call edges  -> sweep runs, orphan finding still correct
#   2. build_mode 'full'   + zero call edges -> FAULT naming the mode and the per-kind counts
#   3. build_mode 'fast'   + empty refs  -> FAULT (graph is empty), as before
#   4. app-facts: 'source' + calls passes the guard; zero calls FAULTs naming mode and counts
#
# The catalog databases are SYNTHETIC: no real catalog.db is captured in this repo, and the
# report quotes only the FAULT line and the counts. Tables and columns are exactly the ones the
# two scripts query (catalog_meta key/value, refs SourceName/TargetName/RefKind, objects,
# microflows_data, and app-facts' nine required tables); RefKind values 'call' and 'action' are
# the ones the scripts' own queries name. The mxcli used by app-facts is a stub that copies a
# prepared catalog into place — no real mxcli runs.

set -uo pipefail

SUT="${1:-}"
[ -z "$SUT" ] && SUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/project-bin/graph-sweep.sh"
if [ ! -f "$SUT" ]; then
  echo "SKIP: subject not found at $SUT"
  echo "SCORE: 0/0 — nothing to test"
  exit 0
fi
SUT="$(cd "$(dirname "$SUT")" && pwd)/$(basename "$SUT")"
AF="$(dirname "$SUT")/app-facts.sh"
command -v sqlite3 >/dev/null || { echo "SKIP: sqlite3 not on PATH"; echo "SCORE: 0/0"; exit 0; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   — $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL — $1"; [ -n "${2:-}" ] && echo "         got: $2"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/catalog-calls.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# mkdb <db> <build_mode> <with-calls:1|0> <with-refs:1|0>
mkdb() {
  local db="$1" mode="$2" calls="$3" refs="$4"
  mkdir -p "$(dirname "$db")"; rm -f "$db"
  {
    echo "CREATE TABLE catalog_meta (key TEXT, value TEXT);"
    echo "INSERT INTO catalog_meta VALUES ('mpr_mod_time','2026-10-10T12:00:00.000');"
    echo "INSERT INTO catalog_meta VALUES ('build_mode','$mode');"
    echo "CREATE TABLE refs (SourceType TEXT, SourceName TEXT, TargetName TEXT, RefKind TEXT, ModuleName TEXT);"
    echo "CREATE TABLE objects (QualifiedName TEXT, ModuleName TEXT, ObjectType TEXT);"
    echo "CREATE TABLE microflows_data (QualifiedName TEXT, ModuleName TEXT, Name TEXT, ActivityCount INTEGER, MicroflowType TEXT);"
    echo "CREATE TABLE modules_data (Name TEXT, Source TEXT, AppStoreVersion TEXT, AppStoreGuid TEXT);"
    echo "CREATE TABLE entities_data (QualifiedName TEXT, ModuleName TEXT, EntityType TEXT);"
    echo "CREATE TABLE activities_data (MicroflowQualifiedName TEXT, ModuleName TEXT, ActivityType TEXT);"
    echo "CREATE TABLE pages_data (QualifiedName TEXT, ModuleName TEXT);"
    echo "CREATE TABLE scheduled_events_data (QualifiedName TEXT, ModuleName TEXT);"
    echo "CREATE TABLE projects (Name TEXT);"
    echo "INSERT INTO modules_data VALUES ('Orders','', '', ''),('Billing','', '', '');"
    echo "INSERT INTO activities_data VALUES ('Orders.SUB_Total','Orders','ActionActivity');"
    for m in Orders.ACT_Save Orders.SUB_Total Orders.SUB_Unused Billing.ACT_Send; do
      echo "INSERT INTO objects VALUES ('$m','${m%%.*}','MICROFLOW');"
      echo "INSERT INTO microflows_data VALUES ('$m','${m%%.*}','${m#*.}',3,'MICROFLOW');"
    done
    if [ "$refs" = 1 ]; then
      echo "INSERT INTO refs VALUES ('PAGE','Orders.Order_Edit','Orders.ACT_Save','action','Orders');"
      echo "INSERT INTO refs VALUES ('MICROFLOW','Billing.ACT_Send','Orders.ACT_Save','action','Billing');"
      [ "$calls" = 1 ] && echo "INSERT INTO refs VALUES ('MICROFLOW','Orders.ACT_Save','Orders.SUB_Total','call','Orders');"
    fi
  } | sqlite3 "$db"
}

# proj <layout:single|two> -> prints project dir; .mpr mtime pinned to match catalog_meta
proj() {
  local p="$WORK/$1-$RANDOM" mdir
  mkdir -p "$p"
  if [ "$1" = two ]; then mdir="$p/app"; else mdir="$p"; fi
  mkdir -p "$mdir"
  : > "$mdir/Shop.mpr"
  touch -t 202610101200.00 "$mdir/Shop.mpr"
  printf '%s\n' "$p"
}
mdir() { if [ -d "$1/app" ]; then printf '%s/app\n' "$1"; else printf '%s\n' "$1"; fi; }
sweep() { ( cd "$1" && PROJECT_ROOT="$1" bash "$SUT" --min-elements 1 ) > "$WORK/out" 2>&1; echo $?; }
out() { tr '\n' ' ' < "$WORK/out" | cut -c1-400; }

for layout in single two; do
  echo "== graph-sweep · $layout-tree layout"

  # --- 1. 'source' with call edges: the field case --------------------------------------------
  P="$(proj $layout)"; mkdb "$(mdir "$P")/.mxcli/catalog.db" source 1 1
  rc="$(sweep "$P")"
  if grep -q "FAULT: catalog build_mode is 'source'; reference edges require 'full'." "$WORK/out"; then
    bad "[$layout] build_mode 'source' refused by label (issue #259 golden FAULT line)" "rc=$rc $(out)"
  elif [ "$rc" = 0 ] && grep -q "graph-sweep ·" "$WORK/out"; then
    ok "[$layout] build_mode 'source' with call edges is swept (rc 0)"
  else
    bad "[$layout] 'source' catalog with call edges did not sweep" "rc=$rc $(out)"
  fi
  if grep -q "Orders.SUB_Unused" "$WORK/out" && ! grep -q "Orders.SUB_Total " "$WORK/out"; then
    ok "[$layout] orphan finding still reads call edges (SUB_Unused listed, called SUB_Total not)"
  else
    bad "[$layout] orphan finding wrong on a 'source' catalog" "$(out)"
  fi

  # --- 2. 'full' label but zero call edges: the label is not evidence --------------------------
  P="$(proj $layout)"; mkdb "$(mdir "$P")/.mxcli/catalog.db" full 0 1
  rc="$(sweep "$P")"
  if [ "$rc" = 2 ] && grep -q "0 'call' edges" "$WORK/out" && grep -q "build_mode 'full'" "$WORK/out" \
     && grep -q "action=2" "$WORK/out"; then
    ok "[$layout] zero call edges FAULTs, naming the mode and per-kind counts (action=2)"
  else
    bad "[$layout] a catalog with no call edges was not refused by what it holds" "rc=$rc $(out)"
  fi

  # --- 3. empty refs still FAULTs ---------------------------------------------------------------
  P="$(proj $layout)"; mkdb "$(mdir "$P")/.mxcli/catalog.db" fast 0 0
  rc="$(sweep "$P")"
  if [ "$rc" = 2 ] && grep -q "^FAULT:" "$WORK/out"; then
    ok "[$layout] empty refs still FAULTs (never a clean sweep)"
  else
    bad "[$layout] empty refs not refused" "rc=$rc $(out)"
  fi

  # --- 4. app-facts: same guard, through a stub mxcli that drops a prepared catalog -------------
  if [ -f "$AF" ]; then
    for variant in source-calls full-nocalls; do
      P="$(proj $layout)"; M="$(mdir "$P")"
      case "$variant" in
        source-calls) mkdb "$WORK/prep.db" source 1 1 ;;
        full-nocalls) mkdb "$WORK/prep.db" full 0 1 ;;
      esac
      cat > "$WORK/mxcli-stub" <<EOF
#!/usr/bin/env bash
[ "\${1:-}" = --version ] && { echo "mxcli stub"; exit 0; }
o=""; while [ \$# -gt 0 ]; do [ "\$1" = -o ] && o="\$2"; shift; done
mkdir -p .mxcli && cp "$WORK/prep.db" .mxcli/catalog.db && echo '{}' > "\$o"
EOF
      chmod +x "$WORK/mxcli-stub"
      ( cd "$P" && PROJECT_ROOT="$P" MXCLI="$WORK/mxcli-stub" bash "$AF" --skip-loops --facts-dir "$P/facts" ) > "$WORK/out" 2>&1
      rc=$?
      case "$variant" in
        source-calls)
          if grep -q "catalog ok: build_mode=source" "$WORK/out" && ! grep -q "build_mode is 'source'" "$WORK/out"; then
            ok "[$layout] app-facts accepts a 'source' catalog with call edges"
          else
            bad "[$layout] app-facts refused a 'source' catalog with call edges" "rc=$rc $(out)"
          fi ;;
        full-nocalls)
          if [ "$rc" = 2 ] && grep -q "0 'call' edges" "$WORK/out" && grep -q "build_mode 'full'" "$WORK/out"; then
            ok "[$layout] app-facts FAULTs on zero call edges, naming the mode"
          else
            bad "[$layout] app-facts wrote facts from a catalog with no call edges" "rc=$rc $(out)"
          fi ;;
      esac
    done
  else
    bad "app-facts.sh not beside $SUT"
  fi
done

echo ""
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
