"""Frozen inter-module Pydantic models: the DriftInstance family (Track C, T0.3).

M0 SCHEMA FREEZE — any change to these models after the T0.3 commit is a
CONTRACT CHANGE affecting Tracks A/B/C and must be flagged in chat, never
edited in place.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

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


class CurrentValue(BaseModel):
    """The clause's currently mandated value, when it is a scalar/set."""

    model_config = ConfigDict(extra="forbid")

    # Free string, e.g. "duration_years", "amount_inr", "enum_set"; the kind
    # vocabulary is not frozen (Track B extends it in T2.1).
    kind: str
    value: Any


class RegulationClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: str
    clause_id: str
    # version and effective_date are never optional: the temporal axis is the
    # research novelty and every clause must be pinned to a point in time.
    version: str
    effective_date: datetime.date
    text: str
    # None for clauses that mandate a check rather than a scalar (D2/D6).
    # D1/D4/D5 instances should carry it — enforced by the T2.3 generator,
    # not the schema, in v1.
    current_value: CurrentValue | None = None


class CodeLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    programs: list[str] = Field(min_length=1)
    paragraphs: list[str]
    line_span: tuple[int, int]
    slice_vars: list[str]
    # No default: interprocedurality drives the headline stratification and
    # must be a deliberate annotation.
    is_interprocedural: bool

    @field_validator("line_span")
    @classmethod
    def _line_span_ordered(cls, span: tuple[int, int]) -> tuple[int, int]:
        start, end = span
        if start < 1 or end < 1:
            raise ValueError("line_span bounds must be >= 1 (1-based source lines)")
        if start > end:
            raise ValueError("line_span start must be <= end")
        return span


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_level: Literal["drift", "conformant"]
    paragraph_level: Literal["drift", "conformant"]
    # Empty for conformant instances.
    line_level: list[int]


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
    labels: Labels
    gold_rationale: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _labels_consistent_with_drift_type(self) -> "DriftInstance":
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
        elif self.labels.program_level != "drift":
            raise ValueError(
                f"{self.drift_type} requires labels.program_level == 'drift'"
            )
        if (
            self.provenance.source == "synthetic"
            and self.drift_type != "D7_conformant"
            and self.provenance.mutation is None
        ):
            raise ValueError(
                "a synthetic drift instance must record provenance.mutation"
            )
        return self
