#!/usr/bin/env python3
"""(set-memberaccess variant: give a re-created association's member rights a value, CE0073) Remove dangling DomainModels$MemberAccess entries (access-rule member rights) that still name a deleted
association - mxcli `drop module` / `drop entity` leave them behind (CE1613 at Access rule of entity ...), and the
module that owned the association no longer exists, so the increment 6 create-then-drop workaround cannot run.
usage: bson-drop-memberaccess.py <app.mpr> <Assoc.QualifiedName>..."""
import sqlite3,struct,sys,hashlib,base64
mpr=sys.argv[1]; VALUE=sys.argv[2].encode(); TARGETS=set(a.encode() for a in sys.argv[3:])
def cstr(b,i):
    j=b.index(b'\x00',i); return b[i:j],j+1
def elems(b,i):
    n=struct.unpack_from('<i',b,i)[0]; end=i+n; i+=4; out=[]
    while b[i]!=0:
        t=b[i]; k,i2=cstr(b,i+1); s=i2
        if t==2: l=struct.unpack_from('<i',b,s)[0]; e=s+4+l
        elif t in(3,4): e=s+struct.unpack_from('<i',b,s)[0]
        elif t in(1,9,0x11,0x12): e=s+8
        elif t==0x10: e=s+4
        elif t==8: e=s+1
        elif t==0x0A: e=s
        elif t==5: e=s+5+struct.unpack_from('<i',b,s)[0]
        elif t==7: e=s+12
        else: raise ValueError(t)
        out.append((t,k,b[s:e])); i=e
    return out
def build(items):
    body=b''.join(bytes([t])+k+b'\x00'+v for t,k,v in items)+b'\x00'
    return struct.pack('<i',len(body)+4)+body
def strval(v): return v[4:-1]
def is_dead(v):
    it=elems(v,0); d={k:(t,x) for t,k,x in it}
    return b'$Type' in d and strval(d[b'$Type'][1])==b'DomainModels$MemberAccess' and b'Association' in d and d[b'Association'][0]==2 and strval(d[b'Association'][1]) in TARGETS
removed=0
def walk(v,isarr=False):
    global removed
    items=elems(v,0); new=[]; ch=False
    for t,k,x in items:
        if t in(3,4):
            if isarr and t==3 and is_dead(x):
                it=elems(x,0); it=[(tt,kk,(struct.pack('<i',len(VALUE)+1)+VALUE+b'\x00') if kk==b'AccessRights' else vv) for tt,kk,vv in it]; nx=build(it)
                if nx!=x: removed+=1; ch=True
                new.append((t,k,nx)); continue
            nx=walk(x,t==4)
            if nx!=x: ch=True
            x=nx
        new.append((t,k,x))
    if isarr and ch:
        # BSON arrays in MPR: first element may be a version marker (int); keep keys as-is except renumber sequentially
        new=[(t,str(i).encode(),x) for i,(t,k,x) in enumerate(new)]
    return build(new) if ch else v
db=sqlite3.connect(mpr); units=0
for uid,c in db.execute('select UnitID,Contents from Unit').fetchall():
    if not any(tg in c for tg in TARGETS): continue
    before=removed; nb=walk(c)
    if removed>before:
        units+=1; db.execute('update Unit set Contents=?,ContentsHash=? where UnitID=?',(nb,base64.b64encode(hashlib.sha256(nb).digest()).decode(),uid))
db.commit(); print(f'set {removed} MemberAccess entries in {units} units')
