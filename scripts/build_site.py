"""Build the project site (S1) from the repository's canonical files.

    python scripts/build_site.py --out site

Every number on the page is read at build time from
``data/eval/test/report.json`` and the benchmark files; nothing is typed in by
hand. The output directory is overwritten and is not committed.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval.report import GATES, gate_rows
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
REPORT = ROOT / "data" / "eval" / "test" / "report.json"
REPO_URL = "https://github.com/skittlegit/cobol"

E = html.escape

CLASSES = [
    ("D1", "D1_stale_threshold", "Stale threshold",
     "A limit, rate, deadline, or basis still holds a superseded value."),
    ("D2", "D2_missing_rule", "Missing rule",
     "A required check or outcome is absent from reachable code."),
    ("D3", "D3_contradictory", "Contradiction",
     "Code permits what the clause forbids, or a gate is neutralised."),
    ("D4", "D4_stale_reference_data", "Stale reference data",
     "A code list lacks or keeps entries the regulation changed."),
    ("D5", "D5_boundary_error", "Boundary error",
     "Right value, wrong comparison at the edge: > where >= is meant."),
    ("D6", "D6_dead_code", "Dead compliance code",
     "The compliance logic is there but can never execute."),
    ("D7", "D7_conformant", "Conformant",
     "The code satisfies the clause, and the detector must say so."),
]
CLASS_COLOR = {code: f"var(--c{code[1]})" for code, *_ in CLASSES}

# The evaluation record. Decisions only; every number shown comes from the
# current report. Earlier runs and their numbers are in STATUS.md.
HISTORY = [
    ("E1", "NO_GO", ("First official run. The temporal gate missed by one pair; "
      "several temporal programs turned out to omit part of their clause.")),
    ("E2", "GO", ("Same detector after correcting those programs. A post-hoc "
      "re-evaluation of a repaired benchmark, not a first look.")),
    ("E3", None, ("Fresh test split and fresh temporal pairs, written and checked "
      "before the run, with the same frozen detector.")),
]
CURRENT = "E3"


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_rows(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def benchmark_stats() -> dict[str, Any]:
    splits = {
        name: load_rows(BENCHMARK / f"{name}.jsonl") for name in ("train", "dev", "test")
    }
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8"))
    return {
        "splits": {
            name: {
                "rows": len(rows),
                "cross": sum(r.code_locus.is_interprocedural for r in rows),
                "classes": Counter(r.drift_type for r in rows),
            }
            for name, rows in splits.items()
        },
        "pairs": len(pairs),
        "targets": Counter(p["authority_target"] for p in pairs.values()),
    }


def pct(value: float) -> str:
    return f"{value * 100:.1f}"


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------
def hero_excavation() -> str:
    """A dev temporal pair: one program judged under two versions of a clause."""

    rows = {r.instance_id: r for r in load_rows(BENCHMARK / "dev.jsonl")}
    old, new = rows["drift_120001"], rows["drift_120002"]
    source = (BENCHMARK / "seed" / "programs" / old.provenance.base_program).read_text(
        encoding="utf-8"
    )
    marked = {ref.line for ref in new.labels.line_level}
    lines = []
    for number, text in enumerate(source.splitlines(), 1):
        cls = " class=hit" if number in marked else ""
        body = text[6:] if len(text) > 6 else text
        lines.append(f"<span{cls}><i>{number:02d}</i>{E(body)}</span>")
    old_value = old.regulation_clause.current_value.value
    new_value = new.regulation_clause.current_value.value
    return f"""
<figure class="dig" aria-label="Example: the same program under two versions of a regulation">
  <figcaption><span>{E(old.provenance.base_program)}</span><span class=tag>excavated</span></figcaption>
  <pre><code>{"".join(lines)}</code></pre>
  <div class="finds">
    <div class="find ok"><b>KYC rule as of {E(old.regulation_clause.version)}</b>owner above {old_value}%<em>conformant</em></div>
    <div class="find bad"><b>KYC rule as of {E(new.regulation_clause.version)}</b>owner above {new_value}%<em>D1 · stale threshold</em></div>
  </div>
