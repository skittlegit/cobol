"""Deterministic, fail-closed preparation of T6 review disagreements."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    CollaborationSubagentResponseRecord,
    ReviewResponse,
    review_disagreement_dimensions,
    validate_blinded_review_record,
    validate_collaboration_subagent_audit,
)
from cobol_archaeologist.benchmark.t6_v2 import load_blinded_review_packet

DisagreementDimension = Literal["decision", "drift_type", "line_level"]


class PrimaryTranscriptAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    task_identity: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    final_message: str = Field(min_length=1)
    outcome: Literal["schema_invalid", "accepted"]
    envelope_format: Literal["visible_canonical", "full_blind_packet_row"]
    envelope_separator: Literal["space", "lf"]


class PrimaryTranscriptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    attempts: list[PrimaryTranscriptAttempt] = Field(min_length=1)

    @model_validator(mode="after")
    def _attempts_are_a_fail_closed_chain(self) -> PrimaryTranscriptItem:
        if [attempt.attempt for attempt in self.attempts] != list(
            range(1, len(self.attempts) + 1)
        ):
            raise ValueError("primary attempts must be contiguous from one")
        accepted = [
            index
            for index, attempt in enumerate(self.attempts)
            if attempt.outcome == "accepted"
        ]
        if len(accepted) > 1 or (accepted and accepted != [len(self.attempts) - 1]):
            raise ValueError("primary item may end in at most one accepted attempt")
        return self


class CitationCoordinate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    program: str
    line: int
    source_alias: str


class ReviewComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_ordinal: int = Field(ge=1, le=22)
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    primary_task_identity: str
    primary_attempt: int
    independent_task_identity: str
    independent_attempt: int
    primary_decision: str
    independent_decision: str
    primary_drift_type: str | None
    independent_drift_type: str | None
    primary_line_level: list[CitationCoordinate]
    independent_line_level: list[CitationCoordinate]
    disagreement_dimensions: list[DisagreementDimension]
    requires_adjudication_review: bool


class ReviewComparisonReport(BaseModel):
    """Comparison only: this object cannot resolve or promote any item."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    report_kind: Literal["adjudication_preparation"]
    status: Literal["incomplete_primary", "ready_for_adjudication_review"]
    packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_item_count: Literal[22]
    primary_accepted_item_count: int = Field(ge=0, le=22)
    primary_schema_invalid_attempt_count: int = Field(ge=0)
    compared_item_count: int = Field(ge=0, le=22)
    pending_primary_item_ids: list[str]
    exact_agreement_count: int = Field(ge=0, le=22)
    disagreement_item_count: int = Field(ge=0, le=22)
    decision_disagreement_count: int = Field(ge=0, le=22)
    drift_type_disagreement_count: int = Field(ge=0, le=22)
    line_level_disagreement_count: int = Field(ge=0, le=22)
    automatic_adjudication_performed: Literal[False]
    promotion_performed: Literal[False]
    items: list[ReviewComparisonItem]

    @model_validator(mode="after")
    def _summary_matches_items(self) -> ReviewComparisonReport:
        disagreement_items = sum(item.requires_adjudication_review for item in self.items)
        decision = sum(
            "decision" in item.disagreement_dimensions for item in self.items
        )
        drift_type = sum(
            "drift_type" in item.disagreement_dimensions for item in self.items
        )
        line_level = sum(
            "line_level" in item.disagreement_dimensions for item in self.items
        )
        if (
            self.compared_item_count != len(self.items)
            or self.primary_accepted_item_count != len(self.items)
            or self.exact_agreement_count != len(self.items) - disagreement_items
            or self.disagreement_item_count != disagreement_items
            or self.decision_disagreement_count != decision
            or self.drift_type_disagreement_count != drift_type
            or self.line_level_disagreement_count != line_level
        ):
            raise ValueError("comparison summary differs from item details")
        expected_status = (
            "ready_for_adjudication_review"
            if not self.pending_primary_item_ids
            else "incomplete_primary"
        )
        if self.status != expected_status:
            raise ValueError("comparison status differs from primary completeness")
        return self


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    rows: list[BaseModel] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            rows.append(model.model_validate_json(raw))
        except ValueError as exc:
            raise ValueError(f"invalid {path.name} line {line_number}: {exc}") from exc
    return rows


def _citations(response: ReviewResponse) -> list[CitationCoordinate]:
    return [
        CitationCoordinate(program=program, line=line, source_alias=source_alias)
        for program, line, source_alias in sorted(
            (item.program, item.line, item.source_alias)
            for item in response.line_level
        )
    ]


