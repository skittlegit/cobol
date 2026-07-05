"""T0.5 spike deliverable: preprocessing + tree-sitter-cobol paragraph extraction.

Pipeline: fixed-format normalize -> mask EXEC CICS/SQL/DLI blocks (precompiler
analogue) -> mask procedure-division COPY REPLACING -> tree-sitter parse ->
extract paragraphs + control-flow nesting. Line numbers preserved throughout.
"""
import re
import sys
from pathlib import Path

DEFAULT_LANGUAGE_PATHS = (
    Path('build/ts_cobol.so'),
    Path('build/ts_cobol.dll'),
    Path('build/ts_cobol.dylib'),
)

SMOKE_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SMOKE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC CICS RETURN
           END-EXEC.
           GOBACK.
"""


def _import_tree_sitter():
    try:
        from tree_sitter import Language, Parser
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'tree_sitter is required for the spike parser. Install it with '
            '`pip install tree_sitter==0.21.3`.'
        ) from exc
    return Language, Parser


def _language_path() -> Path:
    """Return the compiled tree-sitter COBOL library path."""
    import os

    if os.environ.get('TREE_SITTER_COBOL_LIB'):
        return Path(os.environ['TREE_SITTER_COBOL_LIB'])

    for path in DEFAULT_LANGUAGE_PATHS:
        if path.exists():
            return path

    searched = ', '.join(str(path) for path in DEFAULT_LANGUAGE_PATHS)
    raise FileNotFoundError(
        'Compiled tree-sitter COBOL library not found. Set '
        'TREE_SITTER_COBOL_LIB or place it at one of: ' + searched
    )


def get_language():
    """Load the COBOL language without hardcoding a machine-specific path."""
    Language, _ = _import_tree_sitter()
    return Language(str(_language_path()), 'COBOL')


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
    _, Parser = _import_tree_sitter()
    p = Parser()
    p.set_language(get_language())
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


def main() -> int:
    import os

    base = Path(os.environ.get('CARDDEMO_CBL_DIR', 'data/corpora/carddemo/app/cbl'))
    args = [Path(arg) for arg in sys.argv[1:]]
    sample_names = ['CBTRN02C.cbl', 'COSGN00C.cbl', 'COACTUPC.cbl']

    if args:
        paths = args
    elif base.exists():
        paths = [base / name for name in sample_names]
    else:
        print(
            'Running built-in preprocess smoke check.\n'
            'Pass one or more .cbl files, or set CARDDEMO_CBL_DIR, to parse '
            'real samples.'
        )
        print(preprocess(SMOKE_SOURCE), end='')
        return 0

    for path in paths:
        if not path.exists():
            print(f'Sample program not found: {path}', file=sys.stderr)
            return 1

        src = path.read_text(encoding='utf-8', errors='replace')
        tree = parse(src)
        s = count_errors(tree.root_node)
        paras = extract_paragraphs(tree.root_node)
        got = {p[0].upper() for p in paras}
        truth = ground_truth_paragraphs(src)
        ifs = count_nodes_of(tree.root_node, {'if_statement'})
        evals = count_nodes_of(tree.root_node, {'evaluate_statement'})
        performs = count_nodes_of(tree.root_node, {'perform_statement'})
        print(f"{path.name:14s} ERROR={s['error']}/{s['total']} nodes | "
              f"paragraphs: found={len(paras)} truth={len(truth)} "
              f"missed={sorted(truth - got)[:3] or 'none'} | "
              f"IF={ifs} EVALUATE={evals} PERFORM={performs}")
        print(f"   sample: {[p for p in paras[:4]]}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
