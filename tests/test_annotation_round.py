from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.benchmark.annotation import (
    IndependentAnnotation,
    agreement_report,
    build_blinded_candidates,
)
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "benchmark" / "seed" / "real_curated.jsonl"
PROGRAMS = ROOT / "data" / "benchmark" / "seed" / "programs"


def _rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in SEED.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _annotation(
    row: DriftInstance,
    annotator: str,
    *,
    drift_type: str | None = None,
) -> IndependentAnnotation:
    prediction = DriftPrediction.from_gold(row)
    if drift_type == "D7_conformant":
        prediction = prediction.model_copy(
            update={
                "drift_type": "D7_conformant",
                "labels": prediction.labels.model_copy(
                    update={
                        "program_level": "conformant",
                        "paragraph_level": "conformant",
                        "line_level": [],
                    }
                ),
            }
        )
    return IndependentAnnotation(
        candidate_id=row.instance_id,
        annotator_id=annotator,
        completed_at=datetime(2026, 7, 27, tzinfo=UTC),
        decision="include",
        prediction=prediction,
        rationale="Primary clause and source evidence reviewed independently.",
    )


def test_blinded_pack_omits_every_gold_only_field():
    candidates = build_blinded_candidates(_rows(), program_root=PROGRAMS)
    assert len(candidates) == 51
    payload = "\n".join(item.model_dump_json() for item in candidates)
    for forbidden in (
        '"drift_type"',
        '"target_path"',
        '"labels"',
        '"gold_rationale"',
        '"provenance"',
        '"mutation"',
    ):
        assert forbidden not in payload
    assert all(item.source_files for item in candidates)


def test_annotation_decision_fails_closed():
    row = _rows()[0]
    with pytest.raises(ValidationError, match="include requires"):
        IndependentAnnotation(
            candidate_id=row.instance_id,
            annotator_id="reviewer-a",
            completed_at=datetime(2026, 7, 27, tzinfo=UTC),
            decision="include",
            rationale="Incomplete record must fail.",
        )


def test_agreement_report_is_pre_adjudication_and_paired():
    rows = _rows()[:3]
    left = [_annotation(row, "reviewer-a") for row in rows]
    right = [_annotation(row, "reviewer-b") for row in rows]
    report = agreement_report(left, right, bootstrap_samples=200)
    assert report.sample_size == 3
    assert report.inclusion_raw_agreement == 1.0
    assert report.class_raw_agreement == 1.0
    assert report.class_krippendorff_alpha == 1.0

    with pytest.raises(ValueError, match="different annotator"):
        agreement_report(left, left, bootstrap_samples=200)
