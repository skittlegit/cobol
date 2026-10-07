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
    real_curated_test_rows: int = Field(ge=43, le=51)
    t6_pairs: int = Field(ge=9)
    annotation_sample_size: int = Field(ge=50)
    annotation_evidence_sha256: dict[str, str]
    detector_visible_changes: list[str]
    excluded_candidate_ids: list[str] = Field(default_factory=list)


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
        # code_locus controls source-bundle materialization (additional
        # programs/copybooks) and oracle-slice inputs. A locus-only correction
        # can therefore change what a detector sees even when the clause and
        # base program are unchanged.
        "code_locus": row.code_locus.model_dump(mode="json"),
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
    all_candidate_ids = {row.candidate_id for row in passes_a}
    passes_b_by_id = {row.candidate_id: row for row in passes_b}
    differences = disagreement_ids(passes_a, passes_b)
    # A candidate both passes independently marked needs_adjudication is not
    # a "difference" (decision and None-prediction both match), but it still
    # blocks the freeze until an adjudicator resolves it -- include it in the
    # required-adjudication set alongside genuine disagreements.
    convergent_needs_adjudication = {
        row.candidate_id
        for row in passes_a
        if row.decision == "needs_adjudication"
        and passes_b_by_id[row.candidate_id].decision == "needs_adjudication"
    }
    requires_adjudication = differences | convergent_needs_adjudication
    adjudications = _load(adjudication_path, AdjudicationRecord)
    by_adjudicated_id = {record.candidate_id: record for record in adjudications}
    if len(by_adjudicated_id) != len(adjudications):
        raise ValueError("adjudication log contains duplicate candidate IDs")
    if set(by_adjudicated_id) != requires_adjudication:
        raise ValueError(
            "adjudication log must cover exactly the candidates requiring "
            "adjudication (disagreements plus convergent needs_adjudication)"
        )
    excluded_ids = {
        record.candidate_id for record in adjudications if record.outcome == "exclude"
    }

    adjudicated = _load(adjudicated_real_path, DriftInstance)
    if any(row.provenance.source != "real_curated" for row in adjudicated):
        raise ValueError("adjudicated real artifact contains a non-real row")
    real_by_id = {row.instance_id: row for row in adjudicated}
    if not set(real_by_id).issubset(all_candidate_ids):
        raise ValueError("resolved real rows include an unknown candidate ID")
    if set(real_by_id) | excluded_ids != all_candidate_ids:
        raise ValueError(
            "every candidate must either survive into the resolved real rows "
            "or carry an explicit exclude adjudication record"
        )
    if set(real_by_id) & excluded_ids:
        raise ValueError(
            "a candidate cannot both survive into resolved real rows and "
            "carry an exclude adjudication record"
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
    if set(original_real) != all_candidate_ids:
        raise ValueError(
            "v1-pre real test rows do not match the annotation candidate set"
        )
    new_test = []
    for row in split_rows["test"]:
        if row.provenance.source != "real_curated":
            new_test.append(row)
            continue
        if row.instance_id in excluded_ids:
            continue  # dropped: excluded by adjudication, not replaced
        new_test.append(real_by_id[row.instance_id])
    split_rows["test"] = new_test
    detector_visible_changes = sorted(
        item
        for item in real_by_id
        if _visible_projection(real_by_id[item])
        != _visible_projection(original_real[item])
    )
    t6_pairs = _count_t6_pairs(
        [row for row in split_rows["test"] if row.provenance.source == "real_curated"]
    )
    if t6_pairs < 9:
        raise ValueError("frozen real test rows require at least 9 intact T6 pairs")

    output_dir.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for name, rows in split_rows.items():
        destination = output_dir / f"{name}.jsonl"
        destination.write_text(
            "".join(row.model_dump_json() + "\n" for row in rows),
            encoding="utf-8",
            newline="\n",
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
        excluded_candidate_ids=sorted(excluded_ids),
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest
