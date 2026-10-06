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
    respond_with_contract_repair,
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
        min_successful_observations_before_abstention: int = 1,
        system_prompt: str = SYSTEM_PROMPT,
        finding_guard: (
            Callable[[AgentResponse, list[dict[str, Any]]], list[str]] | None
        ) = None,
        response_guard: (
            Callable[[AgentResponse, list[dict[str, Any]]], list[str]] | None
        ) = None,
        state_renderer: Callable[[list[AgentResponse]], str] | None = None,
    ) -> None:
        if min_successful_observations_before_abstention < 1:
            raise ValueError(
                "min_successful_observations_before_abstention must be >= 1"
            )
        self.tools = tools
        self.model = model
        self.budget = budget or BudgetSpec()
        self.entailer = entailer
        self.clock = clock
        self.min_successful_observations_before_abstention = (
            min_successful_observations_before_abstention
        )
        self.system_prompt = system_prompt
        self.finding_guard = finding_guard
        self.response_guard = response_guard
        self.state_renderer = state_renderer

    def run(self, question: str) -> Trajectory:
        started = self.clock()
        steps: list[ToolCall] = []
        responses: list[AgentResponse] = []
        tokens_used = 0
        contract_repairs = 0
        model_question = question

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
                contract_repairs=contract_repairs,
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

        def repair_allowed(rejected: AgentResponse) -> bool:
            return (
                tokens_used + rejected.token_count <= self.budget.max_tokens
                and self.clock() - started < self.budget.wall_clock_timeout_s
            )

        while True:
            if self.clock() - started >= self.budget.wall_clock_timeout_s:
                return exhausted("wall-clock budget exhausted")
            semantic_turns = len(responses) - contract_repairs
            if semantic_turns >= self.budget.max_steps:
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
            turn_question = model_question
            if self.state_renderer is not None:
                rendered_state = self.state_renderer(responses).strip()
                if rendered_state:
                    turn_question = f"{turn_question}\n\n{rendered_state}"
            try:
                response, attempts = respond_with_contract_repair(
                    self.model,
                    system_prompt=self.system_prompt,
                    question=turn_question,
                    transcript=transcript,
                    max_repairs=self.budget.max_contract_repairs - contract_repairs,
                    repair_allowed=repair_allowed,
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

            responses.extend(attempts)
            contract_repairs += len(attempts) - 1
            tokens_used += sum(attempt.token_count for attempt in attempts)
            if tokens_used > self.budget.max_tokens:
                return exhausted("token budget exhausted")
            if self.clock() - started >= self.budget.wall_clock_timeout_s:
                return exhausted("wall-clock budget exhausted")

            if self.response_guard is not None:
                response_errors = self.response_guard(response, transcript)
                if response_errors:
                    model_question = (
                        f"{question}\n\n"
                        "Your response cannot be accepted because its "
                        "case-local state is invalid: "
                        + "; ".join(response_errors)
                        + ". Return a corrected next action with a complete, "
                        "observation-linked state."
                    )
                    continue

            if response.kind == "abstain":
                reason = response.abstention_reason or "model abstained"
                if response.contract_error is not None:
                    return finish(
                        abstained=True,
                        reason=reason,
                        budget_exhausted=False,
                        final_answer=response.final_answer or f"Abstained: {reason}",
                    )
                successful_observations = sum(
                    call.error is None and bool(call.observation_summary)
                    for call in steps
                )
                if (
                    successful_observations
                    < self.min_successful_observations_before_abstention
                    and len(steps) < self.budget.max_tool_calls
                    and semantic_turns < self.budget.max_steps
                ):
                    available = ", ".join(sorted(_TOOLS))
                    model_question = (
                        f"{question}\n\n"
                        "Your abstention cannot be accepted yet: this hunt has "
                        f"{successful_observations} successful bounded tool "
                        "observation(s) and requires at least "
                        f"{self.min_successful_observations_before_abstention}. "
                        "Obtain the specific missing evidence you identified. "
                        "Investigate only the stated program scope and clause; "
                        "do not infer hidden benchmark labels, source line "
                        "annotations, or mutation provenance. "
                        f"Call one authorized tool: {available}."
                    )
                    continue
                return finish(
                    abstained=True,
                    reason=reason,
                    budget_exhausted=False,
                    final_answer=response.final_answer or f"Abstained: {reason}",
                )

            if response.kind == "tool":
                if len(steps) >= self.budget.max_tool_calls:
                    return exhausted("tool-call budget exhausted")
                semantic_turn = len(responses) - contract_repairs
                call = self._call_tool(response, step=semantic_turn)
                steps.append(call)
                model_question = question
                if self.clock() - started >= self.budget.wall_clock_timeout_s:
                    return exhausted("wall-clock budget exhausted")
                continue

            successful_observations = sum(
                call.error is None and bool(call.observation_summary) for call in steps
            )
            if successful_observations < 1:
                if len(steps) >= self.budget.max_tool_calls:
                    return exhausted("tool-call budget exhausted")
                # DECISION (X7): a fluent first-turn prediction is not
                # evidence. Force one bounded successful observation before
                # constructing a Finding or invoking the verifier.
                available = ", ".join(sorted(_TOOLS))
                model_question = (
                    f"{question}\n\n"
                    "Your finding cannot be accepted yet: no successful "
                    "bounded tool observation supports it. Investigate only "
                    "the stated program scope and clause; do not infer hidden "
                    "benchmark labels, source line annotations, or mutation "
                    "provenance. "
                    f"Call one authorized tool: {available}."
                )
                continue

            if self.finding_guard is not None:
                guard_errors = self.finding_guard(response, transcript)
                if guard_errors:
                    available = ", ".join(sorted(_TOOLS))
                    model_question = (
                        f"{question}\n\n"
                        "Your candidate finding cannot be accepted yet. "
                        "The evidence guard reported: "
                        + "; ".join(guard_errors)
                        + ". Continue the same case investigation, revise or "
                        "reject the hypothesis as warranted, and obtain the "
                        "missing bounded evidence. Do not emit the same "
                        "unsupported finding again. Call one authorized tool "
                        f"when further evidence is available: {available}."
                    )
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
