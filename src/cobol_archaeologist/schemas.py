"""Inter-module Pydantic models: the DriftInstance family (Track C).

SCHEMA v2 — RE-FROZEN 2026-07-12 per
``docs/reviews/2026-07-12/contract-change-track-c-RESOLVED.md`` (T0.3a). Any
change to these models after this commit is a new CONTRACT CHANGE affecting
Tracks A/B/C and must be flagged in chat, never edited in place.

v2 over v1: interprocedural line-to-program binding (``loci`` /
``SourceLocus`` / ``SourceLineRef`` replacing the flat ``CodeLocus``),
recursive+typed ``CurrentValue`` with a ``Comparator`` field on every node, and
``DriftInstance.target_path`` for composite-clause D1/D5 targeting.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DriftType = Literal[
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
]

# Comparator vocabulary — chosen to match Track B's existing clause vocabulary so
# the clauses.jsonl migration is mechanical.
Comparator = Literal[
    "strictly_greater",  # >
    "at_least",          # >=
    "strictly_less",     # <
    "at_most",           # <=
    "equal",             # =
    "not_equal",         # <>
]

# A leaf value: scalar or a homogeneous string set. Composite nodes instead nest
# ``dict[str, CurrentValue]`` (handled on CurrentValue.value directly).
Scalar = int | float | str | bool | list[str]


class CurrentValue(BaseModel):
    """The clause's currently mandated value — recursive and typed.

    A *leaf* carries a scalar ``value`` and (optionally) a ``comparator``. A
    *composite* (``kind == "composite"``) carries a mapping of named child
    ``CurrentValue`` nodes and no comparator (comparators belong to leaves).
    """

    model_config = ConfigDict(extra="forbid")

    # Free string vocabulary, e.g. "duration_years", "amount_inr", "enum_set",
    # "composite"; Track B extends it. "composite" is the one reserved value.
    kind: str
    value: Scalar | dict[str, "CurrentValue"]
    # Leaves only; a composite carrying one is a validation error.
    comparator: Comparator | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _composite_discipline(self) -> "CurrentValue":
        is_mapping = isinstance(self.value, dict)
        if self.kind == "composite":
            if not is_mapping:
                raise ValueError(
                    "a composite CurrentValue must have a mapping value"
                )
            if self.comparator is not None:
                raise ValueError(
                    "a composite CurrentValue must not carry a comparator "
                    "(comparators belong to leaves)"
                )
        elif is_mapping:
            raise ValueError(
                "a non-composite CurrentValue must not have a mapping value"
            )
        return self


def resolve_path(cv: CurrentValue, path: str) -> CurrentValue:
    """Resolve a dotted ``path`` into a composite ``cv``.

    ``"penalty_per_day"`` or ``"a.b"`` for nested composites. Returns the
    ``CurrentValue`` at that path. Raises ``KeyError`` on any bad segment. The
    single canonical accessor imported by both B's emitters and C's metrics.
    """
    node = cv
    for part in path.split("."):
        if not isinstance(node.value, dict) or part not in node.value:
            raise KeyError(part)
        node = node.value[part]
    return node


class RegulationClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: str
    clause_id: str
    # version and effective_date are never optional: the temporal axis is the
    # research novelty and every clause must be pinned to a point in time.
    version: str
    effective_date: datetime.date
    text: str
    # None for clauses that mandate a check rather than a value (D2/D6).
    current_value: CurrentValue | None = None


class SourceLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: str
    # None when the locus is not inside a paragraph (WORKING-STORAGE, decls);
    # populated whenever the locus does fall in a paragraph.
    paragraph: str | None = None
    # None ⇒ the program's own source; else the copybook/file the line resolves
    # to via Track A's LineMap.
    file: str | None = None
    line_span: tuple[int, int]  # 1-based, inclusive

    @field_validator("line_span")
    @classmethod
    def _line_span_ordered(cls, span: tuple[int, int]) -> tuple[int, int]:
        start, end = span
        if start < 1 or end < 1:
            raise ValueError("line_span bounds must be >= 1 (1-based source lines)")
        if start > end:
            raise ValueError("line_span start must be <= end")
        return span


class SourceLineRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: str
    line: int = Field(ge=1)
    file: str | None = None


class CodeLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loci: list[SourceLocus] = Field(min_length=1)
    slice_vars: list[str]
    # No default: interprocedurality drives the headline stratification and must
    # be a deliberate annotation.
    is_interprocedural: bool

    @model_validator(mode="after")
    def _multi_program_is_interprocedural(self) -> "CodeLocus":
        # One-way only: >1 distinct program forces is_interprocedural=True.
        # NOT the reverse — is_interprocedural also covers cross-paragraph
        # single-program cases (playbook §1E), so a single-program locus may
        # legitimately be either.
        if len({locus.program for locus in self.loci}) > 1 and not self.is_interprocedural:
            raise ValueError(
                "loci spanning >1 program require is_interprocedural=True"
            )
        return self


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_level: Literal["drift", "conformant"]
    paragraph_level: Literal["drift", "conformant"]
    # Empty for conformant instances; for D2 the insertion-point line(s).
    line_level: list[SourceLineRef]


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["synthetic", "real_curated"]
    base_program: str
    # Required in practice for synthetic drift (cross-field validator on
    # DriftInstance); absent for real_curated.
    mutation: str | None = None
    # For the real-curated seed (T2.5).
    annotator_notes: str | None = None


class DriftInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    regulation_clause: RegulationClause
    code_locus: CodeLocus
    drift_type: DriftType
    # Dotted path into regulation_clause.current_value; None for non-composite
    # clauses. Required for composite D1/D5 (validator below).
    target_path: str | None = None
    labels: Labels
    gold_rationale: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _labels_consistent_with_drift_type(self) -> "DriftInstance":
        # (v1 rule 1) D7 ⇒ conformant everywhere and empty line_level.
        if self.drift_type == "D7_conformant":
            if (
                self.labels.program_level != "conformant"
                or self.labels.paragraph_level != "conformant"
                or self.labels.line_level != []
            ):
                raise ValueError(
                    "D7_conformant requires conformant program/paragraph labels "
                    "and an empty line_level"
                )
        # (v1 rule 2) non-D7 ⇒ program_level == "drift".
        elif self.labels.program_level != "drift":
            raise ValueError(
                f"{self.drift_type} requires labels.program_level == 'drift'"
            )
        # (v1 rule 3) synthetic non-D7 ⇒ mutation recorded.
        if (
            self.provenance.source == "synthetic"
            and self.drift_type != "D7_conformant"
            and self.provenance.mutation is None
        ):
            raise ValueError(
                "a synthetic drift instance must record provenance.mutation"
            )
        return self

    @model_validator(mode="after")
    def _line_level_within_loci(self) -> "DriftInstance":
        # (v2 rule 4) every line_level ref must fall inside some locus on its
        # (program, file), so interprocedural line-overlap scoring is defined.
        for ref in self.labels.line_level:
            matched = any(
                locus.program == ref.program
                and locus.file == ref.file
                and locus.line_span[0] <= ref.line <= locus.line_span[1]
                for locus in self.code_locus.loci
            )
            if not matched:
                raise ValueError(
                    f"line_level ref (program={ref.program!r}, file={ref.file!r}, "
                    f"line={ref.line}) matches no locus span"
                )
        return self

    @model_validator(mode="after")
    def _target_path_resolves(self) -> "DriftInstance":
        cv = self.regulation_clause.current_value
        tp = self.target_path

        # (v2 rule 6) target_path present ⇒ current_value present and resolves.
        if tp is not None:
            if cv is None:
                raise ValueError(
                    "target_path requires regulation_clause.current_value"
                )
            try:
                resolve_path(cv, tp)
            except KeyError as exc:
                raise ValueError(
                    f"target_path {tp!r} does not resolve into current_value"
                ) from exc

        # (v2 rule 5) composite D1/D5 ⇒ target_path required, resolving to a
        # non-composite node.
        if (
            cv is not None
            and cv.kind == "composite"
            and self.drift_type in {"D1_stale_threshold", "D5_boundary_error"}
        ):
            if tp is None:
                raise ValueError(
                    f"{self.drift_type} against a composite clause requires "
                    "target_path"
                )
            node = resolve_path(cv, tp)  # already known to resolve
            if node.kind == "composite":
                raise ValueError(
                    "target_path must land on a non-composite (leaf) node"
                )
        return self
