#!/usr/bin/env python3
"""Increment 8: legacy widgets -> React-client widgets (CE0582 on Mendix 11), generalised from increment 5's
slice-assets/tools/legacy-extract.py + gen-widgets.py (whose microflow/page signature tables were hand-written
for Assets). Signatures here come from `describe` on the target app.

usage: MXCLI=<mxcli> APP=<target.mpr> react-widgets.py <bson-dir> > edges-C-widgets.mdl
<bson-dir> holds `mxcli bson dump --type page|snippet --object <Doc>` output as <Doc>.json.
Converts: DataGrid -> datagrid (Data grid 2), ReferenceSelector -> combobox on the association,
DropDown -> combobox on the enum attribute, ReferenceSetSelector / InputReferenceSetSelector -> combobox on
the reference set. Everything it cannot carry is listed as DRIFT at the end (a hand-off, not a resolution)."""
import json, os, re, subprocess, sys, glob, collections
M = os.environ["MXCLI"]; APP = os.environ["APP"]; BD = sys.argv[1]
LEGACY = ("Forms$DataGrid", "Forms$ReferenceSelector", "Forms$ReferenceSetSelector",
          "Forms$InputReferenceSetSelector", "Forms$DropDown")
_cache = {}
def desc(kind, name):
    k = (kind, name)
    if k not in _cache:
        _cache[k] = subprocess.run([M, "-p", APP, "-c", f"describe {kind} {name}"], capture_output=True, text=True).stdout
    return _cache[k]
def params_of(kind, name):
    d = desc(kind, name)
    m = re.search(r"Params: \(\s*(\$.*?)\s*\)", d)
    if kind in ("page", "snippet"):
        return [(v, t) for v, t in re.findall(r"\$(\w+): ([\w.]+)", m.group(1))] if m else []
    head = d.split("\nbegin")[0]
    return [(v, t.strip()) for v, t in re.findall(r"\$(\w+): ((?:List of )?[\w.]+)", head)]
def kv(o):
    if isinstance(o, list):
        if o and all(isinstance(x, dict) and set(x) == {"Key", "Value"} for x in o):
            return {x["Key"]: kv(x["Value"]) for x in o}
        return [kv(x) for x in o if not isinstance(x, int)]
    return o
def txt(t):
    if not isinstance(t, dict): return ""
    for it in t.get("Items", []) or []:
        if isinstance(it, dict) and it.get("LanguageCode") == "en_US": return it.get("Text", "")
    return ""
def q(s): return "'" + (s or "").replace("'", "''") + "'"
def steps(er): return [(s.get("Association"), s.get("DestinationEntity")) for s in ((er or {}).get("Steps") or []) if isinstance(s, dict)]
drift = []; by = collections.OrderedDict()
def label(o):
    lt = o.get("LabelTemplate")
    return txt(lt.get("Template")) if isinstance(lt, dict) else ""
