#!/usr/bin/env python3
"""Reorder the microflow/nanoflow statements of a `describe module … with all`
script so every flow is created before any statement that calls it.
Everything else keeps its relative position. Usage: topo-order-mdl.py in.mdl out.mdl"""
import re, sys
src = open(sys.argv[1], encoding='utf-8', newline='').read().split('\n')  # newline='': annotation text carries CRLF inside string literals; translating it changes the flow and exec refuses the splice
# split into top-level statements: a statement ends at a column-0 line ending in ';'
stmts, cur = [], []
for ln in src:
    cur.append(ln)
    if ln and not ln[0].isspace() and ln.rstrip().endswith(';'):
        stmts.append('\n'.join(cur)); cur = []
tail = '\n'.join(cur)
head_re = re.compile(r'^create or modify (microflow|nanoflow) ([A-Za-z_]+\.[A-Za-z_]+)', re.M)
# a flow unit = its create statement + the `grant execute on microflow <same>` statements right after it
units, i = [], 0
while i < len(stmts):
    m = head_re.search(stmts[i])
    if m:
        name, j = m.group(2), i + 1
        while j < len(stmts) and re.match(r'^(\s*)grant execute on (microflow|nanoflow) ' + re.escape(name) + r'\b', stmts[j].strip()):
            j += 1
        units.append(('\n'.join(stmts[i:j]), name)); i = j
    else:
        units.append((stmts[i], None)); i += 1
stmts = [u[0] for u in units]
flows = {u[1]: k for k, u in enumerate(units) if u[1]}
flow_idx = sorted(flows.values())
# dependencies: a flow statement mentioning another flow's qualified name
deps = {}
for name, i in flows.items():
    body = stmts[i]
    deps[name] = {o for o in flows if o != name and re.search(r'\b' + re.escape(o) + r'\b', body)}
# Kahn, stable on original order
order, placed = [], set()
remaining = [n for n in sorted(flows, key=flows.get)]
while remaining:
    progressed = False
    for n in list(remaining):
        if deps[n] <= placed:
            order.append(n); placed.add(n); remaining.remove(n); progressed = True
    if not progressed:   # cycle (recursion): emit the rest in original order, say so
        sys.stderr.write('cycle among: %s\n' % ', '.join(remaining)); order += remaining; break
moved = sum(1 for k, n in enumerate(order) if flows[n] != flow_idx[k])
out = list(stmts)
for k, n in enumerate(order):
    out[flow_idx[k]] = stmts[flows[n]]
open(sys.argv[2], 'w', encoding='utf-8', newline='').write('\n'.join(out) + ('\n' + tail if tail.strip() else '\n'))
sys.stderr.write('statements=%d flows=%d repositioned=%d\n' % (len(stmts), len(flows), moved))
