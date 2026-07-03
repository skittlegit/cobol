"""T0.5 spike deliverable: preprocessing + tree-sitter-cobol paragraph extraction.

Pipeline: fixed-format normalize -> mask EXEC CICS/SQL/DLI blocks (precompiler
analogue) -> mask procedure-division COPY REPLACING -> tree-sitter parse ->
extract paragraphs + control-flow nesting. Line numbers preserved throughout.
"""
import re
import sys
from tree_sitter import Language, Parser

LANG = Language('/home/claude/ts_cobol.so', 'COBOL')


def preprocess(src: str) -> str:
    """Line-count-preserving mask of EXEC ... END-EXEC and COPY ... REPLACING."""
    lines = src.splitlines()
    out, in_exec, in_copy = [], False, False
    for ln in lines:
        body = ln[7:72] if len(ln) > 7 else ''
        is_comment = len(ln) > 6 and ln[6] in ('*', '/')
        upper = body.upper()

        if in_exec:
            if 'END-EXEC' in upper:
                in_exec = False
                # preserve sentence terminator if END-EXEC. closed the sentence
                out.append('           CONTINUE.' if upper.rstrip().endswith('.') else '')
            else:
                out.append('')
            continue
        if in_copy:
            out.append('')
            if body.rstrip().endswith('.'):
                in_copy = False
                out[-1] = '           CONTINUE.'
            continue
        if not is_comment and re.search(r'\bEXEC\s+(CICS|SQL|DLI)\b', body, re.I):
            if 'END-EXEC' in upper:
                out.append('           CONTINUE.' if upper.rstrip().endswith('.')
                           else '           CONTINUE')
            else:
                in_exec = True
                out.append('           CONTINUE')
            continue
        if not is_comment and re.search(r'\bCOPY\s+\S+\s+REPLACING\b', body, re.I):
            if body.rstrip().endswith('.'):
                out.append('           CONTINUE.')
            else:
                in_copy = True
                out.append('')
            continue
        out.append(ln)
    return '\n'.join(out) + '\n'


def parse(src: str):
    p = Parser()
    p.set_language(LANG)
    return p.parse(preprocess(src).encode())


def count_errors(node, acc=None):
    if acc is None:
        acc = {'total': 0, 'error': 0}
    acc['total'] += 1
    if node.type == 'ERROR':
        acc['error'] += 1
    for c in node.children:
        count_errors(c, acc)
    return acc


def extract_paragraphs(root):
    """(name, start_line, end_line) for every procedure-division paragraph."""
    hits = []
    def walk(n):
        if n.type in ('paragraph', 'paragraph_header', 'procedure_section'):
            name = n.text.decode(errors='replace').split('.')[0].strip()
            hits.append((name, n.start_point[0] + 1, n.end_point[0] + 1))
        for c in n.children:
            walk(c)
    walk(root)
    return hits


def count_nodes_of(root, types):
    n = 0
    def walk(x):
        nonlocal n
        if x.type in types:
            n += 1
        for c in x.children:
            walk(c)
    walk(root)
    return n


def ground_truth_paragraphs(src: str) -> set:
    """Regex ground truth: Area-A labels in the PROCEDURE DIVISION ending with '.'"""
    names, in_proc = set(), False
    for ln in src.splitlines():
        if len(ln) > 6 and ln[6] in ('*', '/'):
            continue
        body = ln[7:72] if len(ln) > 7 else ''
        if re.match(r'\s*PROCEDURE\s+DIVISION', body, re.I):
            in_proc = True
            continue
        if in_proc:
            m = re.match(r'([A-Z0-9][A-Z0-9-]*)\s*\.\s*$', body.strip(), re.I)
            if m and not re.match(r'(END|EXIT|GOBACK|STOP|CONTINUE)$', m.group(1), re.I):
                names.add(m.group(1).upper())
    return names


if __name__ == '__main__':
    base = '/home/claude/carddemo/app/cbl/'
    for f in ['CBTRN02C.cbl', 'COSGN00C.cbl', 'COACTUPC.cbl']:
        src = open(base + f, encoding='utf-8', errors='replace').read()
        tree = parse(src)
        s = count_errors(tree.root_node)
        paras = extract_paragraphs(tree.root_node)
        got = {p[0].upper() for p in paras}
        truth = ground_truth_paragraphs(src)
        ifs = count_nodes_of(tree.root_node, {'if_statement'})
        evals = count_nodes_of(tree.root_node, {'evaluate_statement'})
        performs = count_nodes_of(tree.root_node, {'perform_statement'})
        print(f"{f:14s} ERROR={s['error']}/{s['total']} nodes | "
              f"paragraphs: found={len(paras)} truth={len(truth)} "
              f"missed={sorted(truth - got)[:3] or 'none'} | "
              f"IF={ifs} EVALUATE={evals} PERFORM={performs}")
        print(f"   sample: {[p for p in paras[:4]]}")
