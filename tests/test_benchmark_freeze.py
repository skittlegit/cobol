from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cobol_archaeologist.benchmark.annotation import IndependentAnnotation
from cobol_archaeologist.benchmark.freeze import freeze_benchmark
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "data" / "benchmark" / "v1-pre"
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
    assert set(manifest.split_sha256) == {"train", "dev", "test"}
