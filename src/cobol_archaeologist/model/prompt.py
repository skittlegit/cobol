"""Detection policy and deterministic decision seam (Track C, T3.4/T3.5).

The investigation loop depends on :class:`DecisionModel`, not on a provider
SDK.  Production adapters can implement that protocol; offline gates use
:class:`CachedDecisionModel`, whose responses are committed JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.model.verify import ExecProbe, StaticClaim
from cobol_archaeologist.schemas import DriftInstance

MODEL_ID = "claude-3-5-sonnet-20241022"
MODEL_TEMPERATURE = 0.0
MODEL_SEED = 0

ToolName = Literal[
    "read_paragraph",
    "read_program",
    "find_callers",
    "find_callees",
    "trace_variable",
    "slice_on",
    "resolve_copybook",
    "get_data_layout",
    "grep",
    "run_cobol",
    "search_regulations",
]

SYSTEM_PROMPT = """\
Investigate whether COBOL behavior matches the cited regulation.
Use only the supplied ToolLayer tools. Call one tool per turn and keep
observations bounded. A proposed finding must be DriftInstance-shaped and
include concrete execution/static evidence hooks when available. The runtime
will verify every proposed finding; if evidence is insufficient, abstain.
"""


class AgentResponse(BaseModel):
    """One cached or live model turn.

    ``token_count`` is the provider-reported turn-token usage and is part of
    the enforced run budget.  Keeping the complete response in the trajectory
    makes replay independent of another model call.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "finding", "abstain"]
    thought: str = Field(min_length=1)
    tool: ToolName | None = None
    arguments: dict[str, Any] = {}
    prediction: DriftInstance | None = None
    claim: str | None = None
    exec_probe: ExecProbe | None = None
    static_claim: StaticClaim | None = None
    abstention_reason: str | None = None
    final_answer: str | None = None
    token_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _kind_shape(self) -> AgentResponse:
        if self.kind == "tool":
            if self.tool is None:
                raise ValueError("a tool response requires tool")
            if self.prediction is not None or self.abstention_reason is not None:
                raise ValueError("a tool response cannot carry a finding/abstention")
        elif self.kind == "finding":
            if self.prediction is None or not self.claim:
                raise ValueError("a finding response requires prediction and claim")
            if self.tool is not None or self.abstention_reason is not None:
                raise ValueError("a finding response cannot carry a tool/abstention")
            if not self.final_answer:
                raise ValueError("a finding response requires final_answer")
        else:
            if not self.abstention_reason:
                raise ValueError("an abstain response requires abstention_reason")
            if self.tool is not None or self.prediction is not None:
                raise ValueError("an abstain response cannot carry a tool/finding")
        return self


class DecisionModel(Protocol):
    """Provider-neutral next-action seam consumed by InvestigationLoop."""

    model_id: str
    temperature: float
    seed: int | None

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse: ...


class CachedDecisionModel:
    """Deterministic offline model backed by a committed JSON response list."""

    # DECISION (provider seam): cache replay implements the same tiny protocol
    # as a live provider adapter; the loop never imports an SDK or opens a cache.
    def __init__(
        self,
        cache_path: Path,
        *,
        model_id: str = MODEL_ID,
        temperature: float = MODEL_TEMPERATURE,
        seed: int | None = MODEL_SEED,
    ) -> None:
        if temperature != 0:
            raise ValueError("T3.5 deterministic cache requires temperature=0")
        self.cache_path = Path(cache_path)
        self.model_id = model_id
        self.temperature = temperature
        self.seed = seed
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise TypeError("cached model responses must be a JSON list")
        self._responses = [AgentResponse.model_validate(row) for row in raw]
        self._cursor = 0

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        del system_prompt, question, transcript
        if self._cursor >= len(self._responses):
            raise RuntimeError(
                f"cached decision model exhausted after {self._cursor} responses"
            )
        response = self._responses[self._cursor]
        self._cursor += 1
        # Return a copy so a caller cannot mutate the committed replay sequence.
        return response.model_copy(deep=True)
