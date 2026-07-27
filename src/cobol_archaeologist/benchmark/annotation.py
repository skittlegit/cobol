"""Blinded independent-annotation packs and pre-adjudication agreement.

This module deliberately operates on the real-curated rows only.  Gold labels,
rationales, provenance, generator metadata, and prior judgments never enter
the blinded candidate model.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.schemas import (
    DriftInstance,
    DriftPrediction,
    RegulationClause,
)


class BlindedCandidate(BaseModel):
    """The complete evidence bundle shared with both annotators."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    regulation_clause: RegulationClause
    program_scope: str
    source_files: dict[str, str] = Field(min_length=1)


class IndependentAnnotation(BaseModel):
    """One immutable, pre-discussion annotation record."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    annotator_id: str = Field(min_length=1)
    completed_at: datetime
    decision: Literal["include", "exclude", "needs_adjudication"]
    prediction: DriftPrediction | None = None
    rationale: str = Field(min_length=1)
    disagreement_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _decision_shape(self) -> IndependentAnnotation:
        if self.decision == "include":
            if self.prediction is None:
                raise ValueError("include requires a complete prediction")
            if self.prediction.instance_id != self.candidate_id:
                raise ValueError("prediction instance_id must match candidate_id")
        elif self.prediction is not None:
            raise ValueError(
                "exclude/needs_adjudication records must not carry a prediction"
            )
        return self


class AgreementReport(BaseModel):
    """Agreement measured before adjudication."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int = Field(ge=1)
    annotator_ids: tuple[str, str]
    inclusion_raw_agreement: float = Field(ge=0, le=1)
    inclusion_bootstrap_95_ci: tuple[float, float]
    inclusion_cohen_kappa: float | None
    class_comparable_rows: int = Field(ge=0)
    class_raw_agreement: float | None
    class_bootstrap_95_ci: tuple[float, float] | None
    class_cohen_kappa: float | None
    class_krippendorff_alpha: float | None
    disagreement_counts: dict[str, int]


