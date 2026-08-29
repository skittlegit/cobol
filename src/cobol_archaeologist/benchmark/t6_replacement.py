"""Additive, proposal-blind replacement candidates for rejected T6 pairs."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.benchmark.t6_pair_correction import CorrectionPairID
from cobol_archaeologist.benchmark.t6_review import ReviewResponse
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin
from cobol_archaeologist.schemas import CodeLocus, RegulationClause

ReplacementID = Literal[
    "t6v2-replacement-01",
    "t6v2-replacement-02",
    "t6v2-replacement-03",
    "t6v2-replacement-04",
    "t6v2-replacement-05",
    "t6v2-replacement-06",
    "t6v2-replacement-07",
    "t6v2-replacement-08",
    "t6v2-replacement-09",
    "t6v2-replacement-10",
]
REPLACEMENT_ORDER: tuple[ReplacementID, ...] = (
    "t6v2-replacement-01",
    "t6v2-replacement-02",
    "t6v2-replacement-03",
    "t6v2-replacement-04",
    "t6v2-replacement-05",
    "t6v2-replacement-06",
)


class ReplacementSideInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Literal["alpha", "beta"]
    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    source_alias: str = Field(pattern=r"^src-[0-9a-f]{12}$")
    authority: RegulationClause


class ReplacementPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    replacement_id: ReplacementID
    rejected_pair_id: CorrectionPairID
    replacement_call_id: str = Field(pattern=r"^rcall-[0-9a-f]{12}$")
    prompt_protocol_version: Literal[
        "v2_neutral", "v3_decision_semantics", "v4_explicit_schema"
    ] = "v2_neutral"
    prior_protocol_diagnostic: ArtifactPin | None = None
    prior_batch_ledger: ArtifactPin | None = None
    source: ArtifactPin
    shared_source_text: str = Field(min_length=20)
    code_locus: CodeLocus
    host_design_note: str = Field(min_length=20)
    sides: tuple[ReplacementSideInput, ReplacementSideInput]

    @model_validator(mode="after")
    def _ordered_distinct_sides(self) -> ReplacementPlanItem:
        if [side.position for side in self.sides] != ["alpha", "beta"]:
            raise ValueError("replacement sides must be alpha then beta")
        if len({side.review_item_id for side in self.sides}) != 2:
            raise ValueError("replacement review IDs must be distinct")
        axes = {
            (side.authority.version, side.authority.effective_date)
            for side in self.sides
        }
        if len(axes) != 2:
            raise ValueError("replacement sides must span authority versions")
        return self


class ReplacementSideResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_item_id: str = Field(pattern=r"^rvw-[0-9a-f]{8}$")
    review_response: ReviewResponse


class ReplacementCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_call_id: str = Field(pattern=r"^rcall-[0-9a-f]{12}$")
    sides: tuple[ReplacementSideResponse, ReplacementSideResponse]

    @model_validator(mode="after")
    def _distinct_sides(self) -> ReplacementCompletion:
        if len({side.review_item_id for side in self.sides}) != 2:
            raise ValueError("replacement completion sides must be distinct")
        return self


class ReplacementAttemptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: Literal[1]
    task_identity: str = Field(min_length=1)
    fork_turns: Literal["none"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    tools_authorized: Literal[0]
    visible_pairs: Literal[1]
    prior_pair_context_included: Literal[False]
    prompt_utf8_base64: str = Field(min_length=1)
    prompt_utf8_length: int = Field(ge=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_message_utf8_base64: str = Field(min_length=1)
    final_message_utf8_length: int = Field(ge=1)
    final_message_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal[
        "validated_flip",
        "rejected_nonflip",
        "rejected_invalid_identity",
        "rejected_schema",
    ]

    @model_validator(mode="after")
    def _exact_bytes(self) -> ReplacementAttemptAudit:
        try:
            prompt = base64.b64decode(self.prompt_utf8_base64, validate=True)
            final = base64.b64decode(self.final_message_utf8_base64, validate=True)
            prompt.decode("utf-8")
            final.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("replacement transcript bytes are invalid UTF-8") from exc
        if (
            len(prompt) != self.prompt_utf8_length
            or hashlib.sha256(prompt).hexdigest() != self.prompt_sha256
            or len(final) != self.final_message_utf8_length
            or hashlib.sha256(final).hexdigest() != self.final_message_sha256
        ):
            raise ValueError("replacement transcript byte pin changed")
        if self.outcome != "rejected_schema":
            ReplacementCompletion.model_validate_json(final)
        return self


class ReplacementItemAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replacement_id: ReplacementID
    replacement_call_id: str = Field(pattern=r"^rcall-[0-9a-f]{12}$")
    review_item_order: tuple[str, str]
    envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: ReplacementAttemptAudit


class ReplacementAuditManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    audit_variant: Literal["additive_replacement_review"]
    finalized: Literal[True]
    reviewer_pseudonym: str = Field(min_length=1)
    correction_audit: ArtifactPin
    replacement_plan: ArtifactPin
    responses: ArtifactPin
    provider: Literal["chatgpt-codex-collaboration"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    fork_turns_per_attempt: Literal["none"]
    fresh_task_per_pair: Literal[True]
    tools_authorized_per_call: Literal[0]
    prior_pair_context_included: Literal[False]
    item_count: Literal[6]
    validated_flip_count: int = Field(ge=0, le=6)
    rejected_nonflip_count: int = Field(ge=0, le=6)
    replacement_order: tuple[ReplacementID, ...]
    items: list[ReplacementItemAudit]

    @model_validator(mode="after")
    def _complete_scope(self) -> ReplacementAuditManifest:
        if self.replacement_order != REPLACEMENT_ORDER:
            raise ValueError("replacement audit order differs from frozen reserve")
        if [item.replacement_id for item in self.items] != list(self.replacement_order):
            raise ValueError("replacement items differ from frozen reserve")
        validated = sum(
            item.attempt.outcome == "validated_flip" for item in self.items
        )
        rejected = sum(
            item.attempt.outcome == "rejected_nonflip" for item in self.items
        )
        if (
            self.validated_flip_count != validated
            or self.rejected_nonflip_count != rejected
            or validated + rejected != 6
        ):
            raise ValueError("replacement outcome counts differ from one-shot calls")
        tasks = [item.attempt.task_identity for item in self.items]
        if len(tasks) != len(set(tasks)):
            raise ValueError("replacement task identities must be unique")
        return self


class ReplacementBridgeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    finalized: Literal[True]
    projection: Literal[
        "replacement_review_to_t6_pool_v1",
        "replacement_multibatch_to_t6_pool_v1",
    ]
    replacement_audit: ArtifactPin
    replacement_plan: ArtifactPin
    replacement_responses: ArtifactPin
    replacement_order: tuple[ReplacementID, ...]
    review_item_members: dict[ReplacementID, tuple[str, str]]


ReplacementLedgerOutcome = Literal[
    "validated_flip",
    "rejected_nonflip",
    "rejected_invalid_identity",
    "rejected_schema",
]


class ReplacementBatchLedgerManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    ledger_variant: Literal["replacement_one_shot_batch_v1"]
    finalized: Literal[True]
    batch_id: str = Field(pattern=r"^replacement-[a-z0-9-]+$")
    coordinator_manifest: ArtifactPin
    correction_audit: ArtifactPin
    replacement_plan: ArtifactPin
    transcript: ArtifactPin
    provider: Literal["chatgpt-codex-collaboration"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    fork_turns_per_attempt: Literal["none"]
    fresh_task_per_pair: Literal[True]
    tools_authorized_per_call: Literal[0]
    prior_pair_context_included: Literal[False]
    item_count: int = Field(ge=1, le=6)
    outcome_counts: dict[ReplacementLedgerOutcome, int]
    replacement_order: tuple[ReplacementID, ...]
    items: list[ReplacementItemAudit]

    @model_validator(mode="after")
    def _complete_batch(self) -> ReplacementBatchLedgerManifest:
        if self.item_count != len(self.items) or self.item_count != len(
            self.replacement_order
        ):
            raise ValueError("replacement ledger batch size is inconsistent")
        if [item.replacement_id for item in self.items] != list(
            self.replacement_order
        ):
            raise ValueError("replacement ledger order differs from its items")
        expected = {
            outcome: sum(item.attempt.outcome == outcome for item in self.items)
            for outcome in (
                "validated_flip",
                "rejected_nonflip",
                "rejected_invalid_identity",
                "rejected_schema",
            )
        }
        if self.outcome_counts != expected:
            raise ValueError("replacement ledger outcome counts changed")
        tasks = [item.attempt.task_identity for item in self.items]
        if len(tasks) != len(set(tasks)):
            raise ValueError("replacement ledger task identities must be unique")
        return self


class ReplacementMultiBatchLedgerManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    ledger_variant: Literal["replacement_multi_batch_v1"]
    finalized: Literal[True]
    batch_ledgers: tuple[ArtifactPin, ...]
    required_rejected_pair_order: tuple[CorrectionPairID, ...]
    accepted_replacement_order: tuple[ReplacementID, ...]
    accepted_count: Literal[6]


def require_replacement_flip(completion: ReplacementCompletion) -> None:
    responses = [side.review_response for side in completion.sides]
    if any(response.decision != "include" for response in responses) or {
        response.drift_type == "D7_conformant" for response in responses
    } != {False, True}:
        raise ValueError("replacement output does not form a temporal flip")


def replacement_envelope(item: ReplacementPlanItem) -> dict[str, object]:
    """Return only model-visible content; coordinator identity/path stays private."""

    return {
        "review_call_id": item.replacement_call_id,
        "shared_source_text": item.shared_source_text,
        "sides": [
            {
                "position": side.position,
                "review_item_id": side.review_item_id,
                "source_alias": side.source_alias,
                "authority": side.authority.model_dump(mode="json"),
            }
            for side in item.sides
        ],
    }


def build_replacement_prompt(item: ReplacementPlanItem) -> str:
    schema = (
        '{"review_call_id":"rcall-12hex","sides":['
        '{"review_item_id":"rvw-8hex","review_response":'
        '{"decision":"include|exclude|needs_adjudication","drift_type":"'
        'D1_stale_threshold|D2_missing_rule|D3_contradictory|'
        'D4_stale_reference_data|D5_boundary_error|D6_dead_code|'
        'D7_conformant|null","line_level":[{"program":"nonempty","line":1,'
        '"source_alias":"src-12hex"}],"rationale":"nonempty",'
        '"uncertainty_notes":"string or null"}}]}'
    )
    decision_semantics = (
        "Decision semantics: include means the source-authority relationship is "
        "usable and confidently classifiable as D1-D7, including D7 conformant; "
        "exclude is only for unusable or out-of-scope evidence; needs_adjudication "
        "is only for a genuinely unresolved classification. "
        if item.prompt_protocol_version in {
            "v3_decision_semantics",
            "v4_explicit_schema",
        }
        else ""
    )
    final_schema_check = (
        "FINAL SCHEMA CHECK: for D7_conformant, line_level MUST be []; any D7 "
        "citation makes the entire response invalid. For non-D7, line_level "
        "MUST be nonempty. "
        if item.prompt_protocol_version == "v4_explicit_schema"
        else ""
    )
    return (
        "You are a non-human independent paired authority reviewer. Use only the "
        "envelope below. Independently judge the shared COBOL source against each "
        "authority side. Do not use files, web, tools, "
        "prior context, or outside knowledge. D7 has no citations; every non-D7 "
        "label requires visible 1-based source citations using that side's alias. "
        + decision_semantics
        + f"Return only JSON with this exact shape: {schema}"
        + (" " + final_schema_check if final_schema_check else "")
        + "\nEnvelope: "
        + json.dumps(
            replacement_envelope(item),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_pin(root: Path, pin: ArtifactPin, *, label: str) -> Path:
    path = (root / pin.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"{label} leaves repository or is missing")
    if source_sha256(path) != pin.sha256:
        raise ValueError(f"{label} pin changed")
    return path


def _compact(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _validate_side_citations(
    *, plan: ReplacementPlanItem, completion: ReplacementCompletion
) -> None:
    if completion.review_call_id != plan.replacement_call_id:
        raise ValueError("replacement completion uses the wrong opaque call ID")
    planned_sides = {side.review_item_id: side for side in plan.sides}
    if tuple(side.review_item_id for side in completion.sides) != tuple(
        planned_sides
    ):
        raise ValueError("replacement completion side order differs from plan")
    lines = plan.shared_source_text.splitlines()
    declarations = [
        (index, match.group(1).upper())
        for index, line in enumerate(lines, start=1)
        if (
            match := re.search(
                r"\bPROGRAM-ID\.\s+([A-Z0-9-]+)\.", line, re.IGNORECASE
            )
        )
    ]
    program_spans = {
        program: range(
            start,
            (
                declarations[index + 1][0]
                if index + 1 < len(declarations)
                else len(lines) + 1
            ),
        )
        for index, (start, program) in enumerate(declarations)
    }
    visible_programs = {locus.program.upper() for locus in plan.code_locus.loci}
    if set(program_spans) != visible_programs:
        raise ValueError("replacement source programs differ from frozen locus")
    for side in completion.sides:
        source = planned_sides[side.review_item_id]
        for citation in side.review_response.line_level:
            if citation.source_alias != source.source_alias or citation.line > len(lines):
                raise ValueError("replacement citation differs from opaque source")
            cited_program = citation.program.upper()
            if (
                cited_program not in visible_programs
                or citation.line not in program_spans[cited_program]
            ):
                raise ValueError("replacement citation uses a non-visible program")


def validate_replacement_completion(
    plan: ReplacementPlanItem, completion: ReplacementCompletion
) -> None:
    """Validate one model completion without consulting coordinator gold state."""

    _validate_side_citations(plan=plan, completion=completion)
    require_replacement_flip(completion)


def classify_replacement_final(
    *, plan: ReplacementPlanItem, final: bytes
) -> tuple[ReplacementLedgerOutcome, ReplacementCompletion | None]:
    """Classify one immutable raw final without correcting or retrying it."""

    try:
        completion = ReplacementCompletion.model_validate_json(final)
    except (ValueError, UnicodeDecodeError):
        return "rejected_schema", None
    try:
        _validate_side_citations(plan=plan, completion=completion)
    except (KeyError, ValueError):
        return "rejected_invalid_identity", completion
    try:
        require_replacement_flip(completion)
    except ValueError:
        return "rejected_nonflip", completion
    return "validated_flip", completion


def validate_replacement_batch_ledger(
    *, root: Path, ledger_path: Path
) -> tuple[
    ReplacementBatchLedgerManifest,
    list[ReplacementPlanItem],
    list[tuple[ReplacementPlanItem, ReplacementCompletion]],
]:
    from cobol_archaeologist.benchmark.t6_pair_correction import (
        PairCorrectionAuditManifest,
        PairCorrectionPlanItem,
    )

    ledger = ReplacementBatchLedgerManifest.model_validate_json(
        ledger_path.read_text(encoding="utf-8")
    )
    coordinator_path = _check_pin(
        root, ledger.coordinator_manifest, label="replacement coordinator"
    )
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    correction_path = _check_pin(
        root, ledger.correction_audit, label="replacement correction audit"
    )
    correction = PairCorrectionAuditManifest.model_validate_json(
        correction_path.read_text(encoding="utf-8")
    )
    correction_plan_path = _check_pin(
        root, correction.correction_plan, label="rejected-pair correction plan"
    )
    correction_plans = {
        item.correction_pair_id: item
        for raw in correction_plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for item in [PairCorrectionPlanItem.model_validate_json(raw)]
    }
    plan_path = _check_pin(root, ledger.replacement_plan, label="replacement plan")
    transcript_path = _check_pin(
        root, ledger.transcript, label="replacement raw transcript"
    )
    if (
        ArtifactPin.model_validate(coordinator["replacement_plan"])
        != ledger.replacement_plan
        or ArtifactPin.model_validate(coordinator["correction_audit"])
        != ledger.correction_audit
        or coordinator.get("freeze_version")
        != ledger.batch_id.removeprefix("replacement-")
        or coordinator.get("model_id") != ledger.model_id
        or coordinator.get("reasoning_effort") != ledger.reasoning_effort
        or coordinator.get("fork_turns") != ledger.fork_turns_per_attempt
        or coordinator.get("tools_authorized")
        != ledger.tools_authorized_per_call
        or coordinator.get("prior_pair_context_included")
        != ledger.prior_pair_context_included
    ):
        raise ValueError("replacement ledger differs from coordinator lineage")
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    calls = [
        json.loads(raw)
        for raw in transcript_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(plans) != ledger.item_count or len(calls) != ledger.item_count:
        raise ValueError("replacement ledger scope differs from frozen batch")
    accepted: list[tuple[ReplacementPlanItem, ReplacementCompletion]] = []
    for plan, call, frozen, item in zip(
        plans, calls, coordinator["calls"], ledger.items, strict=True
    ):
        source_path = _check_pin(root, plan.source, label="replacement source")
        if source_path.read_text(encoding="utf-8") != plan.shared_source_text:
            raise ValueError("replacement source text differs from its pin")
        rejected = correction_plans[plan.rejected_pair_id]
        if {
            side.authority.model_dump_json() for side in plan.sides
        } != {side.authority.model_dump_json() for side in rejected.sides}:
            raise ValueError("replacement authority lineage differs from rejected pair")
        if (
            set(call) != {"review_call_id", "task_identity", "final_message"}
            or call["review_call_id"] != plan.replacement_call_id
            or frozen["replacement_call_id"] != plan.replacement_call_id
        ):
            raise ValueError("replacement transcript identity differs from plan")
        prompt_path = _check_pin(
            root,
            ArtifactPin.model_validate(frozen["prompt"]),
            label="replacement prompt",
        )
        prompt = prompt_path.read_bytes()
        if prompt != build_replacement_prompt(plan).encode("utf-8"):
            raise ValueError("replacement prompt bytes differ from plan")
        final = call["final_message"].encode("utf-8")
        outcome, completion = classify_replacement_final(plan=plan, final=final)
        if (
            item.replacement_id != plan.replacement_id
            or item.replacement_call_id != plan.replacement_call_id
            or item.review_item_order
            != tuple(side.review_item_id for side in plan.sides)
            or item.envelope_sha256
            != hashlib.sha256(_compact(replacement_envelope(plan))).hexdigest()
            or item.attempt.task_identity != call["task_identity"]
            or base64.b64decode(
                item.attempt.prompt_utf8_base64, validate=True
            )
            != prompt
            or base64.b64decode(
                item.attempt.final_message_utf8_base64, validate=True
            )
            != final
            or item.attempt.outcome != outcome
        ):
            raise ValueError("replacement ledger item differs from raw attempt")
        if outcome == "validated_flip" and completion is not None:
            accepted.append((plan, completion))
    return ledger, plans, accepted


def validate_replacement_audit(
    *, root: Path, manifest_path: Path
) -> ReplacementAuditManifest:
    from cobol_archaeologist.benchmark.t6_pair_correction import (
        PairCorrectionAuditManifest,
    )

    manifest = ReplacementAuditManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    correction_path = _check_pin(
        root, manifest.correction_audit, label="replacement correction audit"
    )
    correction = PairCorrectionAuditManifest.model_validate_json(
        correction_path.read_text(encoding="utf-8")
    )
    if correction.rejected_nonflip_count != 6:
        raise ValueError("replacement reserve differs from rejected correction count")
    plan_path = _check_pin(root, manifest.replacement_plan, label="replacement plan")
    correction_plan_path = _check_pin(
        root, correction.correction_plan, label="rejected-pair correction plan"
    )
    from cobol_archaeologist.benchmark.t6_pair_correction import (
        PairCorrectionPlanItem,
    )

    correction_plans = {
        item.correction_pair_id: item
        for raw in correction_plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for item in [PairCorrectionPlanItem.model_validate_json(raw)]
    }
    response_path = _check_pin(
        root, manifest.responses, label="replacement responses"
    )
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    responses = [
        ReplacementCompletion.model_validate_json(raw)
        for raw in response_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(plans) != 6 or len(responses) != 6:
        raise ValueError("replacement audit must contain six one-shot calls")
    for plan, response, item in zip(plans, responses, manifest.items, strict=True):
        source_path = _check_pin(root, plan.source, label="replacement source")
        if source_path.read_text(encoding="utf-8") != plan.shared_source_text:
            raise ValueError("replacement plan source text differs from pin")
        rejected = correction_plans[plan.rejected_pair_id]
        replacement_authorities = {
            side.authority.model_dump_json() for side in plan.sides
        }
        rejected_authorities = {
            side.authority.model_dump_json() for side in rejected.sides
        }
        if replacement_authorities != rejected_authorities:
            raise ValueError("replacement authority lineage differs from rejected pair")
        prompt = build_replacement_prompt(plan).encode("utf-8")
        final = base64.b64decode(
            item.attempt.final_message_utf8_base64, validate=True
        )
        if (
            item.replacement_id != plan.replacement_id
            or item.replacement_call_id != plan.replacement_call_id
            or response.review_call_id != plan.replacement_call_id
            or item.review_item_order
            != tuple(side.review_item_id for side in plan.sides)
            or item.envelope_sha256
            != hashlib.sha256(_compact(replacement_envelope(plan))).hexdigest()
            or base64.b64decode(item.attempt.prompt_utf8_base64, validate=True)
            != prompt
            or ReplacementCompletion.model_validate_json(final) != response
        ):
            raise ValueError("replacement audit differs from frozen prompt/output")
        _validate_side_citations(plan=plan, completion=response)
        try:
            require_replacement_flip(response)
        except ValueError:
            expected = "rejected_nonflip"
        else:
            expected = "validated_flip"
        if item.attempt.outcome != expected:
            raise ValueError("replacement outcome differs from hidden flip gate")
    return manifest


def validate_replacement_bridge(
    *, root: Path, bridge_path: Path
) -> tuple[ReplacementBridgeManifest, list[tuple[ReplacementPlanItem, ReplacementCompletion]]]:
    bridge = ReplacementBridgeManifest.model_validate_json(
        bridge_path.read_text(encoding="utf-8")
    )
    if bridge.projection == "replacement_multibatch_to_t6_pool_v1":
        aggregate_path = _check_pin(
            root, bridge.replacement_audit, label="replacement multi-batch ledger"
        )
        aggregate = ReplacementMultiBatchLedgerManifest.model_validate_json(
            aggregate_path.read_text(encoding="utf-8")
        )
        accepted_by_pair: dict[
            CorrectionPairID, tuple[ReplacementPlanItem, ReplacementCompletion]
        ] = {}
        seen_calls: set[str] = set()
        seen_reviews: set[str] = set()
        seen_aliases: set[str] = set()
        for pin in aggregate.batch_ledgers:
            batch_path = _check_pin(
                root, pin, label="replacement aggregate batch ledger"
            )
            _, plans, accepted = validate_replacement_batch_ledger(
                root=root, ledger_path=batch_path
            )
            for plan in plans:
                review_ids = {side.review_item_id for side in plan.sides}
                aliases = {side.source_alias for side in plan.sides}
                if (
                    plan.replacement_call_id in seen_calls
                    or seen_reviews.intersection(review_ids)
                    or seen_aliases.intersection(aliases)
                ):
                    raise ValueError("replacement batches reuse model-visible identity")
                seen_calls.add(plan.replacement_call_id)
                seen_reviews.update(review_ids)
                seen_aliases.update(aliases)
            for plan, completion in accepted:
                if plan.rejected_pair_id in accepted_by_pair:
                    raise ValueError("multiple replacements project the same rejected pair")
                accepted_by_pair[plan.rejected_pair_id] = (plan, completion)
        if set(accepted_by_pair) != set(aggregate.required_rejected_pair_order):
            raise ValueError("multi-batch replacements do not cover exact rejected scope")
        accepted = [
            accepted_by_pair[pair_id]
            for pair_id in aggregate.required_rejected_pair_order
        ]
        if (
            aggregate.accepted_count != len(accepted)
            or aggregate.accepted_replacement_order
            != tuple(plan.replacement_id for plan, _ in accepted)
        ):
            raise ValueError("multi-batch accepted order differs from ledger")
        plan_path = _check_pin(
            root, bridge.replacement_plan, label="replacement aggregate plan"
        )
        response_path = _check_pin(
            root,
            bridge.replacement_responses,
            label="replacement aggregate responses",
        )
        projected_plans = [
            ReplacementPlanItem.model_validate_json(raw)
            for raw in plan_path.read_text(encoding="utf-8").splitlines()
            if raw.strip()
        ]
        projected_responses = [
            ReplacementCompletion.model_validate_json(raw)
            for raw in response_path.read_text(encoding="utf-8").splitlines()
            if raw.strip()
        ]
        expected_members = {
            plan.replacement_id: tuple(side.review_item_id for side in plan.sides)
            for plan, _ in accepted
        }
        if (
            projected_plans != [plan for plan, _ in accepted]
            or projected_responses != [response for _, response in accepted]
            or bridge.replacement_order != aggregate.accepted_replacement_order
            or bridge.review_item_members != expected_members
        ):
            raise ValueError("replacement aggregate bridge projection changed")
        return bridge, accepted
    audit_path = _check_pin(root, bridge.replacement_audit, label="replacement audit")
    audit = validate_replacement_audit(root=root, manifest_path=audit_path)
    plan_path = _check_pin(root, bridge.replacement_plan, label="replacement bridge plan")
    response_path = _check_pin(
        root, bridge.replacement_responses, label="replacement bridge responses"
    )
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    responses = [
        ReplacementCompletion.model_validate_json(raw)
        for raw in response_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    accepted = [
        (plan, response)
        for plan, response, item in zip(plans, responses, audit.items, strict=True)
        if item.attempt.outcome == "validated_flip"
    ]
    expected_members = {
        plan.replacement_id: tuple(side.review_item_id for side in plan.sides)
        for plan, _ in accepted
    }
    if (
        bridge.replacement_plan != audit.replacement_plan
        or bridge.replacement_order != tuple(expected_members)
        or bridge.review_item_members != expected_members
    ):
        raise ValueError("replacement bridge differs from validated one-shot audit")
    return bridge, accepted
