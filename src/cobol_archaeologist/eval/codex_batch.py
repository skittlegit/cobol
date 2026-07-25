"""Provider-neutral batch contracts for ChatGPT-authenticated Codex evaluation.

The earlier API implementation remains the source of truth for materialization,
retrieval contexts, policy evidence guards, verification, and persisted M4
records.  This module replaces only the paid provider call.  It deliberately
does not accept or forward API keys: the subprocess must authenticate through
the user's ChatGPT Codex login.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.agent.policy import (
    HuntBatchOutcome,
    HuntOutcome,
    confidence_for_tier,
    get_hunt,
)
from cobol_archaeologist.agent.trajectory import BudgetSpec, ToolCall, Trajectory
from cobol_archaeologist.model.prompt import AgentResponse, build_hunt_prompt
from cobol_archaeologist.model.verify import (
    Entailer,
    ExecProbe,
    Finding,
    StaticClaim,
    verify,
)
from cobol_archaeologist.schemas import (
    DriftPrediction,
    DriftType,
    Labels,
    SourceLocus,
)

if TYPE_CHECKING:
    from cobol_archaeologist.eval.codex_tool import ToolLogEntry
    from cobol_archaeologist.schemas import RegulationClause
    from cobol_archaeologist.tool_types import ToolLayer

AGENT_HUNTS: tuple[DriftType, ...] = (
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
)
MAX_BATCH_CASES = 5
_SECRET_ENV_NAMES = frozenset(
    {
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }
)


class SubmittedCodeLocus(BaseModel):
    """Provider-authored locus before host-side semantic validation.

    JSON-schema structured output cannot express the cross-field rule that
    multi-program loci require ``is_interprocedural=True``. Keep the submitted
    value intact here, then let ``DriftPrediction`` validate it during trusted
    input binding. A violation therefore abstains only that hunt instead of
    invalidating every row in the provider batch.
    """

    model_config = ConfigDict(extra="forbid")

    loci: list[SourceLocus] = Field(min_length=1)
    slice_vars: list[str]
    is_interprocedural: bool


class SubmittedPrediction(BaseModel):
    """Provider-authored prediction fields; trusted inputs are host-attached."""

    model_config = ConfigDict(extra="forbid")

    code_locus: SubmittedCodeLocus
    drift_type: DriftType
    target_path: str | None
    labels: Labels
    rationale: str = Field(min_length=1)

    def attach_inputs(
        self,
        *,
        instance_id: str,
        clause: RegulationClause,
    ) -> DriftPrediction:
        return DriftPrediction(
            instance_id=instance_id,
            regulation_clause=clause,
            **self.model_dump(),
        )


class SubmittedResponse(BaseModel):
    """Provider-facing final answer without provider-owned telemetry."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["finding", "abstain"]
    thought: str
    prediction: SubmittedPrediction | None
    claim: str | None
    exec_probe: ExecProbe | None
    static_claim: StaticClaim | None
    abstention_reason: str | None
    final_answer: str

    @model_validator(mode="after")
    def _exclusive_shape(self) -> SubmittedResponse:
        if self.kind == "finding":
            if self.prediction is None or not self.claim:
                raise ValueError("a finding requires prediction and claim")
            if self.abstention_reason is not None:
                raise ValueError("a finding cannot carry an abstention reason")
        else:
            if self.prediction is not None or self.claim is not None:
                raise ValueError("an abstention cannot carry a finding")
            if self.exec_probe is not None or self.static_claim is not None:
                raise ValueError("an abstention cannot carry verifier hooks")
            if not self.abstention_reason:
                raise ValueError("an abstention requires a reason")
        return self


class SubmittedHunt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hunt: DriftType
    response: SubmittedResponse


class SubmittedAgentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=r"^drift_9\d{5}$")
    d1: SubmittedResponse = Field(alias="D1_stale_threshold")
    d2: SubmittedResponse = Field(alias="D2_missing_rule")
    d3: SubmittedResponse = Field(alias="D3_contradictory")
    d4: SubmittedResponse = Field(alias="D4_stale_reference_data")
    d5: SubmittedResponse = Field(alias="D5_boundary_error")
    d6: SubmittedResponse = Field(alias="D6_dead_code")
    d7: SubmittedResponse = Field(alias="D7_conformant")

    @property
    def hunts(self) -> list[SubmittedHunt]:
        """Expose the fixed wire fields through the existing internal API."""

        return [
            SubmittedHunt(hunt=hunt, response=getattr(self, f"d{index}"))
            for index, hunt in enumerate(AGENT_HUNTS, start=1)
        ]


class CodexBatchEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SubmittedAgentCase] = Field(
        min_length=1,
        max_length=MAX_BATCH_CASES,
    )


class SubmittedBaselineCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(pattern=r"^drift_9\d{5}$")
    # Dense-RAG must identify which detector-visible retrieved clause supports
    # its finding. Oracle-slice has one visible clause and therefore uses null.
    clause_index: int | None
    response: SubmittedResponse


class CodexBaselineEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SubmittedBaselineCase] = Field(
        min_length=1,
        max_length=MAX_BATCH_CASES,
    )


class CodexUsage(BaseModel):
    # Codex CLI may add provider-specific usage counters in later releases.
    # The complete raw event remains persisted; these three stable counters are
    # the only ones required for exact response-token allocation.
    model_config = ConfigDict(extra="ignore")

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ParsedCodexEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_message: str
    usage: CodexUsage
    thread_id: str | None
    events: list[dict[str, Any]]


def sanitized_codex_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Copy an environment while stripping every supported API-key route."""

    source = os.environ if source is None else source
    return {
        name: value
        for name, value in source.items()
        if name.upper() not in _SECRET_ENV_NAMES
    }


def strict_codex_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic schema to the Codex structured-output subset.

    Structured output requires every property name in ``required``. Nullable
    fields remain nullable through their ``anyOf`` branch; requiring the key
    does not require a non-null value. Pydantic re-validates the returned JSON,
    so validation annotations outside the provider subset are unnecessary.
    """

    schema = model.model_json_schema()

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            for keyword in (
                "default",
                "format",
                "maxItems",
                "maxLength",
                "maximum",
                "minItems",
                "minLength",
                "minimum",
                "multipleOf",
                "pattern",
                "uniqueItems",
            ):
                node.pop(keyword, None)
            prefix_items = node.pop("prefixItems", None)
            if isinstance(prefix_items, list) and prefix_items:
                node["items"] = (
                    prefix_items[0]
                    if all(item == prefix_items[0] for item in prefix_items)
                    else {"anyOf": prefix_items}
                )
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


def allocate_tokens(total: int, slots: int) -> list[int]:
    """Allocate one batched provider turn exactly across persisted responses."""

    if total < 0:
        raise ValueError("total token count cannot be negative")
    if slots < 1:
        raise ValueError("slots must be positive")
    base, remainder = divmod(total, slots)
    return [base + (index < remainder) for index in range(slots)]


def _exact_unique(values: Sequence[str], expected: Iterable[str], noun: str) -> None:
    expected_list = list(expected)
    if len(values) != len(set(values)):
        raise ValueError(f"{noun} contain duplicates")
    if set(values) != set(expected_list) or len(values) != len(expected_list):
        raise ValueError(f"{noun} do not match the requested set")


def validate_agent_envelope(
    envelope: CodexBatchEnvelope,
    aliases: Sequence[str],
) -> None:
    """Require exact case aliases and all seven hunts before any record builds."""

    _exact_unique(
        [result.alias for result in envelope.results],
        aliases,
        "response aliases",
    )
    for result in envelope.results:
        hunts = [item.hunt for item in result.hunts]
        if len(hunts) != len(set(hunts)) or set(hunts) != set(AGENT_HUNTS):
            raise ValueError(
                f"{result.alias} must contain each D1-D7 hunt exactly once"
            )


def validate_baseline_envelope(
    envelope: CodexBaselineEnvelope,
    aliases: Sequence[str],
) -> None:
    _exact_unique(
        [result.alias for result in envelope.results],
        aliases,
        "response aliases",
    )


