"""Replayable trajectory models for the bounded T3.5 investigation loop."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.model.prompt import AgentResponse
from cobol_archaeologist.model.verify import VerificationResult
from cobol_archaeologist.schemas import DriftInstance


class BudgetSpec(BaseModel):
    """Hard run limits. Crossing any limit forces abstention."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=8, ge=0)
    max_tokens: int = Field(default=4096, ge=1)
    wall_clock_timeout_s: float = Field(default=30.0, gt=0)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    tool: str
    arguments: dict[str, Any]
    observation_summary: str
    observation_truncated: bool
    error: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)


class Trajectory(BaseModel):
    """A complete replay record, including the verifier's full tier ladder."""

    model_config = ConfigDict(extra="forbid")

    question: str
    steps: list[ToolCall]
    # DECISION (replay completeness): ToolCall alone cannot reproduce model
    # choices, so retain complete turns alongside the work-order's steps shape.
    model_responses: list[AgentResponse]
    verification: VerificationResult | None
    finding: DriftInstance | None
    abstained: bool
    abstention_reason: str | None
    budget: BudgetSpec
    budget_exhausted: bool
    tokens_used: int = Field(ge=0)
    final_answer: str
    model_id: str
    seed: int | None

    @model_validator(mode="after")
    def _emission_invariants(self) -> Trajectory:
        if self.abstained:
            if self.finding is not None:
                raise ValueError("an abstained trajectory cannot emit a finding")
            if not self.abstention_reason:
                raise ValueError("an abstained trajectory requires a reason")
        else:
            if self.finding is None:
                raise ValueError("a non-abstained trajectory must emit a finding")
            if self.abstention_reason is not None:
                raise ValueError("a non-abstained trajectory cannot have a reason")
            if self.verification is None or not self.verification.verified:
                raise ValueError("a finding may be emitted only after verification")
        if self.budget_exhausted and not self.abstained:
            raise ValueError("budget exhaustion must terminate in abstention")
        return self