def grid(o, doc, ctx):
    g = o.get("Name"); d = o.get("DataSource") or {}
    er = d.get("EntityRef") or {}
    ent = er.get("Entity"); st = steps(er)
    cvar = "$" + ctx[0][0] if ctx else None
    if st:
        ent = st[-1][1]; src = f"DATABASE {ent} WHERE [{st[0][0]} = {cvar}]"
        drift.append(f"{doc}/{g}: association source written as DATABASE {ent} WHERE [{st[0][0]} = {cvar}]")
    elif d.get("$Type") == "Forms$MicroflowSource" or (d.get("MicroflowSettings") or {}).get("Microflow"):
        mf = (d.get("MicroflowSettings") or {}).get("Microflow")
        ret = re.search(r"^returns\s+List of ([\w.]+)", desc("microflow", mf), re.M)
        if not ret:
            drift.append(f"{doc}/{g}: microflow source {mf} with no list return: grid replaced by a text"); return f"    dynamictext {g} (Content: 'HAND-OFF: legacy grid over {mf}')"
        ent = ret.group(1); args = []
        for pn, pt in params_of("microflow", mf):
            v = next(("$" + a for a, t in ctx if t == pt), None)
            args.append(f"{pn} = {v or 'empty'}")
        src = f"MICROFLOW {mf}({', '.join(args)})"
    else:
        xp = (d.get("XPathConstraint") or "").replace("\n", " ")
        if "[%CurrentObject%]" in xp:
            xp = xp.replace("'[%CurrentObject%]'", cvar or "empty")
        src = f"DATABASE {ent}" + (f" WHERE {xp}" if xp.strip() else "")
        sort = [((s.get("AttributeRef") or {}).get("Attribute"), s.get("SortOrder")) for s in ((d.get("SortBar") or {}).get("SortItems") or []) if isinstance(s, dict)]
        ok = [(a.split(".")[-1], so) for a, so in sort if a and a.rsplit(".", 1)[0] == ent]
        if ok: src += " SORT BY " + ", ".join(f"{a} {'ASC' if so == 'Ascending' else 'DESC'}" for a, so in ok)
        if len(ok) != len(sort): drift.append(f"{doc}/{g}: sort over an association dropped")
    sel = o.get("SelectionMode")
    L = [f"    datagrid {g} (DataSource: {src}, Selection: {sel if sel in ('Single', 'Multi') else 'None'}) {{"]
    for c in o.get("Columns", []):
        if not isinstance(c, dict): continue
        ar = c.get("AttributeRef") if isinstance(c.get("AttributeRef"), dict) else {}
        a = ar.get("Attribute")
        if not a: continue
        cs = steps(ar.get("EntityRef"))
        path = "/".join(x[0].split(".")[1] for x in cs) + "/" + a.split(".")[-1] if cs else a.split(".")[-1]
        L.append(f"      column (Attribute: {path}, Caption: {q(txt(c.get('Caption')) or a.split('.')[-1])})")
    row, bar = [], []
    cb = o.get("ControlBar") or {}
    for b in (cb.get("NewButtons") or []) if isinstance(cb, dict) else []:
        if not isinstance(b, dict): continue
        bt = b.get("$Type", "").split("$")[-1]; name = b.get("Name")
        cap = txt((b.get("CaptionTemplate") or {}).get("Template")) or name
        a = b.get("Action") if isinstance(b.get("Action"), dict) else {}
        at = a.get("$Type", "").split("$")[-1]
        if bt in ("GridSearchButton", "DataGridSelectButton", "GridDeleteButton", "GridExportToExcelButton", "GridExportToCSVButton"):
            drift.append(f"{doc}/{g}: legacy {bt} {name} has no Data grid 2 equivalent — dropped"); continue
        if bt == "GridNewButton":
            pg = ((b.get("PageSettings") or {}).get("Page")) or (((a.get("PageSettings") or a.get("FormSettings") or {}).get("Form")))
            drift.append(f"{doc}/{g}: New button {name} (page {pg}) dropped — needs a create-object action"); continue
        mf = (a.get("MicroflowSettings") or {}).get("Microflow")
        pg = (a.get("FormSettings") or a.get("PageSettings") or {}).get("Form") or (a.get("FormSettings") or a.get("PageSettings") or {}).get("Page")
        if mf:
            args, kind = [], "bar"
            for pn, pt in params_of("microflow", mf):
                if pt == ent: args.append(f"{pn} = $currentObject"); kind = "row"
                elif pt == f"List of {ent}": args.append(f"{pn} = ${g}")
                else:
                    v = next(("$" + x for x, t in ctx if t == pt), None)
                    args.append(f"{pn} = {v or 'empty'}")
            btn = f"actionbutton {name} (Caption: {q(cap)}, Action: CALL MICROFLOW {mf}({', '.join(args)}))"
            (row if kind == "row" else bar).append(btn)
        elif pg:
            pp = params_of("page", pg)
            if pp and pp[0][1] == ent:
                row.append(f"actionbutton {name} (Caption: {q(cap)}, Action: SHOW PAGE {pg}({pp[0][0]} = $currentObject))")
            elif not pp:
                bar.append(f"actionbutton {name} (Caption: {q(cap)}, Action: SHOW PAGE {pg})")
            else:
                drift.append(f"{doc}/{g}: button {name} -> page {pg} with parameter {pp} not mappable — dropped")
        else:
            drift.append(f"{doc}/{g}: button {name} ({bt}/{at}) dropped")
    if row:
        L.append("      column (Caption: ' ') {"); L += ["        " + x for x in row]; L.append("      }")
    if any(f"= ${g}" in b for b in bar) and "Selection: None" in L[0]:
        L[0] = L[0].replace("Selection: None", "Selection: Multi")  # a list-parameter button needs the grid's selection
        drift.append(f"{doc}/{g}: selection set to Multi for list-parameter buttons")
    if bar:
        L.append("      controlbar {"); L += ["        " + x for x in bar]; L.append("      }")
    L.append("    }")
    return "\n".join(L)
