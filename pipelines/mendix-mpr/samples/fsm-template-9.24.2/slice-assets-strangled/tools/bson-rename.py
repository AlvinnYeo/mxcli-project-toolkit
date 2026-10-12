#!/usr/bin/env python3
"""Rewrite qualified names (or, with --literal, exact substrings; map values use \\n for newlines) inside string values of every unit's BSON in an MPR v1 file (XPath, expressions),
recomputing lengths and ContentsHash. Increment 7 workaround: `move entity` rewrites by-name references but NOT
names embedded in XPath/expression text. usage: bson-rename.py <app.mpr> <map.tsv> [--dry]"""
import sqlite3,struct,re,sys,hashlib,base64
mpr,mapf=sys.argv[1],sys.argv[2]; dry='--dry' in sys.argv
MAP=[tuple(x.replace('\\n','\n') for x in l.rstrip('\n').split('\t')) for l in open(mapf) if l.strip() and not l.startswith('#')]
LIT='--literal' in sys.argv
RX=[(re.compile(r'(?<![A-Za-z0-9_])'+re.escape(a)+r'(?![A-Za-z0-9_])'),b) for a,b in MAP]
def sub(s):
    if LIT:
        for a,b in MAP:
            if a in s: s=b[1:] if b.startswith('=') else s.replace(a,b)
        return s
    for rx,b in RX: s=rx.sub(b,s)
    return s
def cstr(b,i):
    j=b.index(b'\x00',i); return b[i:j],j+1
def doc(b,i):
    n=struct.unpack_from('<i',b,i)[0]; end=i+n; i+=4; out=bytearray(); ch=0
    while b[i]!=0:
        t=b[i]; k,i2=cstr(b,i+1); out+=bytes([t])+k+b'\x00'; i=i2
        if t==2:
            l=struct.unpack_from('<i',b,i)[0]; s=b[i+4:i+4+l-1].decode('utf8'); i+=4+l
            s2=sub(s)
            if s2!=s: ch+=1
            e=s2.encode('utf8')+b'\x00'; out+=struct.pack('<i',len(e))+e
        elif t in (3,4):
            sub_b,i,c=doc(b,i); out+=sub_b; ch+=c
        elif t==1 or t==9 or t==0x11 or t==0x12: out+=b[i:i+8]; i+=8
        elif t==0x10: out+=b[i:i+4]; i+=4
        elif t==8: out+=b[i:i+1]; i+=1
        elif t==0x0A: pass
        elif t==5:
            l=struct.unpack_from('<i',b,i)[0]; out+=b[i:i+5+l]; i+=5+l
        elif t==7: out+=b[i:i+12]; i+=12
        else: raise ValueError('bson type %d'%t)
    i+=1; assert i==end,(i,end)
    body=bytes(out)+b'\x00'
    return struct.pack('<i',len(body)+4)+body,i,ch
db=sqlite3.connect(mpr); tot=0; units=0
for uid,c in db.execute('select UnitID,Contents from Unit').fetchall():
    nb,_,ch=doc(c,0)
    if ch:
        units+=1; tot+=ch
        if not dry: db.execute('update Unit set Contents=?,ContentsHash=? where UnitID=?',(nb,base64.b64encode(hashlib.sha256(nb).digest()).decode(),uid))
    elif nb!=c: raise SystemExit('round-trip mismatch on unchanged unit')
if not dry: db.commit()
print(f'{"would rewrite" if dry else "rewrote"} {tot} strings in {units} units')
