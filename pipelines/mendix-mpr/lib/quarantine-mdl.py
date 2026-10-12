#!/usr/bin/env python3
"""quarantine-mdl.py <script.mdl> <check-output.txt> <deferred.mdl>

Move the statements that `mxcli check` rejected out of <script.mdl> (rewritten in place) and append
them to <deferred.mdl>, so the rest of the module can be executed instead of nothing at all. check is
all-or-nothing per file: one `-- line N:` syntax error or one `statement N:` reference error blocks
every other statement of the module (GenAI Showcase, 2026-10-12: 1 of 36 modules executed; 25 of
the 35 failures were cascades of 10 modules whose java actions mxcli emits with a trailing `,` inside
a `--` comment). Deferred statements are retried by the caller once the modules they reference exist;
what still fails is a ledger row with the verbatim check error, never a silent drop.

Numbering: check counts statements without the leading `mdl 1;` (verified against
ChatCompletions_ComplexityReduction "statement 6" and GenAICommons "statement 233"). Prints the number of
statements moved, 0 when the check output names none it can map.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdlsplit import split_statements

src, chk, deferred = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src, encoding='utf-8', newline='').read()
stmts, tail = split_statements(text)
if tail.strip(): stmts.append(tail)
report = open(chk, encoding='utf-8', errors='replace').read()

# statement index (0-based into stmts) of each 1-based check statement number: check does not count
# the leading `mdl 1;` (GenAICommons: "statement 233" = the 234th split statement, `mdl 1;` first).
numbered = [i for i, s in enumerate(stmts) if s.strip() != 'mdl 1;']
bad = set()
for n in re.findall(r'^\s*statement (\d+):', report, re.M):
    n = int(n) - 1
    if 0 <= n < len(numbered): bad.add(numbered[n])
# syntax errors come as `line N:M` — map the line onto the statement that holds it
if re.search(r'^Syntax errors found', report, re.M):
    starts, line = [], 1
    for s in stmts:
        starts.append(line); line += s.count('\n') + 1
    for n in re.findall(r'^\s*- line (\d+)', report, re.M):
        n = int(n)
        for i in range(len(stmts) - 1, -1, -1):
            if starts[i] <= n: bad.add(i); break
# close over the module's own references: a statement that names a document defined by a deferred
# statement would fail the next round anyway (check skips references to objects created within the
# script, so deferring the definition exposes every caller) — MxGenAIConnector took 15 rounds of one
# layer each before this. The callers go to the deferred file too and come back in the same retry.
head_re = re.compile(r'^(?:@[^\n]*\n|/\*\*.*?\*/\s*)*create or modify ([a-z][a-z -]*?) ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\b', re.M | re.S)
grant_re = re.compile(r'^grant .*? on (?:[a-z ]+?) ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\b', re.M)
defined = {}
for i, s in enumerate(stmts):
    m = head_re.search(s)
    if m and m.group(1) != 'module': defined.setdefault(m.group(2), []).append(i)
grown = True
while grown:
    grown = False
    names = {n for n, ks in defined.items() if any(k in bad for k in ks)}
    for n in names:
        pat = re.compile(r'\b' + re.escape(n) + r'\b')
        for i, s in enumerate(stmts):
            if i in bad or s.strip() == 'mdl 1;': continue
            m = head_re.search(s); g = grant_re.search(s.strip())
            if (m and m.group(1) == 'module'): continue
            if pat.search(s) and not (m and m.group(2) == n and m.group(1) in ('entity', 'non-persistent entity')):
                bad.add(i); grown = True
if not bad:
    print(0); sys.exit(0)
keep = [s for i, s in enumerate(stmts) if i not in bad]
gone = [s for i, s in enumerate(stmts) if i in bad]
open(src, 'w', encoding='utf-8', newline='').write('\n'.join(keep) + '\n')
with open(deferred, 'a', encoding='utf-8', newline='') as f:
    if os.path.getsize(deferred) == 0: f.write('mdl 1;\n')
    for s in gone:
        head = s.strip().split('\n')[0][:100]
        f.write('-- deferred: check rejected this statement (%s); see the check capture for the verbatim error\n%s\n' % (head, s))
print(len(gone))
