"""Typed, non-contract records for evaluation runs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.trajectory import Trajectory
from cobol_archaeologist.model.verify import VerificationResult
from cobol_archaeologist.schemas import DriftInstance


class EvaluationRecord(BaseModel):
    """One paired gold/system result.

    The runner constructs this only after the system turn is complete; the
    system-facing context is a separate, gold-hidden object in ``eval.run``.
    """

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    gold: DriftInstance
    prediction: DriftInstance | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification: VerificationResult | None = None
    trajectory: Trajectory | None = None
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
        if self.infrastructure_error:
            if self.prediction is not None or self.trajectory is not None:
                raise ValueError("infrastructure failures cannot carry system output")
            return self
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
