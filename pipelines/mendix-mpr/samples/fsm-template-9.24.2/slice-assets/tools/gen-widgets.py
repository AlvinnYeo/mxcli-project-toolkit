#!/usr/bin/env python3
"""Legacy DataGrid / ReferenceSelector -> Data grid 2 / Combo box (Mendix 11 has only the React client).
Input: legacy-widgets.json (legacy-extract.py over mxcli bson dump). Output: ALTER PAGE/SNIPPET MDL."""
import json, re, glob, collections
W=json.load(open("<lab>/web-assets/legacy-widgets.json"))
params={}
for f in glob.glob("<lab>/web-assets/desc-*.mdl"):
    for m in re.finditer(r"create or modify (page|snippet) ([\w.]+)(.*?)\) \{\n", open(f).read(), re.S):
        params[m.group(2)]=(m.group(1), dict((v,t) for v,t in re.findall(r"\$(\w+): ([\w.]+)", m.group(3).split("Params:")[-1]) if "Params:" in m.group(3)))
MFSIG={  # from describe microflow (AssetsApp): parameter name -> type
 "AssetManagement.ACT_AssetPart_AddNew":[("Asset","AssetManagement.Asset")],
 "AssetManagement.ACT_AssetPart_CreateAndAddToBOM":[("Asset","AssetManagement.Asset"),("Part","Part.Part")],
 "AssetManagement.ACT_AssetPart_Delete":[("AssetPartList_ToDelete","List of Part.AssetPart")],
 "AssetManagement.ACT_AssetPart_ShowPartDetails":[("AssetPartList","List of Part.AssetPart")],
 "AssetManagement.ACT_Asset_CreateRoster":[("Asset","AssetManagement.Asset")],
 "AssetManagement.ACT_Asset_Delete":[("Asset","AssetManagement.Asset")],
 "AssetManagement.ACT_Asset_DeleteRosters":[("Asset","AssetManagement.Asset")],
 "Part.ACT_Part_AssociateSuggestedPart":[("Part","Part.Part"),("SuggestedPart","Part.SuggestedPart")],
 "Part.ACT_Part_Delete":[("Part","Part.Part")],
 "Part.ACT_UnitOfMeasure_Delete":[("UnitOfMeasure","Part.UnitOfMeasure")],
 "Part.ACT_UnitOfMeasure_View":[("UnitOfMeasure","Part.UnitOfMeasure")],
 "RosterManagement.ACT_Roster_Delete":[("Roster","RosterManagement.Roster")],
 "Tool.ACT_Tool_Delete":[("Tool","Tool.Tool")],
 "WarehouseManagement.ACT_Inventory_Delete":[("Inventory","WarehouseManagement.Inventory")],
 "WarehouseManagement.ACT_Inventory_New":[("Warehouse","WarehouseManagement.Warehouse")],
 "WarehouseManagement.ACT_Warehouse_Delete":[("Warehouse","WarehouseManagement.Warehouse")],
}
PAGEPARAM={"AssetManagement.Asset_View":"Asset","CustomerManagement.ContactPerson_View":"ContactPerson","RosterManagement.Roster_NewEdit":"Roster",
 "TicketManagement.Ticket_View":"Ticket","Part.Part_View":"Part","WarehouseManagement.Inventory_View":"Inventory","WarehouseManagement.Warehouse_View":"Warehouse","Tool.Tool_View":"Tool"}
drift=[]
def q(s): return "'"+s.replace("'","''")+"'"
def rowent(w):
    d=w["ds"]
    if d.get("entity"): return d["entity"]
    if d.get("steps"): return d["steps"][-1][1]
    return {"Part.DS_Part_Get_AssetList":"AssetManagement.Asset"}.get(d.get("mf"))
def ctxvar(doc, typ):
    for v,t in params.get(doc,("",{}))[1].items():
        if t==typ: return "$"+v
    return None
