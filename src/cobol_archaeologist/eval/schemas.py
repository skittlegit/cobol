"""Typed, non-contract records for evaluation runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.trajectory import Trajectory
from cobol_archaeologist.model.verify import VerificationResult, VerificationTier
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction, DriftType


class AgentHuntTrace(BaseModel):
    """One retained D1-D7 hunt, including non-selected abstentions."""

    model_config = ConfigDict(extra="forbid")

    hunt: DriftType
    selected: bool = False
    finding: DriftPrediction | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None
    verification_tier: VerificationTier | None
    trajectory: Trajectory
    abstained: bool
    abstention_reason: str | None

    @model_validator(mode="after")
    def _outcome_shape(self) -> AgentHuntTrace:
        if self.abstained:
            if (
                self.finding is not None
                or self.confidence is not None
                or not self.abstention_reason
            ):
                raise ValueError("an abstained hunt trace requires a reason only")
        else:
            if (
                self.finding is None
                or self.confidence is None
                or self.verification is None
                or not self.verification.verified
                or self.verification_tier != self.verification.tier
            ):
                raise ValueError("an emitted hunt trace requires verified output")
        if self.trajectory.finding != self.finding:
            raise ValueError("hunt trace finding must match its trajectory")
        if (
            self.trajectory.abstained != self.abstained
            or self.trajectory.verification != self.verification
            or self.trajectory.abstention_reason != self.abstention_reason
        ):
            raise ValueError("hunt trace outcome must match its trajectory")
        return self


class RunValidity(BaseModel):
    """Auditable run-level gates; zero infrastructure failures is insufficient."""

    model_config = ConfigDict(extra="forbid")

    completed_rows: int = Field(ge=0)
    available_rows: int = Field(ge=0)
    infrastructure_failures: int = Field(ge=0)
    provider_turns: int = Field(ge=0)
    contract_rejections: int = Field(ge=0)
    contract_rejection_rate: float = Field(ge=0, le=1)
    non_null_predictions: int = Field(ge=0)
    non_null_prediction_rate: float = Field(ge=0, le=1)
    successful_tool_observations: int | None = Field(default=None, ge=0)
    mean_successful_tool_observations: float | None = Field(default=None, ge=0)
    status: Literal[
        "VALID",
        "HALTED_CONTRACT_REJECTIONS",
        "INVALID_AGENT_RUN",
        "NOT_EVALUABLE",
    ]
    failed_gates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _arithmetic_and_status(self) -> RunValidity:
        if self.available_rows + self.infrastructure_failures != self.completed_rows:
            raise ValueError("available and infrastructure counts must sum to completed")
        if self.contract_rejections > self.provider_turns:
            raise ValueError("contract rejections cannot exceed provider turns")
        if self.non_null_predictions > self.available_rows:
            raise ValueError("predictions cannot exceed available rows")
        expected_contract_rate = (
            self.contract_rejections / self.provider_turns
            if self.provider_turns
            else 0.0
        )
        expected_prediction_rate = (
            self.non_null_predictions / self.available_rows
            if self.available_rows
            else 0.0
        )
        if abs(self.contract_rejection_rate - expected_contract_rate) > 1e-12:
            raise ValueError("contract rejection rate does not match its counts")
        if abs(self.non_null_prediction_rate - expected_prediction_rate) > 1e-12:
            raise ValueError("prediction rate does not match its counts")
        if (self.successful_tool_observations is None) != (
            self.mean_successful_tool_observations is None
        ):
            raise ValueError("agent tool count and mean must be present together")
        if self.status == "VALID" and self.failed_gates:
            raise ValueError("a VALID run cannot contain failed gates")
        return self


class EvaluationRecord(BaseModel):
    """One paired gold/system result.

    The runner constructs this only after the system turn is complete; the
    system-facing context is a separate, gold-hidden object in ``eval.run``.
    """

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    gold: DriftInstance
    prediction: DriftPrediction | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None = None
    trajectory: Trajectory | None = None
    agent_hunts: list[AgentHuntTrace] = Field(default_factory=list)
    abstained: bool
    abstention_reason: str | None = None
    infrastructure_error: str | None = None
    system_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def _shape(self) -> EvaluationRecord:
        if self.instance_id != self.gold.instance_id:
            raise ValueError("evaluation instance_id must match gold")
        if (
            self.prediction is not None
            and self.prediction.instance_id != self.instance_id
        ):
            raise ValueError("prediction instance_id must match evaluation record")
        if self.infrastructure_error:
            if (
                self.prediction is not None
                or self.trajectory is not None
                or self.agent_hunts
            ):
                raise ValueError("infrastructure failures cannot carry system output")
            return self
        if self.agent_hunts:
            hunts = [trace.hunt for trace in self.agent_hunts]
            if len(hunts) != 7 or len(set(hunts)) != 7:
                raise ValueError("agent_hunts must retain each D1-D7 hunt exactly once")
            selected = [trace for trace in self.agent_hunts if trace.selected]
            if len(selected) != 1:
                raise ValueError("agent_hunts must mark exactly one selected hunt")
            if self.trajectory != selected[0].trajectory:
                raise ValueError("record trajectory must equal the selected hunt")
            if (
                self.prediction != selected[0].finding
                or self.confidence != selected[0].confidence
                or self.verification != selected[0].verification
                or self.abstained != selected[0].abstained
            ):
                raise ValueError("record output must equal the selected hunt outcome")
        if self.abstained:
            if self.prediction is not None:
                raise ValueError("abstention cannot carry a prediction")
            if not self.abstention_reason:
                raise ValueError("abstention requires a reason")
        else:
            if self.prediction is None or self.trajectory is None:
                raise ValueError("answered records require prediction and trajectory")
            if self.verification is None or not self.verification.verified:
                raise ValueError("answered records require successful verification")
            if self.confidence is None:
                raise ValueError("answered records require confidence")
        return self


class TrajectoryAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    replayable: bool
    evidence_path_ok: bool
    code_fact_ok: bool
    budget_ok: bool
    shortcut_free: bool
    reasons: list[str] = Field(default_factory=list)
