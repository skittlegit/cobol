from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.annotation import (
    AdjudicationRecord,
    IndependentAnnotation,
)
from cobol_archaeologist.benchmark.freeze import (
    _visible_projection,
    freeze_benchmark,
)
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "data" / "benchmark" / "legacy" / "v1-pre"
V1 = ROOT / "data" / "benchmark" / "v1"
REAL = ROOT / "data" / "benchmark" / "seed" / "real_curated.jsonl"


def _real_rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in REAL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_pass(path: Path, rows: list[DriftInstance], annotator: str) -> None:
    records = [
        IndependentAnnotation(
            candidate_id=row.instance_id,
            annotator_id=annotator,
            completed_at=datetime(2026, 7, 27, tzinfo=UTC),
            decision="include",
            prediction=DriftPrediction.from_gold(row),
            rationale="Independent primary-source fixture review.",
        )
        for row in rows
    ]
    path.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )


def test_committed_manifest_pins_exact_canonical_lf_split_bytes():
    manifest = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))

    for name in ("train", "dev", "test"):
        split_bytes = (V1 / f"{name}.jsonl").read_bytes()
        assert b"\r\n" not in split_bytes
        assert (
            hashlib.sha256(split_bytes).hexdigest()
            == manifest["split_sha256"][name]
        )


def test_freeze_requires_and_hashes_independent_evidence(tmp_path):
    rows = _real_rows()
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    adjudications = tmp_path / "adjudications.jsonl"
    _write_pass(left, rows, "fixture-reviewer-a")
    _write_pass(right, rows, "fixture-reviewer-b")
    adjudications.write_text("", encoding="utf-8")

    manifest = freeze_benchmark(
        pre_dir=PRE,
        output_dir=tmp_path / "v1",
        adjudicated_real_path=REAL,
        pass_a_path=left,
        pass_b_path=right,
        adjudication_path=adjudications,
    )

    assert manifest.split_counts == {"train": 307, "dev": 102, "test": 204}
    assert manifest.real_curated_test_rows == 51
    assert manifest.t6_pairs == 20
    assert manifest.detector_visible_changes == []
    assert manifest.excluded_candidate_ids == []
    assert set(manifest.split_sha256) == {"train", "dev", "test"}
    for name, expected_sha256 in manifest.split_sha256.items():
        split_bytes = (tmp_path / "v1" / f"{name}.jsonl").read_bytes()
        assert b"\r\n" not in split_bytes
        assert hashlib.sha256(split_bytes).hexdigest() == expected_sha256
    assert b"\r\n" not in (tmp_path / "v1" / "manifest.json").read_bytes()


def test_detector_visible_projection_includes_code_locus_but_not_gold_rationale():
    row = _real_rows()[0]
    locus_changed = row.model_copy(
        update={
            "code_locus": row.code_locus.model_copy(
                update={"slice_vars": [*row.code_locus.slice_vars, "EXTRA-VISIBLE-VAR"]}
            )
        }
    )
    rationale_changed = row.model_copy(update={"gold_rationale": "Gold-only update."})

    assert _visible_projection(row) != _visible_projection(locus_changed)
    assert _visible_projection(row) == _visible_projection(rationale_changed)


def test_freeze_drops_excluded_candidates_and_shrinks_test_split(tmp_path):
    """A candidate excluded by adjudication is removed from test, not forced
    into a label -- the freeze must succeed below the original 51/20
    baseline as long as every non-surviving candidate has an exclude record
    covering exactly the candidates requiring adjudication."""

    rows = _real_rows()
    excluded_row = rows[0]
    kept_rows = rows[1:]

    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    adjudications = tmp_path / "adjudications.jsonl"

    # Both passes agree the excluded candidate needs_adjudication (a
    # convergent needs_adjudication, not a disagreement); all others agree
    # on inclusion as in the happy-path fixture.
    left_records = []
    right_records = []
    for row in rows:
        if row.instance_id == excluded_row.instance_id:
            for records in (left_records, right_records):
                records.append(
                    IndependentAnnotation(
                        candidate_id=row.instance_id,
                        annotator_id="fixture-reviewer-a"
                        if records is left_records
                        else "fixture-reviewer-b",
                        completed_at=datetime(2026, 7, 27, tzinfo=UTC),
                        decision="needs_adjudication",
                        prediction=None,
                        rationale="Fixture: deliberately ambiguous for this test.",
                        disagreement_codes=["fixture_ambiguous"],
                    )
                )
            continue
        for records, annotator in (
            (left_records, "fixture-reviewer-a"),
            (right_records, "fixture-reviewer-b"),
        ):
            records.append(
                IndependentAnnotation(
                    candidate_id=row.instance_id,
                    annotator_id=annotator,
                    completed_at=datetime(2026, 7, 27, tzinfo=UTC),
                    decision="include",
                    prediction=DriftPrediction.from_gold(row),
                    rationale="Independent primary-source fixture review.",
                )
            )
    left.write_text(
        "".join(r.model_dump_json() + "\n" for r in left_records), encoding="utf-8"
    )
    right.write_text(
        "".join(r.model_dump_json() + "\n" for r in right_records), encoding="utf-8"
    )

    adjudication_record = AdjudicationRecord(
        candidate_id=excluded_row.instance_id,
        adjudicator_id="fixture-adjudicator",
        decided_at=datetime(2026, 7, 27, tzinfo=UTC),
        outcome="exclude",
        final_instance=None,
        changed_fields=[],
        rationale="Fixture: no decisive primary authority found.",
    )
    adjudications.write_text(
        adjudication_record.model_dump_json() + "\n", encoding="utf-8"
    )

    adjudicated_real = tmp_path / "resolved_real.jsonl"
    adjudicated_real.write_text(
        "".join(row.model_dump_json() + "\n" for row in kept_rows), encoding="utf-8"
    )

    manifest = freeze_benchmark(
        pre_dir=PRE,
        output_dir=tmp_path / "v1",
        adjudicated_real_path=adjudicated_real,
        pass_a_path=left,
        pass_b_path=right,
        adjudication_path=adjudications,
    )

    assert manifest.real_curated_test_rows == len(kept_rows)
    assert manifest.excluded_candidate_ids == [excluded_row.instance_id]
    assert manifest.split_counts["test"] == 203  # 204 - the one dropped row

    test_ids = {
        json.loads(line)["instance_id"]
        for line in (tmp_path / "v1" / "test.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    assert excluded_row.instance_id not in test_ids


def test_freeze_rejects_missing_adjudication_for_excluded_candidate(tmp_path):
    """A candidate absent from the resolved real rows without a matching
    exclude adjudication record must fail closed, not silently drop."""

    rows = _real_rows()
    left = tmp_path / "left.jsonl"
    right = tmp_path / "right.jsonl"
    adjudications = tmp_path / "adjudications.jsonl"
    _write_pass(left, rows, "fixture-reviewer-a")
    _write_pass(right, rows, "fixture-reviewer-b")
    adjudications.write_text("", encoding="utf-8")

    adjudicated_real = tmp_path / "resolved_real.jsonl"
    adjudicated_real.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows[1:]), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="explicit exclude adjudication"):
        freeze_benchmark(
            pre_dir=PRE,
            output_dir=tmp_path / "v1",
            adjudicated_real_path=adjudicated_real,
            pass_a_path=left,
            pass_b_path=right,
            adjudication_path=adjudications,
        )