class AdjudicationRecord(BaseModel):
    """Immutable resolution for one candidate whose locked passes differed."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    adjudicator_id: str = Field(min_length=1)
    decided_at: datetime
    outcome: Literal["include", "exclude"]
    final_instance: DriftInstance | None = None
    changed_fields: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _outcome_shape(self) -> AdjudicationRecord:
        if self.outcome == "include":
            if self.final_instance is None:
                raise ValueError("included adjudication requires final_instance")
            if self.final_instance.instance_id != self.candidate_id:
                raise ValueError("final instance ID must match adjudicated candidate")
        elif self.final_instance is not None:
            raise ValueError("excluded adjudication must not carry final_instance")
        return self


def _resolve_source(program_root: Path, name: str) -> Path:
    direct = program_root / name
    if direct.is_file():
        return direct
    matches = sorted(
        path for path in program_root.rglob(Path(name).name) if path.is_file()
    )
    if len(matches) != 1:
        raise ValueError(
            f"source file {name!r} resolved to {len(matches)} paths under {program_root}"
        )
    return matches[0]


def build_blinded_candidates(
    rows: Iterable[DriftInstance],
    *,
    program_root: Path,
) -> list[BlindedCandidate]:
    """Project real-curated gold into identical, gold-hidden evidence bundles."""

    candidates: list[BlindedCandidate] = []
    for row in rows:
        if row.provenance.source != "real_curated":
            continue
        names = {row.provenance.base_program}
        names.update(
            locus.file for locus in row.code_locus.loci if locus.file is not None
        )
        sources: dict[str, str] = {}
        for name in sorted(names):
            path = _resolve_source(program_root, name)
            sources[path.name] = path.read_text(encoding="utf-8")
        candidates.append(
            BlindedCandidate(
                candidate_id=row.instance_id,
                regulation_clause=row.regulation_clause,
                program_scope=Path(row.provenance.base_program).stem,
                source_files=sources,
            )
        )
    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("blinded annotation pack contains duplicate candidate IDs")
    return sorted(candidates, key=lambda candidate: candidate.candidate_id)


def _cohen_kappa(left: Sequence[str], right: Sequence[str]) -> float | None:
    if len(left) != len(right):
        raise ValueError("kappa inputs must be paired")
    if not left:
        return None
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    categories = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[item] / len(left)) * (right_counts[item] / len(right))
        for item in categories
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else None
    return (observed - expected) / (1.0 - expected)


def _krippendorff_alpha_nominal(
    left: Sequence[str | None],
    right: Sequence[str | None],
) -> float | None:
    pairs = [(a, b) for a, b in zip(left, right, strict=True) if a and b]
    if not pairs:
        return None
    observed_disagreement = sum(a != b for a, b in pairs) / len(pairs)
    values = [value for pair in pairs for value in pair]
    counts = Counter(values)
    total = len(values)
    if total < 2:
        return None
    expected_disagreement = 1.0 - sum(
        count * (count - 1) / (total * (total - 1)) for count in counts.values()
    )
    if expected_disagreement == 0.0:
        return 1.0 if observed_disagreement == 0.0 else None
    return 1.0 - observed_disagreement / expected_disagreement


def _bootstrap_agreement(
    left: Sequence[str],
    right: Sequence[str],
    *,
    seed: int,
    samples: int,
) -> tuple[float, float]:
    if not left or len(left) != len(right):
        raise ValueError("bootstrap agreement inputs must be non-empty and paired")
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        indexes = [generator.randrange(len(left)) for _ in left]
        estimates.append(
            sum(left[index] == right[index] for index in indexes) / len(indexes)
        )
    estimates.sort()
    low = estimates[int(0.025 * (samples - 1))]
    high = estimates[int(0.975 * (samples - 1))]
    return low, high


def agreement_report(
    left: Sequence[IndependentAnnotation],
    right: Sequence[IndependentAnnotation],
    *,
    seed: int = 20260727,
    bootstrap_samples: int = 10_000,
) -> AgreementReport:
    """Pair two locked passes and report raw, kappa, and alpha before discussion."""

    if bootstrap_samples < 100:
        raise ValueError("agreement report requires at least 100 bootstrap samples")
    left_by_id = {row.candidate_id: row for row in left}
    right_by_id = {row.candidate_id: row for row in right}
    if len(left_by_id) != len(left) or len(right_by_id) != len(right):
        raise ValueError("each annotation pass must contain unique candidate IDs")
    if set(left_by_id) != set(right_by_id) or not left_by_id:
        raise ValueError(
            "annotation passes must cover the same non-empty candidate set"
        )
    left_annotators = {row.annotator_id for row in left}
    right_annotators = {row.annotator_id for row in right}
    if len(left_annotators) != 1 or len(right_annotators) != 1:
        raise ValueError("each pass must belong to exactly one annotator")
    annotators = (next(iter(left_annotators)), next(iter(right_annotators)))
    if annotators[0] == annotators[1]:
        raise ValueError("independent passes require different annotator IDs")

    ids = sorted(left_by_id)
    left_decisions = [left_by_id[item].decision for item in ids]
    right_decisions = [right_by_id[item].decision for item in ids]
    comparable = [
        item
        for item in ids
        if left_by_id[item].prediction is not None
        and right_by_id[item].prediction is not None
    ]
    left_classes = [
        left_by_id[item].prediction.drift_type  # type: ignore[union-attr]
        for item in comparable
    ]
    right_classes = [
        right_by_id[item].prediction.drift_type  # type: ignore[union-attr]
        for item in comparable
    ]
    class_raw = (
        sum(a == b for a, b in zip(left_classes, right_classes, strict=True))
        / len(comparable)
        if comparable
        else None
    )
    disagreement_counts: Counter[str] = Counter()
    for item in ids:
        a = left_by_id[item]
        b = right_by_id[item]
        if a.decision != b.decision:
            disagreement_counts["decision"] += 1
        elif (
            a.prediction is not None
            and b.prediction is not None
            and a.prediction.drift_type != b.prediction.drift_type
        ):
            disagreement_counts["class"] += 1
        for code in set(a.disagreement_codes) | set(b.disagreement_codes):
            disagreement_counts[code] += 1

    inclusion_raw = sum(
        a == b for a, b in zip(left_decisions, right_decisions, strict=True)
    ) / len(ids)
    return AgreementReport(
        sample_size=len(ids),
        annotator_ids=annotators,
        inclusion_raw_agreement=inclusion_raw,
        inclusion_bootstrap_95_ci=_bootstrap_agreement(
            left_decisions,
            right_decisions,
            seed=seed,
            samples=bootstrap_samples,
        ),
        inclusion_cohen_kappa=_cohen_kappa(left_decisions, right_decisions),
        class_comparable_rows=len(comparable),
        class_raw_agreement=class_raw,
        class_bootstrap_95_ci=(
            _bootstrap_agreement(
                left_classes,
                right_classes,
                seed=seed + 1,
                samples=bootstrap_samples,
            )
            if comparable
            else None
        ),
        class_cohen_kappa=_cohen_kappa(left_classes, right_classes),
        class_krippendorff_alpha=_krippendorff_alpha_nominal(
            [
                left_by_id[item].prediction.drift_type
                if left_by_id[item].prediction
                else None
                for item in ids
            ],
            [
                right_by_id[item].prediction.drift_type
                if right_by_id[item].prediction
                else None
                for item in ids
            ],
        ),
        disagreement_counts=dict(sorted(disagreement_counts.items())),
    )


def disagreement_ids(
    left: Sequence[IndependentAnnotation],
    right: Sequence[IndependentAnnotation],
) -> set[str]:
    """Return candidates whose decision or included semantic record differs."""

    left_by_id = {row.candidate_id: row for row in left}
    right_by_id = {row.candidate_id: row for row in right}
    if set(left_by_id) != set(right_by_id):
        raise ValueError("annotation passes must cover the same candidate IDs")
    return {
        item
        for item in left_by_id
        if (
            left_by_id[item].decision != right_by_id[item].decision
            or left_by_id[item].prediction != right_by_id[item].prediction
        )
    }


def _load_gold(path: Path) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--program-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    candidates = build_blinded_candidates(
        _load_gold(args.source),
        program_root=args.program_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(candidate.model_dump_json() + "\n" for candidate in candidates),
        encoding="utf-8",
    )
    manifest = {
        "candidate_count": len(candidates),
        "candidate_ids": [candidate.candidate_id for candidate in candidates],
        "forbidden_gold_fields": [
            "drift_type",
            "target_path",
            "labels",
            "gold_rationale",
            "provenance",
            "mutation",
        ],
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
