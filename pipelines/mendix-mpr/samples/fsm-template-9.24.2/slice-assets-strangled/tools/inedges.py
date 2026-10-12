import sqlite3,sys,collections
c=sqlite3.connect(sys.argv[1])
S={'AssetManagement','Part','WarehouseManagement','Tool'}
rows=[r for r in c.execute("select SourceType,SourceName,TargetType,TargetName,RefKind from refs")]
m=lambda n:n.split('.')[0]
ins=[r for r in rows if m(r[3]) in S and m(r[1]) not in S]
print("in-edge refs",len(ins),"distinct src docs",len({r[1] for r in ins}))
cnt=collections.Counter((m(r[1]),r[0]) for r in ins)
by=collections.defaultdict(dict)
for (mod,t),n in cnt.items(): by[mod][t]=n
for mod in sorted(by,key=lambda k:-sum(by[k].values())):
  docs=len({r[1] for r in ins if m(r[1])==mod})
  print(mod,sum(by[mod].values()),"docs",docs,by[mod])
if len(sys.argv)>2:
  for r in ins:
    if m(r[1])==sys.argv[2]: print("\t".join(r))
