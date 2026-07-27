"""Registered D1-D7 policy hunts with fail-closed evidence guards.

Benchmark integrity rule: hunts classify semantic behavior against the cited
clause.  They never use edit-artifact shortcuts such as comment freshness,
formatting discontinuity, identifier style, literal roundness, git history, or
file mtimes.  Track B's MO-0/style probe measured those cues at AUC 0.50; using
them here would invalidate the benchmark rather than improve detection.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory
from cobol_archaeologist.model.prompt import (
    AgentResponse,
    DecisionModel,
    build_hunt_prompt,
)
from cobol_archaeologist.model.verify import (
    Entailer,
    VerificationResult,
    VerificationTier,
)
from cobol_archaeologist.schemas import (
    DriftPrediction,
    DriftType,
    RegulationClause,
    SourceLocus,
)
from cobol_archaeologist.tool_types import ToolLayer

_TIER_CONFIDENCE = {
    VerificationTier.EXECUTED: 0.95,
    VerificationTier.STATIC: 0.85,
    VerificationTier.ENTAILMENT: 0.60,
}

# DECISION (M4-X X2): these class-derived floors replace config 1's global
# three-observation guard. D3's base is two and grows with a proposed locus
# count; D2 keeps four because an absence claim needs breadth.
EVIDENCE_MINIMUMS: dict[DriftType, int] = {
    "D1_stale_threshold": 1,
    "D2_missing_rule": 4,
    "D3_contradictory": 2,
    "D4_stale_reference_data": 1,
    "D5_boundary_error": 1,
    "D6_dead_code": 1,
    "D7_conformant": 1,
}

_PROGRAM_SOURCE_SUFFIXES = frozenset({".cbl", ".cob", ".cobol"})
_NORMALIZATION_MARKER = "SourceLocus.file normalized"


def confidence_for_tier(tier: VerificationTier) -> float:
    """Return the frozen confidence assigned to a verified evidence tier."""

    return _TIER_CONFIDENCE[tier]


def evidence_minimum_for(
    drift_type: DriftType,
    *,
    locus_count: int | None = None,
) -> int:
    """Return the M4-X evidence floor for one drift-class hunt."""

    minimum = EVIDENCE_MINIMUMS[drift_type]
    if drift_type == "D3_contradictory" and locus_count is not None:
        return max(minimum, locus_count)
    return minimum


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _source_stem(value: str) -> str:
    name = _basename(value)
    for suffix in _PROGRAM_SOURCE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


# DECISION (frozen schema): confidence and verifier provenance wrap the
# DriftPrediction instead of widening the gold-only DriftInstance contract.
class HuntOutcome(BaseModel):
    """Typed policy output consumed by T4 evaluation."""

    model_config = ConfigDict(extra="forbid")

    hunt: DriftType
    finding: DriftPrediction | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None
    verification_tier: VerificationTier | None
    trajectory: Trajectory
    abstained: bool
    abstention_reason: str | None

    @model_validator(mode="after")
    def _verified_emission_only(self) -> HuntOutcome:
        if self.abstained:
            if self.finding is not None:
                raise ValueError("an abstained hunt cannot emit a finding")
            if not self.abstention_reason:
                raise ValueError("an abstained hunt requires a reason")
        else:
            if self.finding is None:
                raise ValueError("a successful hunt requires a finding")
            if (
                self.verification is None
                or not self.verification.verified
                or self.verification_tier != self.verification.tier
            ):
                raise ValueError("a hunt finding requires its verified tier result")
            if self.confidence is None:
                raise ValueError("a hunt finding requires confidence")
        return self


class HuntBatchOutcome(BaseModel):
    """All seven hunt trajectories plus the deterministic selected outcome."""

    model_config = ConfigDict(extra="forbid")

    outcomes: list[HuntOutcome] = Field(min_length=7, max_length=7)
    selected: HuntOutcome

    @model_validator(mode="after")
    def _complete_unique_ladder(self) -> HuntBatchOutcome:
        expected = {
            "D1_stale_threshold",
            "D2_missing_rule",
            "D3_contradictory",
            "D4_stale_reference_data",
            "D5_boundary_error",
            "D6_dead_code",
            "D7_conformant",
        }
        hunts = [outcome.hunt for outcome in self.outcomes]
        if set(hunts) != expected or len(set(hunts)) != 7:
            raise ValueError("a hunt batch must contain each D1-D7 hunt exactly once")
        if not any(outcome == self.selected for outcome in self.outcomes):
            raise ValueError("selected outcome must be one of the seven hunts")
        return self


class PolicyHunt(Protocol):
    drift_type: DriftType

    def run(
        self,
        *,
        clause: RegulationClause,
        tools: ToolLayer,
        model: DecisionModel,
        program_scope: str | None = None,
        budget: BudgetSpec | None = None,
        entailer: Entailer | None = None,
        clock: Callable[[], float] = time.monotonic,
        min_successful_observations_before_abstention: int = 1,
    ) -> HuntOutcome: ...


class _EvidenceGuardModel:
    """Turn an under-evidenced finding proposal into abstention before the loop."""

    # DECISION (pre-emission evidence): class evidence is checked on the model
    # response + transcript before InvestigationLoop can verify or emit it.
    def __init__(
        self,
        inner: DecisionModel,
        hunt: BasePolicyHunt,
        clause: RegulationClause,
    ) -> None:
        self.inner = inner
        self.hunt = hunt
        self.clause = clause
        self.model_id = inner.model_id
        self.temperature = inner.temperature
        self.seed = inner.seed

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        response = self.inner.respond(
            system_prompt=system_prompt,
            question=question,
            transcript=transcript,
        )
        if response.kind != "finding":
            return response
        errors = self.hunt.validate_response(response, transcript, self.clause)
        if not errors:
            return response
        reason = "policy evidence guard: " + "; ".join(errors)
        return AgentResponse(
            kind="abstain",
            thought="Required class evidence is incomplete; withhold the proposal.",
            abstention_reason=reason,
            final_answer=f"Abstained: {reason}",
            token_count=response.token_count,
            raw_provider_text=response.raw_provider_text,
        )


class BasePolicyHunt:
    """Shared loop orchestration; class modules own evidence semantics."""

    drift_type: DriftType

    def run(
        self,
        *,
        clause: RegulationClause,
        tools: ToolLayer,
        model: DecisionModel,
        program_scope: str | None = None,
        budget: BudgetSpec | None = None,
        entailer: Entailer | None = None,
        clock: Callable[[], float] = time.monotonic,
        min_successful_observations_before_abstention: int = 1,
    ) -> HuntOutcome:
        # Retained for source compatibility with config-1 callers; M4-X makes
        # the class table authoritative instead of accepting a global scalar.
        del min_successful_observations_before_abstention
        guarded = _EvidenceGuardModel(model, self, clause)
        trajectory = InvestigationLoop(
            tools,
            model=guarded,
            budget=budget,
            entailer=entailer,
            clock=clock,
            min_successful_observations_before_abstention=(
                evidence_minimum_for(self.drift_type)
            ),
        ).run(build_hunt_prompt(self.drift_type, clause, program_scope))

        if trajectory.abstained:
            return HuntOutcome(
                hunt=self.drift_type,
                finding=None,
                confidence=None,
                verification=trajectory.verification,
                verification_tier=(
                    trajectory.verification.tier
                    if trajectory.verification is not None
                    else None
                ),
                trajectory=trajectory,
                abstained=True,
                abstention_reason=trajectory.abstention_reason,
            )

        errors = self.validate_trajectory(trajectory)
        if errors:
            reason = "policy result guard: " + "; ".join(errors)
            withheld = Trajectory.model_validate(
                {
                    **trajectory.model_dump(),
                    "finding": None,
                    "abstained": True,
                    "abstention_reason": reason,
                    "final_answer": f"Abstained: {reason}",
                }
            )
            return HuntOutcome(
                hunt=self.drift_type,
                finding=None,
                confidence=None,
                verification=withheld.verification,
                verification_tier=(
                    withheld.verification.tier
                    if withheld.verification is not None
                    else None
                ),
                trajectory=withheld,
                abstained=True,
                abstention_reason=reason,
            )

        verification = trajectory.verification
        tier = verification.tier
        return HuntOutcome(
            hunt=self.drift_type,
            finding=trajectory.finding,
            confidence=confidence_for_tier(tier),
            verification=verification,
            verification_tier=tier,
            trajectory=trajectory,
            abstained=False,
            abstention_reason=None,
        )

    def validate_response(
        self,
        response: AgentResponse,
        transcript: list[dict[str, Any]],
        clause: RegulationClause,
    ) -> list[str]:
        errors: list[str] = []
        prediction = response.prediction
        if prediction is None:
            return ["finding response has no prediction"]
        _normalize_program_source_files(response, transcript)
        prediction = response.prediction
        if prediction.drift_type != self.drift_type:
            errors.append(
                f"proposal type {prediction.drift_type} does not match {self.drift_type}"
            )
        if prediction.regulation_clause != clause:
            errors.append("proposal clause differs from the requested clause")
        errors.extend(_static_claim_source_token_errors(response, transcript))
        return errors

    def validate_trajectory(self, trajectory: Trajectory) -> list[str]:
        if (
            trajectory.finding is None
            or trajectory.verification is None
            or not trajectory.verification.verified
        ):
            return ["verification did not authorize a finding"]
        # DECISION (M4-X X3′): a Tier-3 result remains visible in the full
        # VerificationResult but cannot authorize config-2 emission. A Tier-1/2
        # result must also be tied to a source-pointed trajectory observation.
        errors = []
        if trajectory.verification.tier == VerificationTier.ENTAILMENT:
            errors.append(
                "Tier-3-only finding lacks required Tier-2 code-fact verification"
            )
        if not _has_bound_code_fact(trajectory):
            errors.append(
                "finding lacks a code-fact observation bound to its claimed locus"
            )
        return errors


def transcript_tools(transcript: list[dict[str, Any]]) -> list[str]:
    return [
        str(step["tool"])
        for step in transcript
        if not step.get("error") and step.get("observation_summary")
    ]


def observations(
    transcript: list[dict[str, Any]], tool: str
) -> list[Any]:
    values: list[Any] = []
    for step in transcript:
        if step["tool"] != tool or step.get("error"):
            continue
        try:
            values.append(json.loads(step["observation_summary"]))
        except (json.JSONDecodeError, TypeError):
            continue
    return values


def _observed_program_sources(
    transcript: list[dict[str, Any]],
) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    for value in observations(transcript, "read_program"):
        if not isinstance(value, dict):
            continue
        program = value.get("program")
        path = value.get("path")
        if isinstance(program, str) and isinstance(path, str):
            sources.setdefault(_source_stem(program), set()).add(_basename(path))
    return sources


def _is_program_source_file(
    locus: SourceLocus,
    *,
    observed_sources: dict[str, set[str]],
) -> bool:
    if not locus.file:
        return False
    filename = _basename(locus.file)
    program_stem = _source_stem(locus.program)
    if filename in observed_sources.get(program_stem, set()):
        return True
    suffix = next(
        (
            candidate
            for candidate in _PROGRAM_SOURCE_SUFFIXES
            if filename.endswith(candidate)
        ),
        None,
    )
    return filename == _basename(locus.program) or (
        suffix is not None and filename[: -len(suffix)] == program_stem
    )


def _normalize_program_source_files(
    response: AgentResponse,
    transcript: list[dict[str, Any]],
) -> None:
    """Normalize program filenames while retaining measurable trajectory telemetry."""

    # DECISION (M4-X X1): mutate the host-side response copy so every caller
    # records the normalized prediction plus an audit marker, while
    # raw_provider_text preserves what the model actually sent.
    prediction = response.prediction
    if prediction is None:
        return
    observed_sources = _observed_program_sources(transcript)
    payload = prediction.model_dump(mode="json")
    normalized_loci = 0
    normalized_labels = 0
    for locus in payload["code_locus"]["loci"]:
        typed = SourceLocus.model_validate(locus)
        if _is_program_source_file(typed, observed_sources=observed_sources):
            locus["file"] = None
            normalized_loci += 1
    for ref in payload["labels"]["line_level"]:
        typed = SourceLocus(
            program=ref["program"],
            paragraph=None,
            file=ref.get("file"),
            line_span=(ref["line"], ref["line"]),
        )
        if _is_program_source_file(typed, observed_sources=observed_sources):
            ref["file"] = None
            normalized_labels += 1
    if not normalized_loci and not normalized_labels:
        return

    response.prediction = DriftPrediction.model_validate(payload)
    if _NORMALIZATION_MARKER not in response.thought:
        response.thought += (
            "\n[policy telemetry: "
            f"{_NORMALIZATION_MARKER}; loci={normalized_loci}; "
            f"line_refs={normalized_labels}]"
        )


def _same_program(left: str, right: str) -> bool:
    return _source_stem(left) == _source_stem(right)


def _overlaps(locus: SourceLocus, start: int, end: int) -> bool:
    locus_start, locus_end = locus.line_span
    return start <= locus_end and locus_start <= end


def _source_ref_matches(locus: SourceLocus, value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    program = value.get("program")
    start = value.get("line_start")
    end = value.get("line_end")
    return (
        isinstance(program, str)
        and isinstance(start, int)
        and isinstance(end, int)
        and _same_program(locus.program, program)
        and _overlaps(locus, start, end)
    )


def _step_binds_locus(step: ToolCall, locus: SourceLocus) -> bool:
    try:
        value = json.loads(step.observation_summary)
    except (json.JSONDecodeError, TypeError):
        return False
    if step.tool == "read_paragraph":
        return isinstance(value, dict) and _source_ref_matches(locus, value.get("ref"))
    if step.tool == "grep" and isinstance(value, dict):
        return any(
            isinstance(match, dict)
            and isinstance(match.get("program"), str)
            and isinstance(match.get("line"), int)
            and _same_program(locus.program, match["program"])
            and _overlaps(locus, match["line"], match["line"])
            for match in value.get("matches", [])
        )
    if step.tool == "trace_variable" and isinstance(value, dict):
        return any(
            isinstance(site, dict) and _source_ref_matches(locus, site.get("ref"))
            for site in value.get("sites", [])
        )
    if step.tool == "slice_on" and isinstance(value, dict):
        return any(
            isinstance(statement, dict)
            and _source_ref_matches(locus, statement.get("ref"))
            for statement in value.get("statements", [])
        )
    if step.tool == "get_data_layout" and isinstance(value, dict):
        return _source_ref_matches(locus, value.get("source"))
    if step.tool == "resolve_copybook" and isinstance(value, dict) and locus.file:
        wanted = _basename(locus.file)
        for entry in value.get("line_map", []):
            if not isinstance(entry, dict):
                continue
            source_file = entry.get("source_file")
            source_start = entry.get("source_line_start")
            expanded_start = entry.get("expanded_start")
            expanded_end = entry.get("expanded_end")
            if not (
                isinstance(source_file, str)
                and _basename(source_file) == wanted
                and isinstance(source_start, int)
                and isinstance(expanded_start, int)
                and isinstance(expanded_end, int)
            ):
                continue
            source_end = source_start + expanded_end - expanded_start
            if _overlaps(locus, source_start, source_end):
                return True
    return False


def _bound_source_texts(step: ToolCall, locus: SourceLocus) -> list[str]:
    """Return source-bearing text from one observation bound to ``locus``."""

    if not _step_binds_locus(step, locus):
        return []
    try:
        value = json.loads(step.observation_summary)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, dict):
        return []
    if step.tool == "read_paragraph":
        code = value.get("code")
        return [code] if isinstance(code, str) else []
    if step.tool == "resolve_copybook":
        text = value.get("text")
        return [text] if isinstance(text, str) else []
    if step.tool == "grep":
        return [
            match["text"]
            for match in value.get("matches", [])
            if (
                isinstance(match, dict)
                and isinstance(match.get("text"), str)
                and isinstance(match.get("program"), str)
                and isinstance(match.get("line"), int)
                and _same_program(locus.program, match["program"])
                and _overlaps(locus, match["line"], match["line"])
            )
        ]
    if step.tool == "trace_variable":
        return [
            site["excerpt"]
            for site in value.get("sites", [])
            if (
                isinstance(site, dict)
                and isinstance(site.get("excerpt"), str)
                and _source_ref_matches(locus, site.get("ref"))
            )
        ]
    if step.tool == "slice_on":
        return [
            statement["text"]
            for statement in value.get("statements", [])
            if (
                isinstance(statement, dict)
                and isinstance(statement.get("text"), str)
                and _source_ref_matches(locus, statement.get("ref"))
            )
        ]
    return []


def _static_claim_source_token_errors(
    response: AgentResponse,
    transcript: list[dict[str, Any]],
) -> list[str]:
    """Fail closed when static hooks are prose rather than observed tokens."""

    prediction = response.prediction
    static_claim = response.static_claim
    if prediction is None or static_claim is None:
        return []
    claimed_tokens = {
        "literal": static_claim.literal,
        "comparator": static_claim.comparator,
    }
    if all(token is None for token in claimed_tokens.values()):
        return []

    steps = [ToolCall.model_validate(step) for step in transcript]
    source_texts = [
        text
        for step in steps
        if step.error is None and step.observation_summary
        for locus in prediction.code_locus.loci
        for text in _bound_source_texts(step, locus)
    ]
    errors: list[str] = []
    for field, token in claimed_tokens.items():
        if token is None:
            continue
        if not token or not any(token in text for text in source_texts):
            errors.append(
                "static-claim source-token validator: "
                f"{field} {token!r} is not an exact substring of any "
                "source-bearing observation bound to the claimed loci"
            )
    return errors


def _has_bound_code_fact(trajectory: Trajectory) -> bool:
    finding = trajectory.finding
    if finding is None:
        return False
    return any(
        _step_binds_locus(step, locus)
        for step in trajectory.steps
        if step.error is None and step.observation_summary
        for locus in finding.code_locus.loci
    )


def require_tools(
    transcript: list[dict[str, Any]], required: set[str]
) -> list[str]:
    missing = required - set(transcript_tools(transcript))
    if not missing:
        return []
    return ["required tool evidence missing: " + ", ".join(sorted(missing))]


def _build_registry() -> dict[DriftType, BasePolicyHunt]:
    from cobol_archaeologist.agent.hunts.d1 import D1Hunt
    from cobol_archaeologist.agent.hunts.d2 import D2Hunt
    from cobol_archaeologist.agent.hunts.d3 import D3Hunt
    from cobol_archaeologist.agent.hunts.d4 import D4Hunt
    from cobol_archaeologist.agent.hunts.d5 import D5Hunt
    from cobol_archaeologist.agent.hunts.d6 import D6Hunt
    from cobol_archaeologist.agent.hunts.d7 import D7Hunt

    hunts = [D1Hunt(), D2Hunt(), D3Hunt(), D4Hunt(), D5Hunt(), D6Hunt(), D7Hunt()]
    return {hunt.drift_type: hunt for hunt in hunts}


HUNT_REGISTRY = _build_registry()


def get_hunt(drift_type: str) -> BasePolicyHunt:
    try:
        return HUNT_REGISTRY[drift_type]
    except KeyError:
        raise KeyError(f"no policy hunt registered for {drift_type!r}") from None