def prepare_review_comparison(
    *,
    root: Path,
    packet_path: Path,
    primary_transcript_path: Path,
    independent_manifest_path: Path,
) -> ReviewComparisonReport:
    """Compare accepted judgments; never adjudicate or promote them."""

    packet = load_blinded_review_packet(packet_path)
    if len(packet) != 22:
        raise ValueError("comparison requires the complete 22-item packet")
    packet_ids = [item.review_item_id for item in packet]
    manifest = validate_collaboration_subagent_audit(
        root=root, manifest_path=independent_manifest_path
    )
    if manifest.review_role != "independent_verifier":
        raise ValueError("independent evidence manifest has the wrong role")
    independent_path = root / manifest.responses.path
    independent_rows = _load_jsonl(
        independent_path, CollaborationSubagentResponseRecord
    )
    independent = {
        row.review_item_id: row
        for row in independent_rows
        if isinstance(row, CollaborationSubagentResponseRecord)
    }
    if list(independent) != packet_ids:
        raise ValueError("independent responses differ from packet order")
    primary_rows = _load_jsonl(primary_transcript_path, PrimaryTranscriptItem)
    if [row.review_item_id for row in primary_rows] != packet_ids:
        raise ValueError("primary transcript differs from packet order")
    packet_by_id = {item.review_item_id: item for item in packet}
    accepted_primary: dict[str, tuple[PrimaryTranscriptAttempt, ReviewResponse]] = {}
    invalid_count = 0
    for row in primary_rows:
        assert isinstance(row, PrimaryTranscriptItem)
        for attempt in row.attempts:
            try:
                parsed = ReviewResponse.model_validate_json(attempt.final_message)
            except ValueError:
                if attempt.outcome != "schema_invalid":
                    raise ValueError("accepted primary attempt is schema-invalid")
                invalid_count += 1
                continue
            if attempt.outcome != "accepted":
                raise ValueError("primary attempt marked invalid has a valid response")
            validate_blinded_review_record(
                record=BlindedReviewRecord(
                    review_item_id=row.review_item_id,
                    reviewer_pseudonym="comparison-validation-only",
                    completed_at="1970-01-01T00:00:00Z",
                    review_response=parsed,
                ),
                item=packet_by_id[row.review_item_id],
            )
            accepted_primary[row.review_item_id] = (attempt, parsed)
    items: list[ReviewComparisonItem] = []
    for item in packet:
        primary_pair = accepted_primary.get(item.review_item_id)
        if primary_pair is None:
            continue
        primary_attempt, primary_response = primary_pair
        independent_row = independent[item.review_item_id]
        independent_response = independent_row.review_response
        primary_citations = _citations(primary_response)
        independent_citations = _citations(independent_response)
        dimensions: list[DisagreementDimension] = list(
            review_disagreement_dimensions(primary_response, independent_response)
        )
        items.append(
            ReviewComparisonItem(
                release_ordinal=item.release_ordinal,
                review_item_id=item.review_item_id,
                primary_task_identity=primary_attempt.task_identity,
                primary_attempt=primary_attempt.attempt,
                independent_task_identity=independent_row.task_identity,
                independent_attempt=independent_row.attempt,
                primary_decision=primary_response.decision,
                independent_decision=independent_response.decision,
                primary_drift_type=primary_response.drift_type,
                independent_drift_type=independent_response.drift_type,
                primary_line_level=primary_citations,
                independent_line_level=independent_citations,
                disagreement_dimensions=dimensions,
                requires_adjudication_review=bool(dimensions),
            )
        )
    pending = [item_id for item_id in packet_ids if item_id not in accepted_primary]
    disagreement_count = sum(item.requires_adjudication_review for item in items)
    return ReviewComparisonReport(
        schema_version="1",
        report_kind="adjudication_preparation",
        status=(
            "ready_for_adjudication_review" if not pending else "incomplete_primary"
        ),
        packet_sha256=_sha(packet_path),
        primary_transcript_sha256=_sha(primary_transcript_path),
        independent_manifest_sha256=_sha(independent_manifest_path),
        expected_item_count=22,
        primary_accepted_item_count=len(accepted_primary),
        primary_schema_invalid_attempt_count=invalid_count,
        compared_item_count=len(items),
        pending_primary_item_ids=pending,
        exact_agreement_count=len(items) - disagreement_count,
        disagreement_item_count=disagreement_count,
        decision_disagreement_count=sum(
            "decision" in item.disagreement_dimensions for item in items
        ),
        drift_type_disagreement_count=sum(
            "drift_type" in item.disagreement_dimensions for item in items
        ),
        line_level_disagreement_count=sum(
            "line_level" in item.disagreement_dimensions for item in items
        ),
        automatic_adjudication_performed=False,
        promotion_performed=False,
        items=items,
    )


def write_review_comparison(report: ReviewComparisonReport, path: Path) -> None:
    """Write only the deterministic preparation report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