def parse_codex_events(stdout: str) -> ParsedCodexEvents:
    """Parse ``codex exec --json`` output without discarding replay evidence."""

    events: list[dict[str, Any]] = []
    final_message: str | None = None
    thread_id: str | None = None
    usage = CodexUsage()
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Codex event line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(event, dict):
            raise TypeError(f"Codex event line {line_number} is not an object")
        events.append(event)
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str):
                    final_message = text
        if event.get("type") == "turn.completed":
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = CodexUsage.model_validate(raw_usage)
    if final_message is None:
        raise ValueError("Codex event stream has no completed agent message")
    return ParsedCodexEvents(
        final_message=final_message,
        usage=usage,
        thread_id=thread_id,
        events=events,
    )


def bind_submitted_response(
    submitted: SubmittedResponse,
    *,
    instance_id: str,
    clause: RegulationClause,
    token_count: int,
    prebinding_error: str | None = None,
) -> AgentResponse:
    """Attach trusted inputs, abstaining when model fields cannot bind to them."""

    raw_provider_text = submitted.model_dump_json()
    thought = submitted.thought.strip() or (
        submitted.claim
        or submitted.abstention_reason
        or "Provider supplied no reasoning."
    )
    final_answer = submitted.final_answer.strip() or (
        f"Finding: {submitted.claim}"
        if submitted.kind == "finding"
        else f"Abstained: {submitted.abstention_reason}"
    )

    def binding_abstention(detail: str) -> AgentResponse:
        reason = f"prediction failed host-input binding; refusing emission: {detail}"
        return AgentResponse(
            kind="abstain",
            thought=thought,
            prediction=None,
            claim=None,
            exec_probe=None,
            static_claim=None,
            abstention_reason=reason,
            final_answer=f"Abstained: {reason}",
            token_count=token_count,
            raw_provider_text=raw_provider_text,
        )

    if submitted.kind == "finding" and prebinding_error is not None:
        return binding_abstention(prebinding_error)

    prediction = submitted.prediction
    if prediction is not None:
        try:
            prediction = prediction.attach_inputs(
                instance_id=instance_id,
                clause=clause,
            )
        except ValueError as exc:
            return binding_abstention(str(exc))
    return AgentResponse(
        kind=submitted.kind,
        thought=thought,
        prediction=prediction,
        claim=submitted.claim,
        exec_probe=submitted.exec_probe,
        static_claim=submitted.static_claim,
        abstention_reason=submitted.abstention_reason,
        final_answer=final_answer,
        token_count=token_count,
        raw_provider_text=raw_provider_text,
    )


def _tool_calls(
    logs: Sequence[ToolLogEntry],
    hunt_name: DriftType,
) -> list[ToolCall]:
    relevant = sorted(
        (entry for entry in logs if entry.hunt == hunt_name),
        key=lambda entry: entry.sequence,
    )
    return [
        ToolCall(
            step=index,
            tool=entry.tool,
            arguments=entry.arguments,
            observation_summary=entry.observation_summary,
            observation_truncated=entry.observation_truncated,
            error=entry.error,
            latency_ms=entry.latency_ms,
        )
        for index, entry in enumerate(relevant, start=1)
    ]


def _transcript(steps: Sequence[ToolCall]) -> list[dict[str, Any]]:
    return [
        {
            "step": step.step,
            "tool": step.tool,
            "arguments": step.arguments,
            "observation_summary": step.observation_summary,
            "observation_truncated": step.observation_truncated,
            "error": step.error,
        }
        for step in steps
    ]


def _abstained_hunt(
    *,
    hunt_name: DriftType,
    response: AgentResponse,
    question: str,
    steps: list[ToolCall],
    budget: BudgetSpec,
    reason: str,
    model_id: str,
    verification=None,
) -> HuntOutcome:
    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=None,
        abstained=True,
        abstention_reason=reason,
        budget=budget,
        budget_exhausted=False,
        tokens_used=response.token_count,
        contract_repairs=0,
        final_answer=f"Abstained: {reason}",
        model_id=model_id,
        seed=None,
    )
    return HuntOutcome(
        hunt=hunt_name,
        finding=None,
        confidence=None,
        verification=verification,
        verification_tier=(
            verification.tier if verification is not None else None
        ),
        trajectory=trajectory,
        abstained=True,
        abstention_reason=reason,
    )


