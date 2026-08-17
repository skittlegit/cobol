from __future__ import annotations

import json

from cobol_archaeologist.eval.phase5_complete import build_completion_summary
from cobol_archaeologist.eval.phase5_reuse import (
    FROZEN_TEST,
    confirm_m4_reranker_identity,
    projection_specs,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.schemas import DriftInstance


def _rows(path, model):
    return [model.model_validate_json(line) for line in path.read_text("utf-8").splitlines()]


def test_m4_reranker_identity_is_proved_from_immutable_runtime_source():
    evidence = confirm_m4_reranker_identity()
    assert evidence["conclusion"] == "search.mode == hybrid_rerank"


def test_phase5_projections_are_complete_ordered_and_fail_closed():
    frozen = _rows(FROZEN_TEST, DriftInstance)
    frozen_ids = [row.instance_id for row in frozen]
    for spec in projection_specs():
        records = _rows(spec.output_records, EvaluationRecord)
        manifest = json.loads(spec.output_manifest.read_text("utf-8"))
        assert [record.instance_id for record in records] == frozen_ids
        assert len(records) == len({record.instance_id for record in records}) == 196
        assert all(record.system_id == spec.system_id for record in records)
        assert all(record.infrastructure_error is None for record in records)
        assert all(
            record.abstained or (record.verification and record.verification.verified)
            for record in records
        )
        assert manifest["validity"]["status"] == "VALID"
        assert manifest["total"] == 196


def test_t53_completion_summary_is_evaluable_and_keeps_floor_vacated():
    report = build_completion_summary(resamples=200)
    assert report.status == "EVALUABLE"
    assert not report.issues
    assert len(report.systems) == 9
    assert report.decisions["surface_floor"]["status"] == "VACATED"
    assert report.decisions["surface_floor"]["met"] is None
