import sqlite3,sys,re,collections
db=sqlite3.connect(sys.argv[1]); pat=sys.argv[2].encode()
names={}
rows=db.execute("select UnitID,ContainerID,Contents from Unit").fetchall()
def name(b):
    m=re.search(rb'\x02Name\x00....([^\x00]*)\x00',b,re.S); return m.group(1).decode('utf8','replace') if m else '?'
def typ(b):
    m=re.search(rb'\x02\$Type\x00....([^\x00]*)\x00',b,re.S); return m.group(1).decode() if m else '?'
info={r[0]:(r[1],name(r[2]) ,typ(r[2])) for r in rows}
def qual(u):
    c,n,t=info[u]; 
    # walk up to module
    p=c; path=[n]
    while p in info:
        pc,pn,pt=info[p]; 
        if pt=='Projects$ModuleImpl' or pt.endswith('Module') : path.insert(0,pn); break
        p=pc
    return '.'.join(path)
hits=collections.Counter()
for u,c,b in rows:
    n=len(re.findall(re.escape(pat)+rb'(?=[\x00/\]\.\s=\)])',b))
    if n: hits[(qual(u),info[u][2])]+=n
for (q,t),n in hits.most_common(): print(n,t,q)
