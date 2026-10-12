"""Split a describe script into top-level statements, shared by topo-order-mdl.py and
compare-mdl.py. A statement ends at a column-0 line that ends in ';' — but only when that line
starts and ends OUTSIDE a string literal ('…', doubled quote escapes), a $$…$$ block (Java/JS
bodies, JSON samples) or a comment (-- to end of line, /* … */). The GenAI Showcase (increment 2)
has microflows returning multi-line JSON string literals whose inner lines sit at column 0 and
end in ';', and the plain column-0 rule cut those flows into fragments that were then reordered.
Text is passed through byte-for-byte: no newline translation (CRLF inside literals is load-bearing)."""
import re
OPENER = re.compile(r'^(create|grant|revoke|alter|drop|delete|mdl|@|/\*|--)')
def split_statements(text):
    stmts, cur, state, pending = [], [], 'code', False      # state: code | str | dollar | block
    for ln in text.split('\n'):
        start = state
        # a candidate boundary closes only when the next non-blank line opens a statement: Studio Pro
        # emits multi-line expressions with continuation lines at column 0 ("else $X, Y = $Z);")
        if pending and ln.strip():
            if start == 'code' and OPENER.match(ln):
                stmts.append('\n'.join(cur)); cur = []
            pending = False
        i, n = 0, len(ln)
        while i < n:
            c = ln[i]
            if state == 'code':
                if c == "'": state = 'str'
                elif ln.startswith('$$', i): state = 'dollar'; i += 1
                elif ln.startswith('--', i): break                 # comment to end of line
                elif ln.startswith('/*', i): state = 'block'; i += 1
            elif state == 'str':
                if c == "'": state = 'code'                        # '' escape toggles twice, net unchanged
            elif state == 'dollar':
                if ln.startswith('$$', i): state = 'code'; i += 1
            elif state == 'block':
                if ln.startswith('*/', i): state = 'code'; i += 1
            i += 1
        cur.append(ln)
        # the line may START inside a $$ body: java/javascript actions end with a column-0 `$$;`
        # (GenAI Showcase: 15 java actions of GenAICommons merged into one "statement", and check's
        # statement numbers no longer matched ours). The opener lookahead above still guards the
        # multi-line-literal case.
        if state == 'code' and ln and not ln[0].isspace() and ln.rstrip().endswith(';'):
            pending = True
    if pending and cur: stmts.append('\n'.join(cur)); cur = []
    return stmts, '\n'.join(cur)