def combo(o, doc, ctx, t):
    w = o.get("Name") or ("dd_" + str(len(drift)))
    ar = o.get("AttributeRef") or {}
    a = ar.get("Attribute") or ""
    st = steps(ar.get("EntityRef"))
    if t == "Forms$DropDown":
        cb = f"combobox {w} (Label: {q(label(o))}, Attribute: {a.split('.')[-1]})"
        if doc.split(".")[1].startswith("Snippet_") and ctx:
            drift.append(f"{doc}/{w}: drop-down wrapped in a data view on ${ctx[0][0]} (no data container in scope otherwise)")
            return w, f"    dataview dv_{w} (DataSource: ${ctx[0][0]}) {{\n      {cb}\n    }}"
        return w, "    " + cb
    if t == "Forms$InputReferenceSetSelector" or not st:
        assoc = (o.get("Association") or (st[0][0] if st else None))
        drift.append(f"{doc}/{w}: {t.split('$')[1]} over {assoc or a} replaced by a text — no combo box mapping verified")
        return w, f"    dynamictext {w} (Content: 'HAND-OFF: {t.split('$')[1]}')"
    if (o.get("SelectorSource") or {}).get("$Type", "").endswith("MicroflowSource"):
        drift.append(f"{doc}/{w}: selectable-objects microflow not carried (combo box lists all {st[0][1]})")
    if (o.get("SelectorSource") or {}).get("XPathConstraint"):
        drift.append(f"{doc}/{w}: selectable-objects XPath dropped")
    cb = f"combobox {w} (Label: {q(label(o))}, Association: {st[0][0]}, DataSource: database {st[0][1]}, CaptionAttribute: {a.split('.')[-1]})"
    if doc.split(".")[1].startswith("Snippet_") and ctx:
        drift.append(f"{doc}/{w}: combo box wrapped in a data view on ${ctx[0][0]} (CE7007 otherwise)")
        return w, f"    dataview dv_{w} (DataSource: ${ctx[0][0]}) {{\n      {cb}\n    }}"
    return w, "    " + cb
def walk(o, doc, kind, ctx, out):
    if isinstance(o, dict):
        t = o.get("$Type")
        if t == "Forms$Table" and any(f'"{x}"' in json.dumps(o) for x in LEGACY):
            # mxcli cannot see inside a legacy layout table (describe prints it as a comment; `replace <inner>`
            # answers "widget not found"), so the whole table is replaced by its converted legacy widgets
            inner = []
            walk(o.get("Cells") or o.get("Rows") or [], doc, kind, ctx, inner)
            drift.append(f"{doc}/{o.get('Name')}: legacy table replaced by a container holding its {len(inner)} converted widget(s); other table content dropped")
            body = "\n".join(b for _, b in inner).replace("\n", "\n  ")
            out.append((o.get("Name"), f"    container {o.get('Name')} {{\n  {body}\n    }}")); return
        if t == "Forms$DataGrid":
            out.append((o.get("Name"), grid(o, doc, ctx))); return
        if t in LEGACY:
            out.append(combo(o, doc, ctx, t)); return
        for v in o.values(): walk(v, doc, kind, ctx, out)
    elif isinstance(o, list):
        for v in o: walk(v, doc, kind, ctx, out)
o = ["mdl 1;", "-- Legacy widgets -> React client (CE0582), generated by tools/react-widgets.py from bson dumps; DRIFT at the end."]
for f in sorted(glob.glob(os.path.join(BD, "*.json"))):
    doc = os.path.basename(f)[:-5]
    raw = open(f).read()
    if not any(f'"{t}"' in raw for t in LEGACY): continue
    kind = "snippet" if ".Snippet_" in doc else "page"
    ctx = params_of(kind, doc)
    out = []
    walk(kv(json.loads(raw)), doc, kind, ctx, out)
    if not out: continue
    o.append(f"alter {kind} {doc} {{")
    for name, body in out:
        if not name: drift.append(f"{doc}: unnamed legacy widget skipped"); continue
        o.append(f"  replace {name} with {{\n{body}\n  }};")
    o.append("};")
o.append("-- DRIFT:\n" + "\n".join("--   " + d for d in drift))
print("\n".join(o))
print(f"-- {len(drift)} drift lines", file=sys.stderr)