</figure>"""


def stat_strip(report: dict[str, Any], stats: dict[str, Any]) -> str:
    test = stats["splits"]["test"]
    items = [
        (str(test["rows"]), "held-out test rows"),
        (str(test["cross"]), "cross-program cases"),
        (str(stats["pairs"]), "temporal pairs"),
        ("7", "drift classes"),
    ]
    if report.get("decision") not in (None, "NOT_EVALUABLE"):
        unverified = "0" if report["gate_results"]["zero_unverified_findings"] else "≥1"
        items.append((unverified, "unverified findings emitted"))
    return "<div class=strip>" + "".join(
        f"<div><strong>{E(v)}</strong><span>{E(k)}</span></div>" for v, k in items
    ) + "</div>"


def meter(value: float, threshold: float, ok: bool) -> str:
    v = max(0.0, min(1.0, value)) * 100
    t = max(0.0, min(1.0, threshold)) * 100
    return (
        f"<div class=meter role=img aria-label='{value:.3f}, required {threshold:g}'>"
        f"<div class='fill {'ok' if ok else 'bad'}' style='width:{v:.1f}%'></div>"
        f"<div class=bar-tick style='left:{t:.1f}%'><span>{threshold:g}</span></div></div>"
    )


def gate_card(label: str, value_html: str, visual: str, required: str, ok: bool,
              wide: bool = False) -> str:
    state = "pass" if ok else "fail"
    return (
        f"<div class='gate {state}{' wide' if wide else ''}'>"
        f"<div class=gh><span>{E(label)}</span><b>{state}</b></div>"
        f"<div class=gv>{value_html}</div>{visual}<div class=gr>{required}</div></div>"
    )


def results_section(report: dict[str, Any]) -> str:
    decision = report["decision"]
    if decision == "NOT_EVALUABLE":
        outstanding = max(
            (len(ids) for ids in report.get("missing_or_failed", {}).values()), default=0
        )
        status = (
            f"{outstanding} required rows have no result yet."
            if outstanding
            else report.get("reason", "").capitalize() + "."
        )
        return (
            f"<div class='verdict pending'><span class=k>{CURRENT} · official result</span>"
            f"<strong>Pending</strong><p>{E(status)} The gates are fixed in advance.</p></div>"
        )

    rows = gate_rows(report)  # (name, measured, required, passed), report order
    t1 = report["detector"]["t1"]
    gates = report.get("gates") or GATES
    comp = report.get("interprocedural_comparison") or {}
    temporal = report["temporal"]

    cards = []
    simple = [
        (0, "Class F1", t1["f1"], gates["t1_f1"]),
        (1, "Balanced accuracy", t1["balanced_accuracy"], gates["balanced_accuracy"]),
        (2, "Answer rate", t1["answer_rate"], gates["answer_rate"]),
        (3, "Answered accuracy", t1["answered_accuracy"], gates["answered_accuracy"]),
    ]
    for index, label, value, threshold in simple:
        ok = rows[index][3]
        cards.append(gate_card(label, f"{value:.3f}", meter(value, threshold, ok),
                               E(rows[index][2]), ok))

    ok = rows[5][3]
    cards.append(gate_card(
        "Temporal paired accuracy",
        f"{temporal['successes']}/{temporal['pairs']} <small>= {temporal['paired_accuracy']:.3f}</small>",
        meter(temporal["paired_accuracy"], gates["temporal_paired_accuracy"], ok),
        E(rows[5][2]), ok,
    ))

    ok = rows[4][3]
    delta = comp.get("delta_f1", 0.0)
    low, high = comp.get("bootstrap_95_ci", [0.0, 0.0])
    axis_lo, axis_hi = -0.2, 0.5

    def x(v: float) -> float:
        return max(0.0, min(100.0, (v - axis_lo) / (axis_hi - axis_lo) * 100))

    need = gates["interprocedural_delta_f1"]
    interval = (
        f"<div class=ci role=img aria-label='difference {delta:+.3f}, 95% interval {low:.3f} to {high:.3f}'>"
        f"<div class=zero style='left:{x(0):.1f}%'><span>0</span></div>"
        f"<div class=need style='left:{x(need):.1f}%'><span>+{need:g} needed</span></div>"
        f"<div class=range style='left:{x(low):.1f}%;width:{x(high) - x(low):.1f}%'></div>"
        f"<div class=dot style='left:{x(delta):.1f}%'></div></div>"
    )
    cards.append(gate_card(
        "Cross-program F1 advantage over the RAG baseline",
        f"{delta:+.3f} <small>95% CI {low:.3f}–{high:.3f} · p = "
        f"{comp.get('paired_randomization_p', float('nan')):.4f} · n = {comp.get('paired_rows', 0)}</small>",
        interval,
        f"detector F1 {comp.get('left_f1', 0):.3f} vs baseline {comp.get('right_f1', 0):.3f} · "
        f"{E(rows[4][2])}",
        ok, wide=True,
    ))

    ok = rows[6][3]
    cards.append(gate_card(
        "Unverified findings emitted", "0" if ok else "≥1", "",
        "Every finding passed the verifier and the class guard; a rejected finding "
        "becomes an abstention.",
        ok,
    ))

    passed = sum(1 for *_, good in rows if good)
    return (
        f"<div class='verdict {decision.lower()}'><span class=k>{CURRENT} · official result</span>"
        f"<strong>{E(decision.replace('_', '-'))}</strong>"
        f"<p>{passed} of {len(rows)} gates pass. The gates were fixed before the run.</p></div>"
        f"<div class=gates>{''.join(cards)}</div>"
        "<div class=sr-only><table><caption>Gate results</caption><thead><tr><th>Gate</th>"
        "<th>Measured</th><th>Required</th><th>Pass</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{E(n)}</td><td>{E(m)}</td><td>{E(r)}</td>"
            f"<td class={'pass' if o else 'fail'}>{'pass' if o else 'fail'}</td></tr>"
            for n, m, r, o in rows
        )
        + "</tbody></table></div>"
    )


def class_chart(report: dict[str, Any]) -> str:
    det = report["detector"].get("t3", {}).get("per_class", {})
    base = (report.get("rag_reranker") or {}).get("t3", {}).get("per_class", {})
    rows = []
    for code, key, name, _ in CLASSES:
        d, b = det.get(key, {}), base.get(key, {})
        df, bf = d.get("f1", 0.0), b.get("f1", 0.0)
        rows.append(
            f"<div class=crow><span class=cname><i style='background:{CLASS_COLOR[code]}'></i>"
            f"{code} {E(name)}<small>n = {d.get('support', 0)}</small></span>"
            f"<div class=cbars><div class='cb det' style='width:{df * 100:.1f}%'><span>{df:.2f}</span></div>"
            f"<div class='cb base' style='width:{bf * 100:.1f}%'><span>{bf:.2f}</span></div></div></div>"
        )
    return (
        "<div class=legend><span><i class=det></i>Detector</span>"
        "<span><i class=base></i>RAG reranker baseline</span>"
        "<span class=hint>F1 per class, test split</span></div>"
        "<div class=classchart>" + "".join(rows) + "</div>"
    )


def heatmap(report: dict[str, Any]) -> str:
    matrix = report["detector"]["confusion"]
    cols = sorted(next(iter(matrix.values())), key=lambda c: (c == "ABSTAIN", c))
    head = "".join(f"<th>{E(c[:2] if c != 'ABSTAIN' else 'ab')}</th>" for c in cols)
    body = []
    for gold, row in matrix.items():
        total = sum(row.values()) or 1
        cells = "".join(
            f"<td class='hm{' diag' if c == gold else ''}' style='--a:{row[c] / total:.3f}' "
            f"title='{E(gold[:2])} predicted {E(c[:2])}: {row[c]}'>{row[c] or ''}</td>"
            for c in cols
        )
        body.append(f"<tr><th>{E(gold[:2])}</th>{cells}</tr>")
    return (
        "<div class=scroll><table class=heat><caption>True class (rows) by predicted class "
        f"(columns)</caption><thead><tr><th></th>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def localisation(report: dict[str, Any]) -> str:
    t2 = report["detector"].get("t2", {})
    tiers = report["detector"].get("t4_faithfulness", {}).get("per_tier", {})
    loc_items = [
        ("Program", t2.get("program", {}).get("accuracy@1", 0.0)),
        ("Paragraph", t2.get("paragraph", {}).get("accuracy@1", 0.0)),
        ("Line", t2.get("line", {}).get("accuracy@1", 0.0)),
    ]
    loc = "".join(
        f"<div class=lrow><span>{n}</span><div class=lbar><div style='width:{v * 100:.1f}%'></div>"
        f"</div><b>{pct(v)}%</b></div>"
        for n, v in loc_items
    )
    names = {"1": "Executed (tier 1)", "2": "Static (tier 2)", "3": "Entailment (tier 3)"}
    tier_rows = "".join(
        f"<div class=lrow><span>{names.get(k, k)}</span><div class=lbar><div style='width:"
        f"{v['faithfulness'] * 100:.1f}%'></div></div><b>n = {v['n']}</b></div>"
        for k, v in sorted(tiers.items())
    )
    return (
        "<div class=twocol><div><h3>Localisation</h3><p class=note>Top-1 accuracy of the cited "
        f"location.</p>{loc}</div><div><h3>Verification tier</h3><p class=note>Faithfulness of "
        "emitted findings, by the strongest evidence that verified them.</p>"
        f"{tier_rows}</div></div>"
    )


def temporal_grid(report: dict[str, Any]) -> str:
    temporal = report.get("temporal", {})
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8"))
    cells = "".join(
        f"<span class='tp {'ok' if ok else 'no'}' title='{E(name)} · "
        f"{E(pairs.get(name, {}).get('authority_target', '').replace('_', ' '))}'>"
        f"{E(name[-2:])}</span>"
        for name, ok in temporal.get("per_pair", {}).items()
    )
    low, high = temporal.get("exact_95_ci", [0.0, 0.0])
    return (
        f"<div class=tgrid>{cells}</div><p class=note>{temporal.get('successes', 0)} of "
        f"{temporal.get('pairs', 0)} pairs right on both sides (exact 95% interval {pct(low)}–"
        f"{pct(high)}%). A pair counts only if the old side is called conformant and the new "
        "side drifted.</p>"
    )


def benchmark_section(stats: dict[str, Any]) -> str:
    bars = []
    for split, s in stats["splits"].items():
        total = s["rows"] or 1
        segments = "".join(
            f"<span style='width:{s['classes'].get(key, 0) / total * 100:.2f}%;"
            f"background:{CLASS_COLOR[code]}' title='{code}: {s['classes'].get(key, 0)}'></span>"
            for code, key, _, _ in CLASSES
        )
        bars.append(
            f"<div class=split><div class=sh><b>{split}</b><span>{s['rows']} rows · "
            f"{s['cross']} cross-program</span></div><div class=stack>{segments}</div></div>"
        )
    legend = "".join(
        f"<span><i style='background:{CLASS_COLOR[c]}'></i>{c}</span>" for c, *_ in CLASSES
    )
    targets = "".join(
        f"<li><b>{n}</b>{E(t.replace('_', ' '))}</li>"
        for t, n in sorted(stats["targets"].items())
    )
    return (
        f"<div class=splits>{''.join(bars)}<div class=legend>{legend}</div></div>"
        "<div class=twocol><div><h3>How rows are made</h3><p>Synthetic rows are mutations of "
        "AWS CardDemo and purpose-written programs: stale constants, removed checks, "
        "neutralised gates, trimmed reference lists, flipped comparators, and disabled guard "
        "flags, including cross-program variants through copybooks, called modules, and batch "
        "steps. Benign edits are mixed in so the edit never gives the answer away. Each row "
        "is its base program plus the exact diff, and every one compiles under GnuCOBOL 3.2."
        "</p></div><div><h3>Temporal pairs</h3><p>One program, two versions of the same KYC "
        "clause. The program keeps the 2016 threshold: conformant then, stale now.</p>"
        f"<ul class=targets>{targets}</ul></div></div>"
    )


def classes_section() -> str:
    return "<ol class=strata>" + "".join(
        f"<li style='--c:{CLASS_COLOR[code]}'><span class=code>{code}</span>"
        f"<div><b>{E(name)}</b><p>{E(text)}</p></div></li>"
        for code, _, name, text in CLASSES
    ) + "</ol>"


def method_section() -> str:
    steps = [
        ("01", "Clean", "Mask EXEC blocks, expand COPY REPLACING, keep every original line number."),
        ("02", "Map", "tree-sitter AST, paragraphs, copybooks, call graph, cross-program def-use."),
        ("03", "Investigate", ("gpt-6-luna reads the clause and the code through bounded tools: "
          "slices, traces, grep, compile-and-run.")),
        ("04", "Verify", ("Executed under GnuCOBOL or shown statically, and entailed by the clause "
          "(DeBERTa NLI, another model family).")),
        ("05", "Guard", ("A class-specific evidence check. Anything that fails becomes an "
          "abstention, never a guess.")),
    ]
    return "<ol class=pipeline>" + "".join(
        f"<li><span class=n>{n}</span><b>{E(t)}</b><p>{E(d)}</p></li>" for n, t, d in steps
    ) + "</ol>"


def history_section(report: dict[str, Any]) -> str:
    items = []
    for run, decision, text in HISTORY:
        shown = decision or report.get("decision", "NOT_EVALUABLE")
        cls = {"GO": "go", "NO_GO": "no_go"}.get(shown, "pending")
        current = " current" if run == CURRENT else ""
        label = "PENDING" if shown == "NOT_EVALUABLE" else shown.replace("_", "-")
        items.append(
            f"<li class='{cls}{current}'><span class=run>{run}</span>"
            f"<span class=dec>{E(label)}</span><p>{E(text)}</p></li>"
        )
    return "<ol class=history>" + "".join(items) + "</ol>"


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------
def render(report: dict[str, Any], stats: dict[str, Any]) -> str:
    detail = ""
    if report.get("decision") not in (None, "NOT_EVALUABLE"):
        detail = (
            "<section id=per-class><div class=wrap><div class=eyebrow>Per class</div>"
            "<h2>Where it is strong, and where it is not</h2>"
            f"{class_chart(report)}<div class='twocol wide'><div>{heatmap(report)}</div>"
            "<div><h3>Reading the matrix</h3><p>Rows are the true class, columns what the "
            "detector said; the diagonal is right. Dead compliance code (D6) is the hardest "
            "class: the evidence lives in another program, and the detector has to show the "
            "guarded step can never run.</p></div></div>"
            f"{localisation(report)}</div></section>"
            "<section id=temporal><div class=wrap><div class=eyebrow>Temporal pairs</div>"
            f"<h2>Same code, different law</h2>{temporal_grid(report)}</div></section>"
        )
    return PAGE.format(
        hero=hero_excavation(),
        strip=stat_strip(report, stats),
        results=results_section(report),
        detail=detail,
        method=method_section(),
        classes=classes_section(),
        benchmark=benchmark_section(stats),
        history=history_section(report),
        repo=REPO_URL,
        current=CURRENT,
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


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>COBOL Archaeologist</title>
<meta name="description" content="A detector and benchmark for finding where legacy COBOL banking code has drifted from the regulation it was built to satisfy.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:ital,wght@0,500;0,600;1,500&display=swap" rel="stylesheet">
<style>
:root {{
  --paper: #f5f1e6; --paper2: #e9e2d0; --ink: #1c1b17; --muted: #6b6455; --rule: #d9d0bb;
  --card: #fbf8f0; --bar: #e3ecd9; --amber: #a8521b;
  --go: #2d7a4c; --nogo: #b3261e; --pend: #8a6d1f; --hit: #f6d9a4;
  --c1: #b35b1e; --c2: #6e4fb0; --c3: #c23838; --c4: #2c79a6; --c5: #b98a0a; --c6: #4f6470; --c7: #2d7a4c;
  --det: #a8521b; --base: #c4b99f;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --paper: #11130f; --paper2: #20241d; --ink: #e9e5d8; --muted: #9b9584; --rule: #2b2f27;
    --card: #181b16; --bar: #1a2419; --amber: #f0a24a;
    --go: #79d39a; --nogo: #ff8a7a; --pend: #e8c46a; --hit: #4a3712;
    --c1: #f0a24a; --c2: #b49cf0; --c3: #ff8a7a; --c4: #6cc0ec; --c5: #ecc95a; --c6: #9fb3bd; --c7: #79d39a;
    --det: #f0a24a; --base: #5d5a4d;
    color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.65 "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; }}
a {{ color: var(--amber); text-underline-offset: 3px; }}
code, pre {{ font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace; }}
.sr-only {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
.eyebrow {{ font: 500 12px/1 "IBM Plex Mono", ui-monospace, monospace; letter-spacing: .14em; text-transform: uppercase; color: var(--amber); margin-bottom: 14px; }}
h1, h2 {{ font-family: "IBM Plex Serif", Georgia, serif; font-weight: 600; letter-spacing: -.015em; }}
h2 {{ font-size: clamp(1.7rem, 3.2vw, 2.4rem); line-height: 1.15; margin: 0 0 28px; max-width: 760px; }}
h3 {{ font-size: 1rem; margin: 0 0 10px; }}
p {{ margin: 0 0 14px; }}
.note {{ color: var(--muted); font-size: 14px; }}

nav.top {{ position: sticky; top: 0; z-index: 10; padding-top: env(safe-area-inset-top, 0px);
  background: color-mix(in srgb, var(--paper) 88%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--rule); }}
nav.top .wrap {{ display: flex; align-items: center; gap: 22px; height: 56px; font-size: 14px; }}
nav.top .brand {{ font: 600 14px "IBM Plex Mono", ui-monospace, monospace; color: var(--ink); text-decoration: none; margin-right: auto; }}
nav.top .brand::before {{ content: "\\25A0  "; color: var(--amber); }}
nav.top a.l {{ color: var(--muted); text-decoration: none; }}
nav.top a.l:hover {{ color: var(--ink); }}
@media (max-width: 760px) {{ nav.top a.l {{ display: none; }} nav.top a.l.gh {{ display: inline; }} }}

header.hero {{ padding: 72px 0 40px; border-bottom: 1px solid var(--rule);
  background: repeating-linear-gradient(180deg, transparent 0 34px, color-mix(in srgb, var(--bar) 55%, transparent) 34px 68px); }}
.hero .grid {{ display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); gap: 56px; align-items: center; }}
.hero .grid > *, .twocol > *, .gates > *, .crow > * {{ min-width: 0; }}
@media (max-width: 920px) {{ .hero .grid {{ grid-template-columns: minmax(0, 1fr); gap: 36px; }} }}
h1 {{ font-size: clamp(2.6rem, 6vw, 4.4rem); line-height: 1.02; margin: 0 0 22px; }}
h1 em {{ font-style: italic; color: var(--amber); }}
.lede {{ font-size: 1.15rem; color: var(--muted); max-width: 540px; }}
.cta {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 26px; }}
.btn {{ display: inline-flex; align-items: center; padding: 10px 16px; border-radius: 6px; font: 500 14px "IBM Plex Mono", ui-monospace, monospace;
  text-decoration: none; border: 1px solid var(--ink); color: var(--ink); transition: transform .15s; }}
.btn.primary {{ background: var(--ink); color: var(--paper); }}
.btn:hover {{ transform: translateY(-1px); }}

.dig {{ margin: 0; background: var(--card); border: 1px solid var(--rule); border-radius: 10px; overflow: hidden;
  box-shadow: 0 18px 40px -24px rgba(0,0,0,.35); }}
.dig figcaption {{ display: flex; justify-content: space-between; padding: 10px 16px; border-bottom: 1px dashed var(--rule);
  font: 500 12px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); }}
.dig .tag {{ color: var(--amber); text-transform: uppercase; letter-spacing: .12em; }}
.dig pre {{ margin: 0; padding: 10px 0; font-size: 12.5px; line-height: 1.6; overflow-x: auto; }}
.dig code {{ display: block; }}
.dig code span {{ display: block; padding: 0 16px; white-space: pre; }}
.dig code span:nth-child(4n+3), .dig code span:nth-child(4n+4) {{ background: color-mix(in srgb, var(--bar) 70%, transparent); }}
.dig code i {{ font-style: normal; color: var(--muted); opacity: .6; margin-right: 14px; user-select: none; }}
.dig code span.hit {{ background: var(--hit); box-shadow: inset 3px 0 0 var(--amber); }}
.finds {{ display: grid; grid-template-columns: 1fr 1fr; border-top: 1px dashed var(--rule); }}
.find {{ padding: 12px 16px; font: 12.5px/1.5 "IBM Plex Mono", ui-monospace, monospace; }}
.find + .find {{ border-left: 1px dashed var(--rule); }}
.find b {{ display: block; color: var(--muted); font-weight: 500; }}
.find em {{ font-style: normal; display: block; font-weight: 600; margin-top: 2px; }}
.find.ok em {{ color: var(--go); }} .find.bad em {{ color: var(--nogo); }}

.strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(150px, 45%), 1fr)); margin-top: 48px; border-top: 1px solid var(--rule); }}
.strip div {{ padding: 18px 4px 0; }}
.strip strong {{ display: block; font: 600 2rem/1 "IBM Plex Serif", Georgia, serif; }}
.strip span {{ font-size: 13px; color: var(--muted); }}

section {{ padding: 88px 0 24px; }}
section + section {{ border-top: 1px solid var(--rule); }}
.twocol {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 40px; }}
.twocol.wide {{ grid-template-columns: 1.3fr 1fr; align-items: start; }}
@media (max-width: 820px) {{ .twocol, .twocol.wide {{ grid-template-columns: 1fr; }} }}

.verdict {{ display: grid; grid-template-columns: auto 1fr; align-items: baseline; gap: 6px 28px; padding: 26px 28px; border-radius: 12px;
  background: var(--card); border: 1px solid var(--rule); border-left: 6px solid var(--pend); margin-bottom: 22px; }}
.verdict .k {{ grid-column: 1 / -1; font: 500 12px "IBM Plex Mono", ui-monospace, monospace; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
.verdict strong {{ font: 600 clamp(2.6rem, 6vw, 3.6rem)/1 "IBM Plex Serif", Georgia, serif; color: var(--pend); }}
.verdict p {{ margin: 0; color: var(--muted); }}
.verdict.go {{ border-left-color: var(--go); }} .verdict.go strong {{ color: var(--go); }}
.verdict.no_go {{ border-left-color: var(--nogo); }} .verdict.no_go strong {{ color: var(--nogo); }}
@media (max-width: 640px) {{ .verdict {{ grid-template-columns: 1fr; }} }}
.gates {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 14px; }}
.gate {{ background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 16px 18px 16px; }}
.gate.wide {{ grid-column: span 2; }}
@media (max-width: 560px) {{ .gate.wide {{ grid-column: auto; }} }}
.gh {{ display: flex; justify-content: space-between; gap: 10px; font-size: 13px; color: var(--muted); }}
.gh b {{ font: 600 11px "IBM Plex Mono", ui-monospace, monospace; text-transform: uppercase; letter-spacing: .1em; padding: 2px 7px; border-radius: 4px; align-self: start; }}
.gate.pass .gh b {{ color: var(--go); background: color-mix(in srgb, var(--go) 14%, transparent); }}
.gate.fail .gh b {{ color: var(--nogo); background: color-mix(in srgb, var(--nogo) 14%, transparent); }}
.gate.fail {{ border-color: color-mix(in srgb, var(--nogo) 50%, var(--rule)); }}
.gv {{ font: 600 1.9rem/1.2 "IBM Plex Mono", ui-monospace, monospace; margin: 8px 0 12px; font-variant-numeric: tabular-nums; }}
.gv small {{ font-size: 12px; font-weight: 400; color: var(--muted); margin-left: 6px; }}
.gr {{ font: 12px/1.5 "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); margin-top: 22px; }}
.meter {{ position: relative; height: 8px; border-radius: 4px; background: var(--paper2); }}
.meter .fill {{ height: 100%; border-radius: 4px; }}
.fill.ok {{ background: var(--go); }} .fill.bad {{ background: var(--nogo); }}
.bar-tick {{ position: absolute; top: -5px; bottom: -5px; width: 2px; background: var(--ink); }}
.bar-tick span {{ position: absolute; top: 18px; transform: translateX(-50%); font: 11px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); }}
.ci {{ position: relative; height: 26px; margin: 4px 0 8px; border-bottom: 1px solid var(--rule); }}
.ci .range {{ position: absolute; top: 9px; height: 8px; border-radius: 4px; background: color-mix(in srgb, var(--go) 35%, transparent); }}
.ci .dot {{ position: absolute; top: 6px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%; background: var(--go); border: 2px solid var(--card); }}
.ci .zero, .ci .need {{ position: absolute; top: 0; bottom: -6px; width: 1px; background: var(--muted); }}
.ci .need {{ background: var(--ink); width: 2px; }}
.ci .zero span, .ci .need span {{ position: absolute; top: 30px; transform: translateX(-50%); font: 11px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); white-space: nowrap; }}

.legend {{ display: flex; flex-wrap: wrap; gap: 8px 18px; font: 12px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); margin-bottom: 14px; }}
.legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }}
.legend i.det {{ background: var(--det); }} .legend i.base {{ background: var(--base); }}
.legend .hint {{ margin-left: auto; }}
.classchart {{ display: grid; gap: 12px; }}
.crow {{ display: grid; grid-template-columns: 230px 1fr; gap: 16px; align-items: center; }}
@media (max-width: 640px) {{ .crow {{ grid-template-columns: 1fr; gap: 4px; }} }}
.cname {{ font-size: 14px; }}
.cname i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }}
.cname small {{ color: var(--muted); margin-left: 8px; font: 11px "IBM Plex Mono", ui-monospace, monospace; }}
.cbars {{ display: grid; gap: 3px; padding-right: 48px; }}
.cb {{ height: 16px; border-radius: 3px; min-width: 2px; position: relative; }}
.cb.det {{ background: var(--det); }} .cb.base {{ background: var(--base); height: 9px; }}
.cb span {{ position: absolute; left: calc(100% + 8px); top: 50%; transform: translateY(-50%); font: 11px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); }}

.scroll {{ overflow-x: auto; }}
table.heat {{ border-collapse: separate; border-spacing: 3px; font: 12px "IBM Plex Mono", ui-monospace, monospace; }}
table.heat caption {{ text-align: left; color: var(--muted); margin-bottom: 8px; }}
table.heat th {{ color: var(--muted); font-weight: 500; padding: 4px 6px; }}
td.hm {{ width: 44px; height: 36px; text-align: center; border-radius: 4px; background: color-mix(in srgb, var(--nogo) calc(var(--a) * 85%), var(--paper2)); }}
td.hm.diag {{ background: color-mix(in srgb, var(--go) calc(var(--a) * 85%), var(--paper2)); font-weight: 600; }}

.lrow {{ display: grid; grid-template-columns: 150px 1fr 70px; gap: 12px; align-items: center; margin: 10px 0; font-size: 14px; }}
.lrow b {{ font: 500 12px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); text-align: right; }}
.lbar {{ height: 10px; background: var(--paper2); border-radius: 5px; overflow: hidden; }}
.lbar div {{ height: 100%; background: var(--amber); }}

.tgrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 6px; max-width: 760px; margin-bottom: 14px; }}
.tp {{ aspect-ratio: 1; display: grid; place-items: center; border-radius: 6px; font: 600 12px "IBM Plex Mono", ui-monospace, monospace; }}
.tp.ok {{ background: color-mix(in srgb, var(--go) 22%, var(--card)); color: var(--go); border: 1px solid color-mix(in srgb, var(--go) 40%, transparent); }}
.tp.no {{ background: color-mix(in srgb, var(--nogo) 16%, var(--card)); color: var(--nogo); border: 1px dashed var(--nogo); }}

.pipeline {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(5, 1fr); }}
@media (max-width: 920px) {{ .pipeline {{ grid-template-columns: 1fr; }} }}
.pipeline li {{ padding: 22px 20px 20px; border-top: 3px solid var(--ink); }}
.pipeline li + li {{ border-left: 1px solid var(--rule); }}
@media (max-width: 920px) {{ .pipeline li + li {{ border-left: 0; }} }}
.pipeline .n {{ font: 500 12px "IBM Plex Mono", ui-monospace, monospace; color: var(--amber); }}
.pipeline b {{ display: block; font: 600 1.15rem "IBM Plex Serif", Georgia, serif; margin: 6px 0 8px; }}
.pipeline p {{ font-size: 14px; color: var(--muted); margin: 0; }}

.strata {{ list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--rule); }}
.strata li {{ display: grid; grid-template-columns: 70px 1fr; gap: 16px; padding: 16px 0 14px 18px; border-bottom: 1px solid var(--rule); box-shadow: inset 4px 0 0 var(--c); }}
.strata .code {{ font: 600 1.2rem "IBM Plex Mono", ui-monospace, monospace; color: var(--c); }}
.strata p {{ margin: 2px 0 0; color: var(--muted); font-size: 14px; }}

.splits {{ display: grid; gap: 14px; }}
.split .sh {{ display: flex; justify-content: space-between; gap: 12px; font-size: 14px; margin-bottom: 6px; }}
.split .sh span {{ color: var(--muted); font: 12px "IBM Plex Mono", ui-monospace, monospace; }}
.stack {{ display: flex; height: 22px; border-radius: 4px; overflow: hidden; gap: 2px; }}
.stack span {{ display: block; height: 100%; }}
.targets {{ list-style: none; padding: 0; margin: 0; }}
.targets li {{ padding: 6px 0; border-bottom: 1px dashed var(--rule); }}
.targets li::first-letter {{ text-transform: uppercase; }}
.targets b {{ font-family: "IBM Plex Mono", ui-monospace, monospace; color: var(--amber); margin-right: 10px; }}

.history {{ list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
@media (max-width: 820px) {{ .history {{ grid-template-columns: 1fr; }} }}
.history li {{ background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 18px; }}
.history li.current {{ border-color: var(--ink); box-shadow: 0 0 0 1px var(--ink); }}
.history .run {{ font: 600 12px "IBM Plex Mono", ui-monospace, monospace; color: var(--muted); }}
.history .dec {{ display: block; font: 600 1.5rem "IBM Plex Serif", Georgia, serif; margin: 4px 0 8px; }}
.history .go .dec {{ color: var(--go); }} .history .no_go .dec {{ color: var(--nogo); }} .history .pending .dec {{ color: var(--pend); }}
.history p {{ font-size: 14px; color: var(--muted); margin: 0; }}

pre.cmd {{ background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 18px 20px; overflow-x: auto; font-size: 13px; line-height: 1.7; }}
pre.cmd .c {{ color: var(--muted); }}
footer {{ margin-top: 80px; padding: 32px 0 calc(48px + env(safe-area-inset-bottom, 0px)); border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
footer .wrap {{ display: flex; flex-wrap: wrap; gap: 12px 32px; justify-content: space-between; }}
</style>
</head>
<body>
<nav class=top><div class=wrap>
  <a class=brand href="#">cobol-archaeologist</a>
  <a class=l href="#result">Result</a><a class=l href="#method">Method</a><a class=l href="#classes">Drift classes</a>
  <a class=l href="#benchmark">Benchmark</a><a class=l href="#record">Record</a><a class="l gh" href="{repo}">GitHub</a>
</div></nav>

<header class=hero><div class=wrap>
  <div class=grid>
    <div>
      <div class=eyebrow>Regulatory drift in legacy banking code</div>
      <h1>The rule changed.<br><em>The COBOL didn’t.</em></h1>
      <p class=lede>COBOL Archaeologist finds where decades-old banking code has drifted from the regulation it was built to satisfy:
      stale thresholds, missing checks, contradictions, dead compliance code. Every finding is pinned to source lines
      and verified before it counts.</p>
      <div class=cta><a class="btn primary" href="#result">See the result</a><a class=btn href="{repo}">Read the code</a></div>
    </div>
    {hero}
  </div>
  {strip}
</div></header>

<main>
<section id=result><div class=wrap>
  <div class=eyebrow>Official evaluation</div>
  <h2>Gates fixed in advance, test data unseen before the run</h2>
  {results}
</div></section>

{detail}

<section id=method><div class=wrap>
  <div class=eyebrow>Method</div>
  <h2>An excavation, not a guess</h2>
  {method}
</div></section>

<section id=classes><div class=wrap>
  <div class=eyebrow>Taxonomy</div>
  <h2>Seven ways code and regulation can disagree</h2>
  <p class=note>Each case binds one COBOL program bundle to one clause of the RBI Credit Card and Debit Card Directions, 2025 or the RBI KYC Directions, 2025, pinned to a version and effective date.</p>
  {classes}
</div></section>

<section id=benchmark><div class=wrap>
  <div class=eyebrow>Benchmark</div>
  <h2>Built to be hard to shortcut</h2>
  {benchmark}
</div></section>

<section id=record><div class=wrap>
  <div class=eyebrow>Evaluation record</div>
  <h2>Every run is kept, including the ones that failed</h2>
  {history}
  <p class=note style="margin-top:18px">The current result is {current}. Earlier runs, their numbers, and what changed between them are in <a href="{repo}/blob/master/STATUS.md">STATUS.md</a>.</p>
</div></section>

<section id=reproduce><div class=wrap>
  <div class=eyebrow>Reproduce</div>
  <h2>Run it yourself</h2>
<pre class=cmd><span class=c># install, fetch the pinned corpora, run the offline suite</span>
pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q

<span class=c># the official run: detector, temporal pairs, baseline, report</span>
python -m cobol_archaeologist.eval.runner detector --split test
python -m cobol_archaeologist.eval.runner detector --split temporal
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.report --split test</pre>
</div></section>
</main>

<footer><div class=wrap>
  <span>Corpora: AWS CardDemo (Apache-2.0) and IBM CICS CBSA (EPL-2.0), fetched at pinned commits. Regulation texts: Reserve Bank of India, pinned by SHA-256.</span>
  <span>Generated from the repository’s result files by <code>scripts/build_site.py</code>.</span>
</div></footer>
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
