"""Bounded ReAct investigation loop with mandatory verify-before-emit."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory
from cobol_archaeologist.model.prompt import (
    SYSTEM_PROMPT,
    AgentResponse,
    DecisionModel,
)
from cobol_archaeologist.model.verify import Entailer, Finding, verify
from cobol_archaeologist.tool_types import RunInputs, ToolLayer

OBSERVATION_CAP_CHARS = 4000
_TOOLS = frozenset(
    {
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
    }
)


class InvestigationLoop:
    """Think -> one ToolLayer call -> observe, until verification or abstention.

    The model and ToolLayer are injected.  This module performs no provider,
    filesystem, retrieval, or concrete tool-layer access of its own.
    """

    def __init__(
        self,
        tools: ToolLayer,
        *,
        model: DecisionModel,
        budget: BudgetSpec | None = None,
        entailer: Entailer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.tools = tools
        self.model = model
        self.budget = budget or BudgetSpec()
        self.entailer = entailer
        self.clock = clock

    def run(self, question: str) -> Trajectory:
        started = self.clock()
        steps: list[ToolCall] = []
        responses: list[AgentResponse] = []
        tokens_used = 0

        def finish(
            *,
            abstained: bool,
            reason: str | None,
            budget_exhausted: bool,
            final_answer: str,
            verification=None,
            finding=None,
        ) -> Trajectory:
            return Trajectory(
                question=question,
                steps=steps,
                model_responses=responses,
                verification=verification,
                finding=finding,
                abstained=abstained,
                abstention_reason=reason,
                budget=self.budget,
                budget_exhausted=budget_exhausted,
                tokens_used=tokens_used,
                final_answer=final_answer,
                model_id=self.model.model_id,
                seed=self.model.seed,
            )

        def exhausted(reason: str) -> Trajectory:
            return finish(
                abstained=True,
                reason=reason,
                budget_exhausted=True,
                final_answer=f"Abstained: {reason}",
            )

        while True:
            if self.clock() - started >= self.budget.wall_clock_timeout_s:
                return exhausted("wall-clock budget exhausted")
            if len(responses) >= self.budget.max_steps:
                return exhausted("step budget exhausted")

            transcript = [
                {
                    "step": call.step,
                    "tool": call.tool,
                    "arguments": call.arguments,
                    "observation_summary": call.observation_summary,
                    "observation_truncated": call.observation_truncated,
                    "error": call.error,
                }
                for call in steps
            ]
            try:
                response = self.model.respond(
                    system_prompt=SYSTEM_PROMPT,
                    question=question,
                    transcript=transcript,
                )
            # Provider adapters may surface SDK-specific exceptions. Any such
            # failure is an abstention, never permission to bypass the model.
            except Exception as exc:  # noqa: BLE001
                reason = f"model response unavailable: {type(exc).__name__}: {exc}"
                return finish(
                    abstained=True,
                    reason=reason,
                    budget_exhausted=False,
                    final_answer=f"Abstained: {reason}",
                )

            responses.append(response)
            tokens_used += response.token_count
            if tokens_used > self.budget.max_tokens:
                return exhausted("token budget exhausted")
            if self.clock() - started >= self.budget.wall_clock_timeout_s:
                return exhausted("wall-clock budget exhausted")

            if response.kind == "abstain":
                reason = response.abstention_reason or "model abstained"
                return finish(
                    abstained=True,
                    reason=reason,
                    budget_exhausted=False,
                    final_answer=response.final_answer or f"Abstained: {reason}",
                )

            if response.kind == "tool":
                if len(steps) >= self.budget.max_tool_calls:
                    return exhausted("tool-call budget exhausted")
                call = self._call_tool(response, step=len(responses))
                steps.append(call)
                if self.clock() - started >= self.budget.wall_clock_timeout_s:
                    return exhausted("wall-clock budget exhausted")
                continue

            # DECISION: build through Finding.from_prediction so verifier hooks
            # stay outside the frozen DriftInstance contract, exactly as T3.4
            # designed. The trajectory emits the prediction only after verify().
            finding = Finding.from_prediction(
                response.prediction,
                claim=response.claim,
            ).model_copy(
                update={
                    "exec_probe": response.exec_probe,
                    "static_claim": response.static_claim,
                }
            )
            try:
                verification = verify(
                    finding,
                    self.tools,
                    entailer=self.entailer,
                )
            # Verification must fail closed even for backend-specific errors.
            except Exception as exc:  # noqa: BLE001
                reason = (
                    "verification unavailable; refusing emission: "
                    f"{type(exc).__name__}: {exc}"
                )
                return finish(
                    abstained=True,
                    reason=reason,
                    budget_exhausted=False,
                    final_answer=f"Abstained: {reason}",
                )

            if not verification.verified:
                reason = verification.rejected_reason or "finding was not verified"
                return finish(
                    abstained=True,
                    reason=reason,
                    budget_exhausted=False,
                    final_answer=f"Abstained: {reason}",
                    verification=verification,
                )

            return finish(
                abstained=False,
                reason=None,
                budget_exhausted=False,
                final_answer=response.final_answer or verification.evidence,
                verification=verification,
                finding=response.prediction,
            )

    def _call_tool(self, response: AgentResponse, *, step: int) -> ToolCall:
        tool = response.tool
        if tool is None or tool not in _TOOLS:
            return ToolCall(
                step=step,
                tool=str(tool),
                arguments=response.arguments,
                observation_summary="",
                observation_truncated=False,
                error=f"unsupported tool {tool!r}",
            )

        arguments = dict(response.arguments)
        if tool == "run_cobol" and isinstance(arguments.get("inputs"), dict):
            arguments["inputs"] = RunInputs.model_validate(arguments["inputs"])

        before = self.clock()
        error: str | None = None
        observation: Any = None
        try:
            observation = getattr(self.tools, tool)(**arguments)
        # Tool implementations share return shapes, not an exception base.
        # A failed observation is recorded and returned to the model.
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = max(0.0, round((self.clock() - before) * 1000, 3))

        if error is not None:
            summary, truncated = error, False
        else:
            summary, truncated = _summarize(observation)
        # Keep the original JSON-compatible arguments in the replay trace.
        return ToolCall(
            step=step,
            tool=tool,
            arguments=response.arguments,
            observation_summary=summary,
            observation_truncated=truncated,
            error=error,
            latency_ms=latency_ms,
        )


def _summarize(observation: Any) -> tuple[str, bool]:
    """Bound an observation while preserving its typed source pointers."""
    if isinstance(observation, BaseModel):
        value = observation.model_dump(mode="json")
        inherent_truncation = bool(getattr(observation, "truncated", False))
    elif isinstance(observation, list):
        value = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in observation
        ]
        inherent_truncation = any(
            bool(getattr(item, "truncated", False)) for item in observation
        )
    else:
        value = observation
        inherent_truncation = False
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > OBSERVATION_CAP_CHARS:
        return rendered[: OBSERVATION_CAP_CHARS - 1] + "…", True
    return rendered, inherent_truncation
