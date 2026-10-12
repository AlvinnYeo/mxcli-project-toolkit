#!/usr/bin/env python3
"""Replace a document unit in <cur.mpr> by the unit of the same name from <old.mpr> (MPR v1). Used once: the
describe -> drop/create round-trip of Scheduler.PlannerContext_GetWorkOrders broke a decision (CE0117).
usage: restore-unit.py <cur.mpr> <old.mpr> <DocName> <$Type>"""
import sqlite3,sys,re,struct
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
cur,old,name,typ=sys.argv[1:5]
def find(db):
    for uid,cid,cn,b in db.execute('select UnitID,ContainerID,ContainmentName,Contents from Unit'):
        top={k:v for t_,k,v in elems(b,0) if t_==2}
        if top.get(b'$Type',b'')[4:-1].decode()==typ and top.get(b'Name',b'')[4:-1].decode()==name: return uid,cid,cn,b
c=sqlite3.connect(cur); o=sqlite3.connect(old)
cu=find(c); ou=find(o)
assert cu and ou, (bool(cu),bool(ou))
row=o.execute('select * from Unit where UnitID=?',(ou[0],)).fetchone()
cols=[r[1] for r in o.execute('pragma table_info(Unit)')]
c.execute('delete from Unit where UnitID=?',(cu[0],))
r=dict(zip(cols,row)); r['ContainerID']=cu[1]
c.execute(f"insert into Unit ({','.join(cols)}) values ({','.join('?'*len(cols))})",[r[k] for k in cols]); c.commit()
print('restored',name,'from',old)
