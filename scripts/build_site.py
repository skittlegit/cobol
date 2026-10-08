"""Export the project site's data (S1) from the repository's canonical files.

    python scripts/build_site.py            # writes web/src/site.json
    npm --prefix web ci && npm --prefix web run build   # renders it into site/

Every number the site shows is computed here, at build time, from
``data/eval/test/report.json`` and the benchmark files; the web app (React and
shadcn/ui under ``web/``) only lays it out. Gate strings come from
``eval/report.py:gate_rows``, the same function that writes ``report.md``.
Neither ``web/src/site.json`` nor ``site/`` is committed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval.report import GATES, gate_rows
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
REPORT = ROOT / "data" / "eval" / "test" / "report.json"
OUT = ROOT / "web" / "src" / "site.json"
REPO_URL = "https://github.com/skittlegit/cobol"

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

# The evaluation record. Decisions only; every number shown comes from the
# current report. E1's numbers are in docs/tasks/E1.md.
HISTORY = [
    ("E1", "NO_GO", ("First-look official run. The temporal gate missed by one pair; "
      "several temporal programs turned out to omit part of their clause.")),
    ("E2", None, ("After fixing what E1 exposed, on dev and new data only: corrected "
      "temporal and chain programs, realistic-size cross-program rows with "
      "conformant cases, and a detector tuned on dev, then frozen.")),
]
CURRENT = "E2"

# Display label per gate, in gate_rows order, keyed like report["gate_results"].
GATE_LABELS = [
    ("t1_f1", "Class F1"),
    ("balanced_accuracy", "Balanced accuracy"),
    ("answer_rate", "Answer rate"),
    ("answered_accuracy", "Answered accuracy"),
    ("interprocedural_advantage", "Cross-program F1 advantage over the RAG baseline"),
    ("temporal_paired_accuracy", "Temporal paired accuracy"),
    ("zero_unverified_findings", "Unverified findings emitted"),
]


def load_rows(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def benchmark() -> dict[str, Any]:
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8"))
    splits = []
    for name in ("train", "dev", "test"):
        rows = load_rows(BENCHMARK / f"{name}.jsonl")
        counts = Counter(r.drift_type for r in rows)
        splits.append({
            "name": name,
            "rows": len(rows),
            "cross": sum(r.code_locus.is_interprocedural for r in rows),
            "classes": {code: counts.get(key, 0) for code, key, *_ in CLASSES},
        })
    targets = Counter(p["authority_target"] for p in pairs.values())
    versions = sorted({r.regulation_clause.version for r in load_rows(BENCHMARK / "temporal" / "rows.jsonl")})
    return {
        "versions": versions,
        "splits": splits,
        "pairs": len(pairs),
        "targets": [
            {"name": t.replace("_", " "), "pairs": n} for t, n in sorted(targets.items())
        ],
    }


def excavation() -> dict[str, Any]:
    """A dev temporal pair: one program judged under two versions of a clause."""

    rows = {r.instance_id: r for r in load_rows(BENCHMARK / "dev.jsonl")}
    old, new = rows["drift_120001"], rows["drift_120002"]
    path = next((BENCHMARK / "seed" / "programs").rglob(old.provenance.base_program))
    marked = {ref.line for ref in new.labels.line_level}
    return {
        "program": old.provenance.base_program,
        "lines": [
            {"n": n, "text": text[6:] if len(text) > 6 else text, "hit": n in marked}
            for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        ],
        "old": {"version": old.regulation_clause.version,
                "value": old.regulation_clause.current_value.value},
        "new": {"version": new.regulation_clause.version,
                "value": new.regulation_clause.current_value.value},
    }


def results(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("decision", "NOT_EVALUABLE")
    if decision == "NOT_EVALUABLE":
        outstanding = max(
            (len(ids) for ids in (report.get("missing_or_failed") or {}).values()), default=0
        )
        status = (
            f"{outstanding} required rows have no result yet."
            if outstanding
            else (report.get("reason") or "").capitalize() + "."
        )
        return {"decision": decision, "status": status}

    gates = report.get("gates") or GATES
    t1 = report["detector"]["t1"]
    comp = report.get("interprocedural_comparison") or {}
    temporal = report["temporal"]
    values = [
        (t1["f1"], gates["t1_f1"]),
        (t1["balanced_accuracy"], gates["balanced_accuracy"]),
        (t1["answer_rate"], gates["answer_rate"]),
        (t1["answered_accuracy"], gates["answered_accuracy"]),
        (comp.get("delta_f1", 0.0), gates["interprocedural_delta_f1"]),
        (temporal["paired_accuracy"], gates["temporal_paired_accuracy"]),
        (None, None),
    ]
    rows = [
        {"key": key, "label": label, "name": name, "measured": measured,
         "required": required, "pass": passed, "value": value, "threshold": threshold}
        for (key, label), (name, measured, required, passed), (value, threshold)
        in zip(GATE_LABELS, gate_rows(report), values, strict=True)
    ]

    det = report["detector"].get("t3", {}).get("per_class", {})
    base = (report.get("rag_reranker") or {}).get("t3", {}).get("per_class", {})
    matrix = report["detector"]["confusion"]
    cols = sorted(next(iter(matrix.values())), key=lambda c: (c == "ABSTAIN", c))
    t2 = report["detector"].get("t2", {})
    tiers = report["detector"].get("t4_faithfulness", {}).get("per_tier", {})
    tier_names = {"1": "Executed (tier 1)", "2": "Static (tier 2)", "3": "Entailment (tier 3)"}
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text(encoding="utf-8"))
    return {
        "decision": decision,
        "passed": sum(1 for r in rows if r["pass"]),
        "gates": rows,
        "comparison": {
            "delta": comp.get("delta_f1", 0.0),
            "ci": comp.get("bootstrap_95_ci", [0.0, 0.0]),
            "p": comp.get("paired_randomization_p"),
            "n": comp.get("paired_rows", 0),
            "detector_f1": comp.get("left_f1", 0.0),
            "baseline_f1": comp.get("right_f1", 0.0),
            "need": gates["interprocedural_delta_f1"],
        },
        "per_class": [
            {"code": code, "name": name,
             "detector": det.get(key, {}).get("f1", 0.0),
             "baseline": base.get(key, {}).get("f1", 0.0),
             "support": det.get(key, {}).get("support", 0)}
            for code, key, name, _ in CLASSES
        ],
        "confusion": {
            "cols": [c[:2] if c != "ABSTAIN" else "ab" for c in cols],
            "rows": [
                {"gold": gold[:2], "cells": [
                    {"n": row[c], "share": row[c] / (sum(row.values()) or 1),
                     "diagonal": c == gold}
                    for c in cols
                ]}
                for gold, row in matrix.items()
            ],
        },
        "localisation": [
            {"name": name, "value": t2.get(key, {}).get("accuracy@1", 0.0)}
            for name, key in (("Program", "program"), ("Paragraph", "paragraph"),
                              ("Line", "line"))
        ],
        "tiers": [
            {"name": tier_names.get(k, k), "n": v["n"], "faithfulness": v["faithfulness"]}
            for k, v in sorted(tiers.items())
        ],
        "temporal": {
            "successes": temporal["successes"],
            "pairs": temporal["pairs"],
            "accuracy": temporal["paired_accuracy"],
            "ci": temporal.get("exact_95_ci", [0.0, 0.0]),
            "per_pair": [
                {"name": name, "ok": ok,
                 "target": pairs.get(name, {}).get("authority_target", "").replace("_", " ")}
                for name, ok in temporal.get("per_pair", {}).items()
            ],
        },
    }


def site_data(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("decision", "NOT_EVALUABLE")
    return {
        "repo": REPO_URL,
        "current": CURRENT,
        "classes": [{"code": c, "name": n, "description": d} for c, _, n, d in CLASSES],
        "history": [
            {"run": run, "text": text, "current": run == CURRENT,
             "decision": (decision if run == CURRENT else d) or "NOT_EVALUABLE"}
            for run, d, text in HISTORY
        ],
        "excavation": excavation(),
        "benchmark": benchmark(),
        "results": results(report),
    }


def build(out: Path = OUT, report: dict[str, Any] | None = None) -> Path:
    report = report or json.loads(REPORT.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(site_data(report), indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    print(build(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
