"""Build the deterministic T5.3 completion summary from frozen artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cobol_archaeologist.eval.live import ROOT
from cobol_archaeologist.eval.phase5 import BinaryBaselineRecord
from cobol_archaeologist.eval.phase5_report import build_phase5_report, write_phase5_report
from cobol_archaeologist.eval.schemas import EvaluationRecord

M5 = ROOT / "data" / "eval" / "m5"


def _jsonl(path: Path, model):
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_completion_summary(*, resamples: int = 10_000):
    structured_paths = {
        "plain_llm": M5 / "plain_llm" / "plain_llm.jsonl",
        "rag_dense": M5 / "rag_dense" / "rag_dense.jsonl",
        "rag_reranker": M5 / "rag_reranker" / "rag_reranker.jsonl",
    }
    binary_paths = {
        name: M5 / "baselines" / f"{name}.jsonl"
        for name in (
            "train_majority",
            "prevalence_random",
            "static_keyword",
            "attacker_with_bases",
        )
    }
    provenance_paths = {
        "agent": M5 / "agent-rerun" / "agent.manifest.json",
        "plain_llm": M5 / "plain_llm" / "plain_llm.manifest.json",
        "rag_dense": M5 / "rag_dense" / "rag_dense.manifest.json",
        "rag_reranker": M5 / "rag_reranker" / "rag_reranker.manifest.json",
        "oracle_slice": M5 / "oracle_slice-rerun" / "oracle_slice.manifest.json",
        **{
            name: M5 / "baselines" / f"{name}.manifest.json"
            for name in binary_paths
        },
    }
    return build_phase5_report(
        agent=_jsonl(M5 / "agent-rerun" / "agent.jsonl", EvaluationRecord),
        oracle_slice=_jsonl(
            M5 / "oracle_slice-rerun" / "oracle_slice.jsonl", EvaluationRecord
        ),
        structured={
            name: _jsonl(path, EvaluationRecord)
            for name, path in structured_paths.items()
        },
        binary={
            name: _jsonl(path, BinaryBaselineRecord)
            for name, path in binary_paths.items()
        },
        provenance={name: _manifest(path) for name, path in provenance_paths.items()},
        benchmark_frozen=True,
        annotation_complete=True,
        resamples=resamples,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument(
        "--output-prefix", type=Path, default=M5 / "t5.3-completion-summary"
    )
    args = parser.parse_args()
    report = build_completion_summary(resamples=args.resamples)
    write_phase5_report(
        report,
        json_path=Path(f"{args.output_prefix}.json"),
        markdown_path=Path(f"{args.output_prefix}.md"),
    )
    print(json.dumps({"status": report.status, "issues": report.issues}))
    return 0 if report.status == "EVALUABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
