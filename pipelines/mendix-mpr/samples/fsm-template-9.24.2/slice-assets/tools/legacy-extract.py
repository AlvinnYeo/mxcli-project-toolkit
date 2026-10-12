#!/usr/bin/env python3
"""Extract legacy DataGrid / ReferenceSelector essentials from mxcli bson dump (json) of pages/snippets."""
import json, subprocess, sys, os
M="<lab>/mxcli"; APP=sys.argv[1]
def kv(o):
    if isinstance(o,list):
        if o and all(isinstance(x,dict) and set(x)=={"Key","Value"} for x in o):
            return {x["Key"]:kv(x["Value"]) for x in o}
        return [kv(x) for x in o if not isinstance(x,int)]
    return o
def txt(t):
    if not isinstance(t,dict): return ""
    for it in t.get("Items",[]) or []:
        if isinstance(it,dict) and it.get("LanguageCode")=="en_US": return it.get("Text","")
    return ""
def ds(d):
    if not isinstance(d,dict): return None
    t=d.get("$Type"); r={"type":t}
    for k in ("XPathConstraint","Microflow","Nanoflow"):
        if d.get(k): r[k]=d[k]
    ms=d.get("MicroflowSettings")
    if isinstance(ms,dict):
        r["mf"]=ms.get("Microflow"); r["mfparams"]=[(pm.get("Parameter"),pm.get("Expression") or (pm.get("Variable") or {}).get("PageParameter") if isinstance(pm.get("Variable"),dict) else pm.get("Expression")) for pm in ms.get("ParameterMappings",[]) if isinstance(pm,dict)]
    er=d.get("EntityRef")
    if isinstance(er,dict): r["entity"]=er.get("Entity"); 
    if isinstance(er,dict) and er.get("Steps"): r["steps"]=[(s.get("Association"),s.get("DestinationEntity")) for s in er["Steps"]]
    if isinstance(d.get("SortBar"),dict): r["sort"]=[(s.get("AttributeRef",{}).get("Attribute"),s.get("SortOrder")) for s in d["SortBar"].get("SortItems",[]) if isinstance(s,dict)]
    return r
def act(a):
    if not isinstance(a,dict): return None
    r={"type":a.get("$Type")}
    for k in ("PageSettings","MicroflowSettings"):
        v=a.get(k)
        if isinstance(v,dict):
            r["target"]=v.get("Page") or v.get("Microflow")
    return r
out=[]
def walk(o,doc):
    if isinstance(o,dict):
        t=o.get("$Type")
        if t=="Forms$DataGrid":
            cols=[]
            for c in o.get("Columns",[]):
                if not isinstance(c,dict): continue
                ar=c.get("AttributeRef") if isinstance(c.get("AttributeRef"),dict) else {}
                st=[x.get("Association") for x in (((ar.get("EntityRef") or {}).get("Steps")) or []) if isinstance(x,dict)]
                cols.append((ar.get("Attribute"), txt(c.get("Caption")), st, (c.get("FormattingInfo") or {}).get("DateFormat")))
            btns=[]
            cb=o.get("ControlBar") or {}
            dflt=(cb.get("DefaultButtonPointer") or {}).get("Data") if isinstance(cb,dict) else None
            for b in (cb.get("NewButtons") or []) if isinstance(cb,dict) else []:
                if not isinstance(b,dict) or b.get("$Type")=="Forms$GridSearchButton": continue
                a=b.get("Action") if isinstance(b.get("Action"),dict) else {}
                fs=a.get("FormSettings") or b.get("FormSettings") or {}
                ms=a.get("MicroflowSettings") or {}
                btns.append({"btype":b["$Type"].split("$")[1],"name":b.get("Name"),"caption":txt((b.get("CaptionTemplate") or {}).get("Template")),"atype":a.get("$Type","").split("$")[-1],"form":fs.get("Form") if isinstance(fs,dict) else None,"mf":ms.get("Microflow") if isinstance(ms,dict) else None,"entity":b.get("Entity"),"default":(b.get("$ID") or {}).get("Data")==dflt,"icon":bool(b.get("Icon"))})
            out.append({"doc":doc,"widget":o.get("Name"),"kind":"DataGrid","ds":ds(o.get("DataSource")),"cols":cols,"buttons":btns,"selection":o.get("SelectionMode"),"default":act(o.get("DefaultButtonTrigger")) if 0 else None})
        if t=="Forms$ReferenceSelector":
            ar=o.get("AttributeRef") or {}
            src=o.get("SelectorSource") or {}
            out.append({"doc":doc,"widget":o.get("Name"),"kind":"ReferenceSelector","attr":ar.get("Attribute"),"path":[(s.get("Association"),s.get("DestinationEntity")) for s in ((ar.get("EntityRef") or {}).get("Steps") or []) if isinstance(s,dict)],"label":txt((o.get("LabelTemplate") or {}).get("Template") if isinstance(o.get("LabelTemplate"),dict) else None),"source":{"type":src.get("$Type"),"xpath":src.get("XPathConstraint"),"mf":src.get("DataSourceMicroflowSettings",{}).get("Microflow") if isinstance(src.get("DataSourceMicroflowSettings"),dict) else None},"onchange":act(o.get("OnChangeAction")),"editable":o.get("Editable"),"required":(o.get("RequiredMessage") and txt(o.get("RequiredMessage"))) or None})
        for v in o.values(): walk(v,doc)
    elif isinstance(o,list):
        for v in o: walk(v,doc)
docs=sorted({l.split()[0] for l in open(sys.argv[2])})
for doc in docs:
    typ="snippet" if ".Snippet_" in doc else "page"
    raw=subprocess.run([M,"bson","dump","-p",APP,"--type",typ,"--object",doc],capture_output=True,text=True).stdout
    open(f"<lab>/web-assets/bson/{doc}.json","w").write(raw)
    walk(kv(json.loads(raw)),doc)
json.dump(out,open("<lab>/web-assets/legacy-widgets.json","w"),indent=1)
for w in out: print(json.dumps(w)[:700])
