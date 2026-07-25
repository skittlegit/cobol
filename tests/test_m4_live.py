"""Offline gates for the resumable three-system M4 live runner."""

from pathlib import Path

from cobol_archaeologist.eval.baselines import DenseRAGContext
from cobol_archaeologist.eval.live import (
    baseline_question,
    bounded_code_context,
)
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"


def _row() -> DriftInstance:
    return DriftInstance.model_validate_json(
        next(line for line in SPLIT.read_text(encoding="utf-8").splitlines() if line)
    )


def test_dense_baseline_question_contains_no_hidden_gold_fields():
    gold = _row()
    visible = DenseRAGContext(
        clause_query=gold.regulation_clause.text,
        retrieved_clauses=[],
        program="0001: IDENTIFICATION DIVISION.",
    )

    rendered = baseline_question("dense_rag", visible)

    for hidden in (
        gold.instance_id,
        gold.drift_type,
        gold.gold_rationale,
        gold.provenance.mutation,
    ):
        if hidden:
            assert hidden not in rendered
    assert gold.regulation_clause.text in rendered


def test_bounded_code_context_is_query_driven_and_line_bounded():
    irrelevant = [f"       01 FILLER-{index:03d} PIC X." for index in range(80)]
    relevant = [
        "       IF CREDIT-LIMIT > 5000",
        "           MOVE 'REVIEW' TO ACCOUNT-STATUS",
        "       END-IF",
    ]
    lines = irrelevant[:40] + relevant + irrelevant[40:]
    materialized = MaterializedSource(
        main_file="ACCOUNT.cbl",
        files={"ACCOUNT.cbl": "\n".join(lines) + "\n"},
        source_sha256="0" * 64,
    )

    context = bounded_code_context(
        materialized,
        "credit limit must not exceed 5000",
        max_lines=40,
    )

    assert "CREDIT-LIMIT > 5000" in context
    numbered_code_lines = [
        line for line in context.splitlines() if line[:4].isdigit()
    ]
    assert len(numbered_code_lines) <= 40
    assert "mutation" not in context.lower()
