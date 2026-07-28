import json
from pathlib import Path

from cobol_archaeologist.eval.phase5 import BinaryBaselineRecord
from cobol_archaeologist.eval.phase5_report import build_phase5_report
from cobol_archaeologist.eval.schemas import EvaluationRecord

ROOT = Path(__file__).resolve().parents[1]
M4 = ROOT / "data" / "eval" / "m4"


def _records(name: str) -> list[EvaluationRecord]:
    return [
        EvaluationRecord.model_validate_json(line)
        for line in (M4 / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _binary(
    agent: list[EvaluationRecord], system_id: str
) -> list[BinaryBaselineRecord]:
    return [
        BinaryBaselineRecord(
            instance_id=row.instance_id,
            system_id=system_id,
            gold_is_drift=row.gold.drift_type != "D7_conformant",
            predicted_is_drift=True,
            score=1.0,
            is_interprocedural=row.gold.code_locus.is_interprocedural,
            source_sha256=row.source_sha256,
        )
        for row in agent
    ]


def test_phase5_report_fails_closed_before_human_freeze():
    report = build_phase5_report(
        agent=None,
        oracle_slice=None,
        structured={},
        binary={},
        benchmark_frozen=False,
        annotation_complete=False,
    )
    assert report.status == "NOT_EVALUABLE"
    assert any("annotation" in issue for issue in report.issues)
    assert any("benchmark" in issue for issue in report.issues)


def test_phase5_report_requires_and_scores_all_seven_baselines():
    agent = _records("agent")[:12]
    oracle = _records("oracle_slice")[:12]
    rag = _records("dense_rag")[:12]
    binary = {
        name: _binary(agent, name)
        for name in (
            "train_majority",
            "prevalence_random",
            "static_keyword",
            "attacker_with_bases",
        )
    }
    report = build_phase5_report(
        agent=agent,
        oracle_slice=oracle,
        structured={
            "plain_llm": rag,
            "rag_dense": rag,
            "rag_reranker": rag,
        },
        binary=binary,
        benchmark_frozen=True,
        annotation_complete=True,
        resamples=200,
    )
    assert report.status == "EVALUABLE"
    assert len(report.systems) == 9
    assert "agent_minus_attacker_with_bases_t1_f1" in report.comparisons
    json.dumps(report.model_dump(mode="json"))