def finalize_agent_hunt(
    *,
    hunt_name: DriftType,
    submitted: SubmittedResponse,
    clause: RegulationClause,
    program_scope: str,
    instance_id: str,
    logs: Sequence[ToolLogEntry],
    tools: ToolLayer,
    budget: BudgetSpec,
    entailer: Entailer,
    token_count: int,
    min_successful_observations: int,
    model_id: str,
) -> HuntOutcome:
    """Apply the frozen policy guard and verifier to one batched hunt answer."""

    hunt = get_hunt(hunt_name)
    question = build_hunt_prompt(hunt_name, clause, program_scope)
    steps = _tool_calls(logs, hunt_name)
    transcript = _transcript(steps)
    response = bind_submitted_response(
        submitted,
        instance_id=instance_id,
        clause=clause,
        token_count=token_count,
    )
    successful = sum(
        step.error is None and bool(step.observation_summary) for step in steps
    )
    if successful < min_successful_observations:
        reason = (
            "batched evidence minimum not met: "
            f"{successful} successful observation(s), "
            f"{min_successful_observations} required"
        )
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=reason,
            model_id=model_id,
        )

    if response.kind == "abstain":
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=response.abstention_reason or "model abstained",
            model_id=model_id,
        )

    guard_errors = hunt.validate_response(response, transcript, clause)
    if guard_errors:
        reason = "policy evidence guard: " + "; ".join(guard_errors)
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=reason,
            model_id=model_id,
        )

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
        verification = verify(finding, tools, entailer=entailer)
    except Exception as exc:  # noqa: BLE001
        reason = (
            "verification unavailable; refusing emission: "
            f"{type(exc).__name__}: {exc}"
        )
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=reason,
            model_id=model_id,
        )
    if not verification.verified:
        reason = verification.rejected_reason or "finding was not verified"
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=reason,
            model_id=model_id,
            verification=verification,
        )

    trajectory = Trajectory(
        question=question,
        steps=steps,
        model_responses=[response],
        verification=verification,
        finding=response.prediction,
        abstained=False,
        abstention_reason=None,
        budget=budget,
        budget_exhausted=False,
        tokens_used=response.token_count,
        contract_repairs=0,
        final_answer=response.final_answer or verification.evidence,
        model_id=model_id,
        seed=None,
    )
    result_errors = hunt.validate_trajectory(trajectory)
    if result_errors:
        reason = "policy result guard: " + "; ".join(result_errors)
        return _abstained_hunt(
            hunt_name=hunt_name,
            response=response,
            question=question,
            steps=steps,
            budget=budget,
            reason=reason,
            model_id=model_id,
            verification=verification,
        )
    return HuntOutcome(
        hunt=hunt_name,
        finding=trajectory.finding,
        confidence=confidence_for_tier(verification.tier),
        verification=verification,
        verification_tier=verification.tier,
        trajectory=trajectory,
        abstained=False,
        abstention_reason=None,
    )


def finalize_agent_case(
    submitted: SubmittedAgentCase,
    *,
    clause: RegulationClause,
    program_scope: str,
    instance_id: str,
    logs: Sequence[ToolLogEntry],
    tools: ToolLayer,
    budget: BudgetSpec,
    entailer: Entailer,
    token_counts: Sequence[int],
    min_successful_observations: int,
    model_id: str,
) -> HuntBatchOutcome:
    """Finalize seven guarded hunts and select the strongest verified finding."""

    if len(token_counts) != len(AGENT_HUNTS):
        raise ValueError("agent case requires one token allocation per hunt")
    by_hunt = {item.hunt: item.response for item in submitted.hunts}
    outcomes = [
        finalize_agent_hunt(
            hunt_name=hunt_name,
            submitted=by_hunt[hunt_name],
            clause=clause,
            program_scope=program_scope,
            instance_id=instance_id,
            logs=logs,
            tools=tools,
            budget=budget,
            entailer=entailer,
            token_count=token_count,
            min_successful_observations=min_successful_observations,
            model_id=model_id,
        )
        for hunt_name, token_count in zip(
            AGENT_HUNTS,
            token_counts,
            strict=True,
        )
    ]
    findings = [outcome for outcome in outcomes if not outcome.abstained]
    selected = (
        max(
            findings,
            key=lambda outcome: (
                outcome.confidence or 0.0,
                -int(outcome.verification_tier),
                outcome.hunt,
            ),
        )
        if findings
        else outcomes[0]
    )
    return HuntBatchOutcome(outcomes=outcomes, selected=selected)
