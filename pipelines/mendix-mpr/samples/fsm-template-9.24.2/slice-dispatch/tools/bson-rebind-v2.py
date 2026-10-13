#!/usr/bin/env python3
"""Increment 8: contextual rebind inside page/snippet units of an MPR v2 project (mprcontents/**/*.mxunit), for what
mxcli cannot alter in place (pluggable-widget data sources, entity paths, XPath of generated data grids).
usage: bson-rebind-v2.py <seam-rebind.py> <unit.mxunit>...      then: mxcli fix hashes --repair -p <app.mpr>
  - every XPathConstraint / Expression string goes through seam-rebind.py's rebind() (R1-R12 text rules);
  - every entity-path step over a technician navigation whose DestinationEntity is Technician.Technician now ends at
    TicketManagement.MonoTechnician, and an AttributeRef on that path names TicketManagement.MonoTechnician.<attr>.
A unit that does not re-encode byte-identically when unchanged is refused (exit 2)."""
import os, re, struct, sys
os.environ.setdefault("MXCLI", "x"); os.environ.setdefault("APP", "x")
src = open(sys.argv[1]).read(); exec(src[:src.index("body = []")])  # rebind(), NAV_T
TECH = re.compile(r"TicketManagement\.%s$" % NAV_T)
FIX = {"8": 1, "1": 8, "9": 8, "17": 8, "18": 8, "16": 4, "7": 12}
def cstr(b, i):
    j = b.index(b"\x00", i); return b[i:j].decode("utf8"), j + 1
def dec(b, i):
    n = struct.unpack_from("<i", b, i)[0]; end = i + n; i += 4; out = []
    while b[i] != 0:
        t = b[i]; k, i = cstr(b, i + 1)
        if t == 2:
            l = struct.unpack_from("<i", b, i)[0]; v = b[i + 4:i + 3 + l].decode("utf8"); i += 4 + l
        elif t in (3, 4):
            v, i = dec(b, i)
        elif t == 5:
            l = struct.unpack_from("<i", b, i)[0]; v = b[i:i + 5 + l]; i += 5 + l
        elif t == 10:
            v = b""
        elif str(t) in FIX:
            v = b[i:i + FIX[str(t)]]; i += FIX[str(t)]
        else:
            raise ValueError("bson type %d" % t)
        out.append([t, k, v])
    assert i + 1 == end, (i, end)
    return out, end
def enc(d):
    body = b""
    for t, k, v in d:
        body += bytes([t]) + k.encode() + b"\x00"
        if t == 2:
            e = v.encode("utf8") + b"\x00"; body += struct.pack("<i", len(e)) + e
        elif t in (3, 4):
            body += enc(v)
        else:
            body += v
    return struct.pack("<i", len(body) + 5) + body + b"\x00"
changes = 0
def get(d, k):
    for e in d:
        if e[1] == k: return e
def walk(d, doc):
    global changes
    if not isinstance(d, list): return
    tech_path = False
    steps = get(d, "Steps")
    if steps and steps[0] in (3, 4):
        for _, _, st in steps[2]:
            if isinstance(st, list):
                a, de = get(st, "Association"), get(st, "DestinationEntity")
                if a and de and TECH.match(a[2] or "") and de[2] == "Technician.Technician":
                    de[2] = "TicketManagement.MonoTechnician"; changes += 1; tech_path = True
    for e in d:
        t, k, v = e
        if t == 2 and k in ("XPathConstraint", "Expression") and v:
            n = rebind(v, doc)
            if n != v: e[2] = n; changes += 1
        if t in (3, 4):
            walk(v, doc)
            er = get(v, "EntityRef") if t == 3 else None
            at = get(v, "Attribute") if t == 3 else None
            if er and at and at[0] == 2 and at[2].startswith("Technician.Technician."):
                st = get(er[2], "Steps") if er[0] == 3 else None
                if st and any(isinstance(x[2], list) and (get(x[2], "DestinationEntity") or [0, 0, ""])[2] == "TicketManagement.MonoTechnician" for x in st[2]):
                    at[2] = "TicketManagement.MonoTechnician." + at[2].split(".")[-1]; changes += 1
for f in sys.argv[2:]:
    b = open(f, "rb").read()
    d, _ = dec(b, 0)
    if enc(d) != b: print("REFUSED (no byte-identical round trip):", f); sys.exit(2)
    before = changes
    walk([[3, "root", d]], f)
    if changes != before:
        open(f, "wb").write(enc(d)); print(f"{changes - before} change(s): {f}")
print(f"{len(handoffs)} hand-off brackets", *handoffs, sep="\n  ")
