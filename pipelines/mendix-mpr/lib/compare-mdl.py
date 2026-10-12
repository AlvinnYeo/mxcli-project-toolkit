#!/usr/bin/env python3
"""Per-document comparison of two `describe module … with all` scripts (source, target).
Statements are grouped per document (a create plus the grant/index statements that
name the same document), keyed by (type, qualified name); order is ignored.
Prints TSV rows: module, document, type, verdict, evidence."""
import re, sys
def units(path):
    stmts, cur = [], []
    for ln in open(path, encoding='utf-8', newline='').read().split('\n'):
        cur.append(ln)
        if ln and not ln[0].isspace() and ln.rstrip().endswith(';'):
            stmts.append('\n'.join(cur)); cur = []
    head = re.compile(r'^(?:@[^\n]*\n)*create or modify (module role|non-persistent entity|persistent entity|view entity|entity|association|enumeration|microflow|nanoflow|page|snippet|layout|image collection|module) ([A-Za-z_]+(?:\.[A-Za-z_]+)?)', re.M)
    grant = re.compile(r'^grant .*? on (?:entity|page|microflow|nanoflow) ([A-Za-z_]+\.[A-Za-z_]+)', re.M)
    docs, last = {}, None
    for s in stmts:
        body = re.sub(r'/\*\*.*?\*/\s*', '', s, flags=re.S)   # doc comment compared separately
        doc = re.search(r'/\*\*(.*?)\*/', s, re.S)
        m = head.search(body)
        if m:
            t = m.group(1).replace('non-persistent entity','entity').replace('persistent entity','entity').replace('view entity','entity')
            last = (t, m.group(2)); docs[last] = {'body': body.strip(), 'doc': (doc.group(1).strip() if doc else ''), 'grants': []}
            continue
        g = grant.search(body)
        if g and last and g.group(1) == last[1]: docs[last]['grants'].append(body.strip()); continue
        if g:
            key = next((k for k in docs if k[1] == g.group(1)), None)
            if key: docs[key]['grants'].append(body.strip()); continue
        sys.stderr.write('unattached statement in %s: %s\n' % (path, body.strip()[:80]))
    return docs
src, tgt = units(sys.argv[1]), units(sys.argv[2])
module = sys.argv[3]
def firstdiff(a, b):
    al, bl = a.split('\n'), b.split('\n')
    for i, (x, y) in enumerate(zip(al, bl)):
        if x != y: return 'line %d: %r -> %r' % (i+1, x.strip()[:70], y.strip()[:70])
    return 'length %d -> %d lines' % (len(al), len(bl))
for k in sorted(src, key=lambda k: (k[0], k[1])):
    t, name = k
    if k not in tgt:
        print('\t'.join([module, name, t, 'failed-exec', 'absent from target describe'])); continue
    s, g = src[k], tgt[k]
    ev = []
    if s['body'] != g['body']: ev.append('body: ' + firstdiff(s['body'], g['body']))
    if sorted(s['grants']) != sorted(g['grants']): ev.append('grants: %d -> %d' % (len(s['grants']), len(g['grants'])))
    if s['doc'] != g['doc']: ev.append('documentation: ' + firstdiff(s['doc'], g['doc']))
    print('\t'.join([module, name, t, 'emitted-drift' if ev else 'emitted-identical', '; '.join(ev) if ev else 'describe on target identical (body, grants, documentation)']))
for k in sorted(set(tgt) - set(src)):
    print('\t'.join([module, k[1], k[0], 'target-extra', 'present in target only (not in source describe)']))
