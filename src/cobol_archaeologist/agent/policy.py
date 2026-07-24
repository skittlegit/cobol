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
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
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
from cobol_archaeologist.schemas import DriftInstance, DriftType, RegulationClause
from cobol_archaeologist.tool_types import ToolLayer

_TIER_CONFIDENCE = {
    VerificationTier.EXECUTED: 0.95,
    VerificationTier.STATIC: 0.85,
    VerificationTier.ENTAILMENT: 0.60,
}


def confidence_for_tier(tier: VerificationTier) -> float:
    """Return the frozen confidence assigned to a verified evidence tier."""

    return _TIER_CONFIDENCE[tier]


# DECISION (frozen schema): confidence and verifier provenance wrap the
# DriftInstance instead of widening schemas.py, which remains contract-frozen.
class HuntOutcome(BaseModel):
    """Typed policy output consumed by T4 evaluation."""

    model_config = ConfigDict(extra="forbid")

    hunt: DriftType
    finding: DriftInstance | None
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
    ) -> HuntOutcome:
        guarded = _EvidenceGuardModel(model, self, clause)
        trajectory = InvestigationLoop(
            tools,
            model=guarded,
            budget=budget,
            entailer=entailer,
            clock=clock,
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
        if prediction.drift_type != self.drift_type:
            errors.append(
                f"proposal type {prediction.drift_type} does not match {self.drift_type}"
            )
        if prediction.regulation_clause != clause:
            errors.append("proposal clause differs from the requested clause")
        return errors

    def validate_trajectory(self, trajectory: Trajectory) -> list[str]:
        if (
            trajectory.finding is None
            or trajectory.verification is None
            or not trajectory.verification.verified
        ):
            return ["verification did not authorize a finding"]
        return []


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
