"""Replayable trajectory models for the bounded T3.5 investigation loop."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.model.prompt import AgentResponse
from cobol_archaeologist.model.verify import VerificationResult
from cobol_archaeologist.schemas import DriftPrediction


class BudgetSpec(BaseModel):
    """Hard run limits. Crossing any limit forces abstention."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=8, ge=0)
    max_tokens: int = Field(default=4096, ge=1)
    wall_clock_timeout_s: float = Field(default=30.0, gt=0)
    max_contract_repairs: int = Field(default=1, ge=0)


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
    finding: DriftPrediction | None
    abstained: bool
    abstention_reason: str | None
    budget: BudgetSpec
    budget_exhausted: bool
    tokens_used: int = Field(ge=0)
    token_usage_recorded: bool = True
    contract_repairs: int = Field(default=0, ge=0)
    final_answer: str
    model_id: str
    seed: int | None

    @model_validator(mode="after")
    def _emission_invariants(self) -> Trajectory:
        recorded = all(response.token_count_recorded for response in self.model_responses)
        if self.token_usage_recorded != recorded:
            raise ValueError("trajectory token-usage status differs from its responses")
        if not self.token_usage_recorded and self.tokens_used != 0:
            raise ValueError("unrecorded trajectory usage must use the zero placeholder")
        if self.contract_repairs > self.budget.max_contract_repairs:
            raise ValueError("contract repairs exceed the frozen repair budget")
        if len(self.model_responses) - self.contract_repairs > self.budget.max_steps:
            raise ValueError("semantic model turns exceed the step budget")
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
