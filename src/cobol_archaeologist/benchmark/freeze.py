"""Fail-closed promotion of v1-pre into the immutable Phase-5 benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.annotation import (
    AdjudicationRecord,
    IndependentAnnotation,
    agreement_report,
    disagreement_ids,
)
from cobol_archaeologist.eval.metrics import versioned_judgment
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.schemas import DriftInstance


class FreezeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "3"
    split_counts: dict[str, int]
    split_sha256: dict[str, str]
    real_curated_test_rows: int = Field(ge=50, le=150)
    t6_pairs: int = Field(ge=20)
    annotation_sample_size: int = Field(ge=50)
    annotation_evidence_sha256: dict[str, str]
    detector_visible_changes: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, model):
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _visible_projection(row: DriftInstance) -> dict:
    return {
        "regulation_clause": row.regulation_clause.model_dump(mode="json"),
        "base_program": row.provenance.base_program,
    }


def _count_t6_pairs(rows: list[DriftInstance]) -> int:
    records = [
        EvaluationRecord(
            instance_id=row.instance_id,
            gold=row,
            abstained=True,
            abstention_reason="freeze pairing probe",
            system_id="freeze",
            source_sha256="0" * 64,
            run_key=f"freeze:{row.instance_id}",
        )
        for row in rows
    ]
    return versioned_judgment(records)["pairs"]


def freeze_benchmark(
    *,
    pre_dir: Path,
    output_dir: Path,
    adjudicated_real_path: Path,
    pass_a_path: Path,
    pass_b_path: Path,
    adjudication_path: Path,
) -> FreezeManifest:
    """Validate independent evidence, replace real gold, and hash v1 splits."""

    passes_a = _load(pass_a_path, IndependentAnnotation)
    passes_b = _load(pass_b_path, IndependentAnnotation)
    report = agreement_report(passes_a, passes_b)
    if report.sample_size < 50:
        raise ValueError(
            "benchmark freeze requires at least 50 independently annotated rows"
        )
    differences = disagreement_ids(passes_a, passes_b)
    adjudications = _load(adjudication_path, AdjudicationRecord)
    by_adjudicated_id = {record.candidate_id: record for record in adjudications}
    if len(by_adjudicated_id) != len(adjudications):
        raise ValueError("adjudication log contains duplicate candidate IDs")
    if set(by_adjudicated_id) != differences:
        raise ValueError(
            "adjudication log must cover exactly the differing independent records"
        )

    adjudicated = _load(adjudicated_real_path, DriftInstance)
    if any(row.provenance.source != "real_curated" for row in adjudicated):
        raise ValueError("adjudicated real artifact contains a non-real row")
    real_by_id = {row.instance_id: row for row in adjudicated}
    if set(real_by_id) != {row.candidate_id for row in passes_a}:
        raise ValueError(
            "adjudicated real rows must match the annotation candidate set"
        )

    split_rows = {
        name: _load(pre_dir / f"{name}.jsonl", DriftInstance)
        for name in ("train", "dev", "test")
    }
    original_real = {
        row.instance_id: row
        for row in split_rows["test"]
        if row.provenance.source == "real_curated"
    }
    if set(original_real) != set(real_by_id):
        raise ValueError("v1-pre real test rows do not match adjudicated candidate IDs")
    split_rows["test"] = [
        real_by_id.get(row.instance_id, row) for row in split_rows["test"]
    ]
    detector_visible_changes = sorted(
        item
        for item in real_by_id
        if _visible_projection(real_by_id[item])
        != _visible_projection(original_real[item])
    )
    t6_pairs = _count_t6_pairs(
        [row for row in split_rows["test"] if row.provenance.source == "real_curated"]
    )
    if t6_pairs < 20:
        raise ValueError("frozen real test rows require at least 20 intact T6 pairs")

    output_dir.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for name, rows in split_rows.items():
        destination = output_dir / f"{name}.jsonl"
        destination.write_text(
            "".join(row.model_dump_json() + "\n" for row in rows),
            encoding="utf-8",
        )
        split_hashes[name] = _sha256(destination)
    manifest = FreezeManifest(
        split_counts={name: len(rows) for name, rows in split_rows.items()},
        split_sha256=split_hashes,
        real_curated_test_rows=len(real_by_id),
        t6_pairs=t6_pairs,
        annotation_sample_size=report.sample_size,
        annotation_evidence_sha256={
            "pass_a": _sha256(pass_a_path),
            "pass_b": _sha256(pass_b_path),
            "adjudications": _sha256(adjudication_path),
            "adjudicated_real": _sha256(adjudicated_real_path),
        },
        detector_visible_changes=detector_visible_changes,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
