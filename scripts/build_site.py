"""Build the project site (S1) from the repository's canonical files.

    python scripts/build_site.py --out site

Every number on the page is read from the benchmark files and
``data/eval/test/report.json`` at build time; nothing is typed in by hand.
The output directory is overwritten and is not committed.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval.report import gate_rows
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
REPORT = ROOT / "data" / "eval" / "test" / "report.json"
REPO_URL = "https://github.com/skittlegit/cobol"

CLASSES = [
    ("D1", "D1_stale_threshold", "Stale threshold", "A limit, rate, or deadline still holds a superseded value."),
    ("D2", "D2_missing_rule", "Missing rule", "A required check or outcome is absent from the reachable code."),
    ("D3", "D3_contradictory", "Contradiction", "Code does the opposite of the obligation, or one path undoes another."),
    ("D4", "D4_stale_reference_data", "Stale reference data", "A code list or table lacks or keeps entries the regulation changed."),
    ("D5", "D5_boundary_error", "Boundary error", "The right value with the wrong comparison at the edge (> vs >=)."),
    ("D6", "D6_dead_code", "Dead compliance code", "The compliance logic exists but can never run."),
    ("D7", "D7_conformant", "Conformant", "The code satisfies the clause; the detector must say so."),
]

E = html.escape


def load_rows(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def benchmark_stats() -> dict[str, Any]:
    splits = {name: load_rows(BENCHMARK / f"{name}.jsonl") for name in ("train", "dev", "test")}
    temporal_rows = load_rows(BENCHMARK / "temporal" / "rows.jsonl")
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8"))
    return {
        "splits": {
            name: {
                "rows": len(rows),
                "interprocedural": sum(r.code_locus.is_interprocedural for r in rows),
                "real": sum(r.provenance.source != "synthetic" for r in rows),
                "classes": Counter(r.drift_type for r in rows),
            }
            for name, rows in splits.items()
        },
        "temporal_pairs": len(pairs),
        "temporal_targets": Counter(p["authority_target"] for p in pairs.values()),
        "temporal_rows": len(temporal_rows),
    }


def results_section(report: dict[str, Any]) -> str:
    decision = report["decision"]
    if decision == "NOT_EVALUABLE":
        outstanding = max((len(ids) for ids in report["missing_or_failed"].values()), default=0)
        status = (
            f"{outstanding} required rows have no result yet."
            if outstanding
            else report.get("reason", "").capitalize() + "."
        )
        return (
            '<div class="decision pending"><span class="label">Official result</span>'
            f"<strong>Pending</strong><p>{E(status)} The frozen "
            "detector is run once on the held-out test split and the temporal pairs; "
            "the gates below are fixed in advance.</p></div>"
            + gates_table_fixed(report["gates"])
        )
    rows = "".join(
        f"<tr><td>{E(name)}</td><td class=num>{E(measured)}</td>"
        f"<td class=num>{E(required)}</td>"
        f"<td class={'pass' if ok else 'fail'}>{'pass' if ok else 'fail'}</td></tr>"
        for name, measured, required, ok in gate_rows(report)
    )
    matrix = report["detector"]["confusion"]
    columns = list(next(iter(matrix.values())))
    head = "".join(f"<th>{E(c[:2] if c != 'ABSTAIN' else 'abst.')}</th>" for c in columns)
    body = "".join(
        f"<tr><th>{E(gold[:2])}</th>"
        + "".join(
            f"<td class='num{' diag' if gold == c else ''}'>{row[c]}</td>" for c in columns
        )
        + "</tr>"
        for gold, row in matrix.items()
    )
    return (
        f'<div class="decision {E(decision.lower())}"><span class="label">Official result</span>'
        f"<strong>{E(decision.replace('_', '-'))}</strong></div>"
        '<div class="scroll"><table><thead><tr><th>Gate</th><th>Measured</th>'
        f"<th>Required</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>"
        "<h3>Confusion matrix (gold rows, predicted columns)</h3>"
        f'<div class="scroll"><table class="matrix"><thead><tr><th></th>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def gates_table_fixed(gates: dict[str, Any]) -> str:
    rows = [
        ("Class F1 (T1)", f">= {gates['t1_f1']}"),
        ("Balanced accuracy", f">= {gates['balanced_accuracy']}"),
        ("Answer rate", f">= {gates['answer_rate']}"),
        ("Answered accuracy", f">= {gates['answered_accuracy']}"),
        (
            "Interprocedural F1 advantage over the RAG baseline",
            f">= +{gates['interprocedural_delta_f1']}, CI > 0, p < {gates['interprocedural_p']}",
        ),
        (
            "Temporal paired accuracy",
            f">= {gates['temporal_paired_accuracy']} on >= {gates['temporal_min_pairs']} pairs",
        ),
        ("Unverified findings emitted", "0"),
    ]
    body = "".join(f"<tr><td>{E(a)}</td><td class=num>{E(b)}</td></tr>" for a, b in rows)
    return (
        '<div class="scroll"><table><thead><tr><th>Gate</th><th>Required</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def benchmark_section(stats: dict[str, Any]) -> str:
    head = "".join(f"<th title='{E(name)}'>{code}</th>" for code, _, name, _ in CLASSES)
    body = ""
    for split, s in stats["splits"].items():
        cells = "".join(f"<td class=num>{s['classes'].get(key, 0)}</td>" for _, key, _, _ in CLASSES)
        body += (
            f"<tr><th>{split}</th><td class=num>{s['rows']}</td>"
            f"<td class=num>{s['interprocedural']}</td><td class=num>{s['real']}</td>{cells}</tr>"
        )
    targets = ", ".join(
        f"{E(t.replace('_', ' '))} ({n})" for t, n in sorted(stats["temporal_targets"].items())
    )
    return (
        '<div class="scroll"><table><thead><tr><th>Split</th><th>Rows</th>'
        f"<th>Cross-program</th><th>Hand-curated</th>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f"<p><strong>{stats['temporal_pairs']} temporal pairs</strong> "
        f"({stats['temporal_rows']} rows): one program, two versions of the same "
        "clause, opposite verdicts. A detector passes a pair only if it gets both "
        f"sides right. Targets: {targets}.</p>"
    )


def example_section() -> str:
    """A dev temporal pair: the same code is conformant, then stale."""

    rows = {r.instance_id: r for r in load_rows(BENCHMARK / "dev.jsonl")}
    old, new = rows["drift_120001"], rows["drift_120002"]
    source = (BENCHMARK / "seed" / "programs" / old.provenance.base_program).read_text(
        encoding="utf-8"
    )
    marked = {ref.line for ref in new.labels.line_level}
    code = "\n".join(
        f"<span class='ln'>{n:>3}</span>"
        + (f"<mark>{E(line)}</mark>" if n in marked else E(line))
        for n, line in enumerate(source.splitlines(), 1)
    )

    def clause_card(row: DriftInstance, verdict: str, css: str) -> str:
        c = row.regulation_clause
        return (
            f"<div class='card {css}'><div class='meta'>{E(c.doc)} {E(c.clause_id)} · "
            f"version {E(c.version)}</div><p>{E(c.text)}</p>"
            f"<div class='verdict'>{verdict}</div></div>"
        )

    return (
        f"<pre class='code'><code>{code}</code></pre>"
        "<div class='cards'>"
        + clause_card(old, "Conformant (D7)", "ok")
        + clause_card(new, "Stale threshold (D1), lines marked", "bad")
        + "</div>"
    )


def render(report: dict[str, Any], stats: dict[str, Any]) -> str:
    classes = "".join(
        f"<li><span class='code-tag'>{code}</span><strong>{E(name)}</strong> {E(text)}</li>"
        for code, _, name, text in CLASSES
    )
    steps = [
        ("Preprocess and parse", "A line-preserving cleaner masks EXEC blocks and expands COPY REPLACING; a tree-sitter COBOL grammar gives the AST, paragraphs, and copybooks. Every reported line is a line of the original file."),
        ("Investigate with tools", "The detector (gpt-6-luna through Codex) gets the clause and the source, never the label. It reads code through bounded tools: paragraphs, slices, call graph, cross-program def-use, and compile-and-run."),
        ("Verify every finding", "A finding counts only if it passes the verifier: executed under GnuCOBOL 3.2 (tier 1), shown statically (tier 2), and the claim entailed by the clause (DeBERTa NLI, a different model family). A class guard then checks the evidence each class needs."),
        ("Abstain otherwise", "A finding that fails verification becomes an abstention, never a guess. Answer rate and answered accuracy are both gates."),
    ]
    step_html = "".join(
        f"<li><h3>{E(title)}</h3><p>{E(text)}</p></li>" for title, text in steps
    )
    return TEMPLATE.format(
        classes=classes,
        steps=step_html,
        results=results_section(report),
        benchmark=benchmark_section(stats),
        example=example_section(),
        repo=REPO_URL,
    )


def build(out: Path, report: dict[str, Any] | None = None) -> Path:
    report = report or json.loads(REPORT.read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    page = out / "index.html"
    page.write_text(render(report, benchmark_stats()), encoding="utf-8", newline="\n")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return page


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>COBOL Archaeologist</title>
<meta name="description" content="Finding where legacy COBOL banking code has drifted from the regulation it was built to satisfy.">
<style>
:root {{
  --bg: #fbfaf7; --fg: #1d1c1a; --muted: #6b665d; --line: #e4e0d8; --card: #ffffff;
  --accent: #8a4b14; --ok: #2f6b3a; --bad: #9b2c1f; --mark: #fbe3b5; --code: #f4f1ea;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #161513; --fg: #ebe7df; --muted: #a39d92; --line: #2f2c27; --card: #1e1c19;
    --accent: #e0a467; --ok: #7cc48a; --bad: #f08a7a; --mark: #5a4319; --code: #201e1a;
    color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 960px; margin: 0 auto; padding: 0 20px; }}
header {{ padding: 72px 0 40px; border-bottom: 1px solid var(--line); }}
.eyebrow {{ font: 600 13px/1 ui-monospace, "SF Mono", Consolas, monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--accent); }}
h1 {{ font: 700 clamp(2.2rem, 6vw, 3.6rem)/1.05 Georgia, "Iowan Old Style", serif; margin: 14px 0 18px;
  letter-spacing: -.02em; }}
.lede {{ font-size: 1.2rem; color: var(--muted); max-width: 680px; margin: 0; }}
nav {{ display: flex; gap: 18px; flex-wrap: wrap; margin-top: 28px; font-size: 14px; }}
nav a {{ color: var(--fg); text-decoration: none; border-bottom: 1px solid var(--line); }}
nav a:hover {{ border-color: var(--accent); }}
section {{ padding: 56px 0 8px; }}
h2 {{ font: 700 1.7rem/1.2 Georgia, "Iowan Old Style", serif; margin: 0 0 18px; }}
h3 {{ font-size: 1rem; margin: 24px 0 8px; }}
p {{ max-width: 720px; }}
.classes {{ list-style: none; padding: 0; display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
.classes li {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
.classes strong {{ display: block; margin-bottom: 2px; }}
.code-tag {{ float: right; font: 600 12px ui-monospace, Consolas, monospace; color: var(--accent); }}
.steps {{ list-style: none; padding: 0; counter-reset: s; display: grid; gap: 4px; }}
.steps li {{ counter-increment: s; padding: 4px 0 4px 52px; position: relative; }}
.steps li::before {{ content: counter(s); position: absolute; left: 0; top: 18px; width: 32px; height: 32px;
  border-radius: 50%; border: 1px solid var(--accent); color: var(--accent); display: grid;
  place-items: center; font: 600 14px ui-monospace, Consolas, monospace; }}
.steps h3 {{ margin-top: 18px; }}
.steps p {{ margin: 0; color: var(--muted); }}
.scroll {{ overflow-x: auto; margin: 14px 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; background: var(--card); }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }}
thead th {{ font-weight: 600; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
td.num {{ font-variant-numeric: tabular-nums; }}
td.pass {{ color: var(--ok); font-weight: 600; }} td.fail {{ color: var(--bad); font-weight: 600; }}
.matrix td.diag {{ font-weight: 700; color: var(--accent); }}
.decision {{ border: 1px solid var(--line); border-left: 4px solid var(--accent); background: var(--card);
  padding: 16px 20px; border-radius: 6px; margin-bottom: 8px; }}
.decision .label {{ display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
.decision strong {{ font: 700 1.6rem/1.3 Georgia, serif; }}
.decision.go {{ border-left-color: var(--ok); }} .decision.no_go {{ border-left-color: var(--bad); }}
.decision p {{ margin: 6px 0 0; color: var(--muted); }}
pre.code {{ background: var(--code); border: 1px solid var(--line); border-radius: 8px; padding: 14px 0;
  overflow-x: auto; font: 13px/1.5 ui-monospace, "SF Mono", Consolas, monospace; }}
pre.code code {{ display: block; padding: 0 16px; white-space: pre; }}
.ln {{ color: var(--muted); user-select: none; margin-right: 14px; }}
mark {{ background: var(--mark); color: inherit; }}
.cards {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
.card .meta {{ font: 12px ui-monospace, Consolas, monospace; color: var(--muted); }}
.card p {{ font-size: 14px; }}
.card .verdict {{ font-weight: 700; }}
.card.ok .verdict {{ color: var(--ok); }} .card.bad .verdict {{ color: var(--bad); }}
pre.cmd {{ background: var(--code); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px;
  overflow-x: auto; font: 13px/1.6 ui-monospace, Consolas, monospace; }}
footer {{ margin-top: 64px; padding: 28px 0 48px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }}
a {{ color: var(--accent); }}
</style>
</head>
<body>
<header><div class="wrap">
  <div class="eyebrow">Regulatory drift in legacy banking code</div>
  <h1>COBOL Archaeologist</h1>
  <p class="lede">Finding where decades-old COBOL has drifted from the regulation it was
  built to satisfy, with every finding pinned to source lines and verified before it counts.</p>
  <nav><a href="#results">Result</a><a href="#classes">Drift classes</a><a href="#how">How it works</a>
  <a href="#benchmark">Benchmark</a><a href="#example">Example</a><a href="#reproduce">Reproduce</a>
  <a href="{repo}">Code</a></nav>
</div></header>
<main class="wrap">
<section id="results"><h2>Result</h2>{results}</section>
<section id="classes"><h2>What counts as drift</h2>
<p>Each benchmark row pairs a COBOL program with one regulation clause, pinned to a
version and effective date. The anchor regulations are the RBI Credit Card and Debit
Card Directions, 2025 and the RBI KYC Directions, 2025.</p>
<ul class="classes">{classes}</ul></section>
<section id="how"><h2>How it works</h2><ol class="steps">{steps}</ol></section>
<section id="benchmark"><h2>Benchmark</h2>
<p>Synthetic rows are mutations of AWS CardDemo and purpose-written seed programs, each
compiled and behaviour-checked, with benign edits mixed in so edit artifacts do not
give the answer away. The test split uses programs that appear in no other split.</p>
{benchmark}</section>
<section id="example"><h2>Example: same code, two verdicts</h2>
<p>This program was correct when it was written. The threshold it encodes was lowered
in 2023, so under the current clause the marked lines are stale.</p>
{example}</section>
<section id="reproduce"><h2>Reproduce</h2>
<pre class="cmd">pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q
python -m cobol_archaeologist.eval.runner detector --split test
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.report --split test</pre></section>
</main>
<footer><div class="wrap">Corpora: AWS CardDemo (Apache-2.0) and IBM CICS CBSA (EPL-2.0), fetched at
pinned commits, not redistributed. Regulation texts: Reserve Bank of India, pinned by SHA-256.
Built from the repository's result files by <code>scripts/build_site.py</code>.</div></footer>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    print(build(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