def grid(w):
    doc=w["doc"]; ent=rowent(w); d=w["ds"]; g=w["widget"]
    ctx=list(params.get(doc,("",{}))[1].items())
    cvar="$"+ctx[0][0] if ctx else None
    if d.get("steps"):
        assoc=d["steps"][0][0]
        src=f"DATABASE {ent} WHERE [{assoc} = {cvar}]"
        drift.append(f"{doc}/{g}: XPath-over-association source written as DATABASE {ent} WHERE [{assoc} = {cvar}]")
    elif d.get("mf"):
        src=f"DATABASE {ent} WHERE [Part.AssetPart_Asset/Part.AssetPart/Part.AssetPart_Part = {cvar}]"
        drift.append(f"{doc}/{g}: microflow source {d['mf']} (custom Paging object) replaced by the equivalent XPath")
    else:
        xp=(d.get("XPathConstraint") or "").replace("\n","").replace("'[%CurrentObject%]'",cvar or "''")
        src=f"DATABASE {ent}"+(f" WHERE {xp}" if xp else "")
    srt=[(a.split(".")[-1],o) for a,o in d.get("sort",[]) if a and a.rsplit(".",1)[0]==ent]
    if srt: src+=" SORT BY "+", ".join(f"{a} {'ASC' if o=='Ascending' else 'DESC'}" for a,o in srt)
    if len(srt)!=len(d.get("sort",[])): drift.append(f"{doc}/{g}: sort over an association dropped")
    sel=w["selection"]
    L=[f"    datagrid {g} (DataSource: {src}, Selection: {sel if sel in ('Single','Multi') else 'None'}) {{"]
    for attr,cap,steps,fmt in w["cols"]:
        if not attr: continue
        a=attr.split(".")[-1] if not steps else "/".join(s.split(".")[-1] if False else s for s in steps)+"/"+attr.split(".")[-1]
        if steps: a="/".join(s.split(".")[1] for s in steps)+"/"+attr.split(".")[-1]
        L.append(f"      column (Attribute: {a}, Caption: {q(cap or attr.split('.')[-1])})")
    rowbtn=[]; barbtn=[]
    for b in w["buttons"]:
        if b["btype"]=="DataGridSelectButton":
            drift.append(f"{doc}/{g}: legacy Select button has no Data grid 2 equivalent — dropped (select pages are opened by the caller; that caller is monolith-side)"); continue
        if b["atype"]=="FormAction":
            rowbtn.append(f"actionbutton {b['name']} (Caption: {q(b['caption'])}, Action: SHOW PAGE {b['form']}({PAGEPARAM[b['form']]} = $currentObject))")
            continue
        sig=MFSIG[b["mf"]]; args=[]; kind="row"
        for pn,pt in sig:
            if pt==ent: args.append(f"{pn} = $currentObject")
            elif pt==f"List of {ent}": args.append(f"{pn} = ${g}"); kind="bar"
            else:
                cv=ctxvar(doc,pt) or cvar; args.append(f"{pn} = {cv}")
        if all(not a.endswith("$currentObject") for a in args) and kind=="row": kind="bar"
        btn=f"actionbutton {b['name']} (Caption: {q(b['caption'])}, Action: CALL MICROFLOW {b['mf']}({', '.join(args)}))"
        (rowbtn if kind=="row" else barbtn).append(btn)
    if rowbtn:
        L.append("      column (Caption: ' ') {"); L+=["        "+x for x in rowbtn]; L.append("      }")
    if barbtn:
        L.append("      controlbar {"); L+=["        "+x for x in barbtn]; L.append("      }")
    L.append("    }")
    return "\n".join(L)
def refsel(w):
    doc=w["doc"]; ctx=list(params.get(doc,("",{}))[1].items())
    assoc=w["path"][0][0].split(".")[1]
    v="$"+ctx[0][0] if ctx else None
    extra=""
    if w["source"]["mf"]:
        drift.append(f"{doc}/{w['widget']}: selectable objects microflow {w['source']['mf']} not carried (combo box lists all {w['path'][0][1]})")
    cb=f"combobox {w['widget']} (Label: {q(w['label'])}, Association: {w['path'][0][0]}, DataSource: database {w['path'][0][1]}, CaptionAttribute: {w['attr'].split('.')[-1]})"
    if doc.split(".")[1].startswith("Snippet_"):  # bound straight to the snippet parameter: no data container -> CE7007; wrap
        drift.append(f"{doc}/{w['widget']}: combo box wrapped in a data view on {v} (param-bound widget had no entity context)")
        return f"    dataview dv_{w['widget']} (DataSource: {v}) {{\n      {cb}\n    }}"
    return "    "+cb
by=collections.OrderedDict()
for w in W: by.setdefault(w["doc"],[]).append(w)
o=["mdl 1;","-- Legacy Data grid / Reference selector -> Data grid 2 / Combo box: Mendix 11 has only the React client (CE0582).","-- Generated by gen-widgets.py from mxcli bson dump of each page; drift listed at the end."]
for doc,ws in by.items():
    kind=params.get(doc,("page",{}))[0]
    o.append(f"alter {kind} {doc} {{")
    for w in ws:
        body=grid(w) if w["kind"]=="DataGrid" else refsel(w)
        o.append(f"  replace {w['widget']} with {{\n{body}\n  }};")
    o.append("};")
o.append("-- DRIFT:\n"+"\n".join("--   "+d for d in drift))
print("\n".join(o))
