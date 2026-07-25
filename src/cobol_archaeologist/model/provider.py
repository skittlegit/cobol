"""Live provider adapters behind the provider-neutral ``DecisionModel`` seam."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from cobol_archaeologist.model.prompt import (
    MODEL_ID,
    MODEL_SEED,
    MODEL_TEMPERATURE,
    AgentResponse,
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
OPENAI_MODEL_ID = "gpt-5.6-sol"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_RESPONSE_TOOL = "submit_agent_response"


class ProviderUnavailable(RuntimeError):
    pass


def _contract_abstention(
    detail: str,
    total_tokens: int,
    raw_provider_text: str,
) -> AgentResponse:
    """Fail closed on model output that cannot satisfy the response contract."""

    return AgentResponse(
        kind="abstain",
        thought="The provider output failed the frozen response contract.",
        abstention_reason=detail,
        final_answer=f"Abstained: {detail}",
        token_count=total_tokens,
        raw_provider_text=raw_provider_text,
        contract_error=detail,
    )


def _normalize_target_path(prediction: dict[str, Any]) -> None:
    """Canonicalize model notation to the frozen relative-child path schema."""

    target_path = prediction.get("target_path")
    if not isinstance(target_path, str):
        return
    current_value = (
        prediction.get("regulation_clause", {}).get("current_value")
        if isinstance(prediction.get("regulation_clause"), dict)
        else None
    )
    if not isinstance(current_value, dict):
        return
    if current_value.get("kind") != "composite":
        # Leaf CurrentValue nodes have no targetable child path.
        prediction["target_path"] = None
        return
    if target_path.startswith("current_value."):
        target_path = target_path.removeprefix("current_value.")
    if target_path.startswith("value."):
        target_path = target_path.removeprefix("value.")
    prediction["target_path"] = target_path


def _normalize_response_shape(data: dict[str, Any]) -> None:
    """Canonicalize provider-only nulls and unambiguous sibling placement.

    The raw provider text remains attached to the returned response. This
    normalization never invents evidence: it only maps a non-applicable null
    arguments value to the contract's empty mapping, or reparents an existing
    response field that Luna placed one object too deep. Conflicting duplicate
    fields are deliberately left in place so Pydantic rejects them.
    """

    if data.get("arguments") is None:
        data["arguments"] = {}
    prediction = data.get("prediction")
    if not isinstance(prediction, dict):
        return
    # Drop punctuation-only keys produced by malformed JSON-key continuation.
    # Any meaningful unknown field remains for Pydantic to reject.
    for key in list(prediction):
        if isinstance(key, str) and not any(
            character.isalnum() or character == "_" for character in key
        ):
            prediction.pop(key)
    for field in (
        "claim",
        "exec_probe",
        "static_claim",
        "final_answer",
        "token_count",
    ):
        if field not in prediction:
            continue
        nested_value = prediction[field]
        if field == "token_count":
            # Provider token usage always owns this telemetry field.
            prediction.pop(field)
        elif field not in data or data[field] is None:
            data[field] = prediction.pop(field)
        elif data[field] == nested_value:
            prediction.pop(field)

    code_locus = prediction.get("code_locus")
    if not isinstance(code_locus, dict):
        return
    if "is_interprocedural" in prediction:
        misplaced = prediction["is_interprocedural"]
        if (
            "is_interprocedural" not in code_locus
            or code_locus["is_interprocedural"] is None
        ):
            code_locus["is_interprocedural"] = prediction.pop(
                "is_interprocedural"
            )
        elif code_locus["is_interprocedural"] == misplaced:
            prediction.pop("is_interprocedural")

    loci = code_locus.get("loci")
    labels = prediction.get("labels")
    line_level = labels.get("line_level") if isinstance(labels, dict) else None
    if not isinstance(loci, list) or not isinstance(line_level, list):
        return
    for ref in line_level:
        if not isinstance(ref, dict):
            continue
        if "line" not in ref and isinstance(ref.get("file"), int):
            ref["line"] = ref["file"]
            ref["file"] = None
        line = ref.get("line")
        if not isinstance(line, int):
            continue
        candidates = []
        for locus in loci:
            if not isinstance(locus, dict) or locus.get("file") != ref.get("file"):
                continue
            span = locus.get("line_span")
            if (
                isinstance(span, list)
                and len(span) == 2
                and all(isinstance(bound, int) for bound in span)
                and span[0] <= line <= span[1]
            ):
                candidates.append(locus)
        if any(locus.get("program") == ref.get("program") for locus in candidates):
            continue
        if len(candidates) == 1 and isinstance(candidates[0].get("program"), str):
            ref["program"] = candidates[0]["program"]


def _agent_response(
    text: str,
    total_tokens: int,
    *,
    prediction_instance_id: str | None = None,
) -> AgentResponse:
    match = _JSON_OBJECT.search(text)
    if match is None:
        return _contract_abstention(
            "response contract rejected provider output: no JSON object",
            total_tokens,
            text,
        )
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return _contract_abstention(
            "response contract rejected provider output: invalid JSON",
            total_tokens,
            text,
        )
    # These fields are adapter-owned telemetry, not model-authored content.
    data.pop("raw_provider_text", None)
    data.pop("contract_error", None)
    _normalize_response_shape(data)
    # A model is not the authority for evaluation-record identity.  Live M4
    # calls use a constant, label-free placeholder here; the orchestrator maps
    # it to the current record only after the provider call returns.
    prediction = data.get("prediction")
    if isinstance(prediction, dict):
        if prediction_instance_id is not None:
            prediction["instance_id"] = prediction_instance_id
        _normalize_target_path(prediction)
    # ``final_answer`` is replay-facing duplication of the finding claim, not
    # evidence. JSON Schema cannot express AgentResponse's kind-dependent
    # validator, so derive the summary when a provider omits it.
    if (
        data.get("kind") == "finding"
        and not data.get("final_answer")
        and isinstance(data.get("claim"), str)
    ):
        data["final_answer"] = data["claim"]
    data["token_count"] = total_tokens
    try:
        response = AgentResponse.model_validate(data)
        return response.model_copy(update={"raw_provider_text": text})
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'response'}: "
            f"{error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)
        )
        reason = f"response contract rejected proposed output: {details}"
        # A syntactically valid provider response that proposes a malformed
        # finding is model behavior, not an API outage. Fail closed as an
        # explicit abstention so no invalid prediction reaches verification.
        return _contract_abstention(reason, total_tokens, text)


def _agent_response_schema(
    prediction_instance_id: str | None = None,
) -> dict[str, Any]:
    schema = AgentResponse.model_json_schema()
    properties = schema.get("properties", {})
    properties.pop("raw_provider_text", None)
    properties.pop("contract_error", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [
            name
            for name in required
            if name not in {"raw_provider_text", "contract_error"}
        ]
    schema["description"] = (
        "One agent turn. kind='finding' requires both a complete prediction "
        "and a non-empty claim; the runtime rejects either field missing."
    )
    properties["kind"]["description"] = (
        "Choose tool, finding, or abstain. A finding requires prediction and claim."
    )
    properties["prediction"]["description"] = (
        "Required and complete when kind='finding'; otherwise null."
    )
    properties["claim"]["description"] = (
        "Required and non-empty when kind='finding'; otherwise null."
    )
    if prediction_instance_id is not None:
        instance_schema = schema["$defs"]["DriftPrediction"]["properties"][
            "instance_id"
        ]
        instance_schema["enum"] = [prediction_instance_id]
    return schema


class AnthropicDecisionModel:
    """Minimal SDK-free adapter; credentials stay in the environment."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ProviderUnavailable("ANTHROPIC_API_KEY is not set")
        self.model_id = model_id or os.environ.get("COBOL_AGENT_MODEL", MODEL_ID)
        self.temperature = MODEL_TEMPERATURE
        self.seed = MODEL_SEED
        self.timeout_s = timeout_s

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        schema = _agent_response_schema()
        user = {
            "question": question,
            "tool_transcript": transcript,
            "response_contract": schema,
            "instruction": (
                "Return exactly one JSON object satisfying response_contract. "
                "Choose one tool call, a finding, or an explicit abstention. "
                "Stop after that object; never append a second object or an "
                "alternative. A finding requires both a complete prediction "
                "and a claim."
            ),
        }
        payload = {
            "model": self.model_id,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(user)}],
        }
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable(f"Anthropic request failed: {exc}") from exc
        text = "\n".join(
            block.get("text", "")
            for block in raw.get("content", [])
            if block.get("type") == "text"
        )
        usage = raw.get("usage", {})
        total_tokens = int(
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
        return _agent_response(text, total_tokens)


class OpenAIDecisionModel:
    """SDK-free Responses API adapter; credentials remain environment-only."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        timeout_s: float = 120.0,
        reasoning_effort: str = "none",
        max_retries: int = 4,
        prediction_instance_id: str = "drift_000000",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is not set")
        self.model_id = model_id or os.environ.get(
            "COBOL_AGENT_MODEL",
            OPENAI_MODEL_ID,
        )
        self.temperature = MODEL_TEMPERATURE
        self.seed = None
        self.timeout_s = timeout_s
        self.reasoning_effort = reasoning_effort
        self.max_retries = max_retries
        if re.fullmatch(r"drift_\d{6}", prediction_instance_id) is None:
            raise ValueError("prediction_instance_id must match drift_NNNNNN")
        self.prediction_instance_id = prediction_instance_id

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        schema = _agent_response_schema(self.prediction_instance_id)
        user = {
            "question": question,
            "tool_transcript": transcript,
            "instruction": (
                "Call submit_agent_response exactly once and stop. Choose one "
                "ToolLayer request, a finding, or an explicit abstention. For a "
                "finding, include a complete prediction with "
                "instance_id, regulation_clause, code_locus (loci, slice_vars, "
                "is_interprocedural), drift_type, target_path, labels, and "
                "rationale, plus a separate claim. The claim, exec_probe, "
                "static_claim, final_answer, and token_count are response "
                "fields alongside prediction, never fields inside prediction. "
                "Use arguments={} whenever no ToolLayer tool is requested. The "
                "claim must restate an obligation entailed by the "
                "supplied clause; put code facts in exec_probe/static_claim. "
                "D7_conformant requires conformant program/paragraph labels and "
                "an empty line_level. D1-D6 require drift labels. target_path must "
                "be null unless it names an exact current_value child path. Set "
                "code_locus.is_interprocedural true exactly when loci span more "
                "than one program. Always set prediction.instance_id to the "
                "schema's single allowed placeholder; record identity is assigned "
                "outside the model. target_path is relative to a composite "
                "current_value's value mapping (for example day_basis), and must "
                "be null for a leaf current_value. For a finding, final_answer "
                "must concisely summarize claim. Set token_count to 0; the adapter "
                "replaces it with provider usage."
            ),
        }
        # DECISION (OpenAI live seam): Responses is stateless and non-persisted
        # here. The repository already owns replay in Trajectory; provider-side
        # storage would add state that is absent from the frozen run key.
        payload = {
            "model": self.model_id,
            "instructions": system_prompt,
            "input": json.dumps(user, ensure_ascii=False),
            "max_output_tokens": 4096,
            "reasoning": {"effort": self.reasoning_effort},
            "tools": [
                {
                    "type": "function",
                    "name": OPENAI_RESPONSE_TOOL,
                    "description": (
                        "Submit exactly one complete agent turn. This is an "
                        "output envelope; it does not execute a ToolLayer tool."
                    ),
                    "parameters": schema,
                    "strict": False,
                }
            ],
            "tool_choice": {
                "type": "function",
                "name": OPENAI_RESPONSE_TOOL,
            },
            "parallel_tool_calls": False,
            "store": False,
        }
        # OpenAI reasoning models reject ``temperature`` whenever reasoning
        # effort is enabled. Keep the legacy deterministic parameter only for
        # the explicitly non-reasoning path; manifests record its omission for
        # Luna/low.
        if self.reasoning_effort == "none":
            payload["temperature"] = self.temperature
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(payload).encode(),
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            method="POST",
        )
        raw = self._request(request)
        if raw.get("status") != "completed":
            detail = raw.get("error") or raw.get("incomplete_details") or raw.get(
                "status"
            )
            raise ProviderUnavailable(f"OpenAI response did not complete: {detail}")
        usage = raw.get("usage", {})
        total_tokens = int(
            usage.get(
                "total_tokens",
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            )
        )
        function_calls = [
            item
            for item in raw.get("output", [])
            if item.get("type") == "function_call"
        ]
        matching_calls = [
            item
            for item in function_calls
            if item.get("name") == OPENAI_RESPONSE_TOOL
        ]
        if len(function_calls) != 1 or len(matching_calls) != 1:
            output_text = json.dumps(raw.get("output", []), ensure_ascii=False)
            return _contract_abstention(
                "response contract rejected provider output: expected exactly "
                f"one {OPENAI_RESPONSE_TOOL} call",
                total_tokens,
                output_text,
            )
        text = str(matching_calls[0].get("arguments", ""))
        return _agent_response(
            text,
            total_tokens,
            prediction_instance_id=self.prediction_instance_id,
        )

    def _request(self, request: urllib.request.Request) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_s,
                ) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:1000]
                retryable = exc.code in {408, 409, 429, 500, 502, 503, 504}
                if not retryable or attempt >= self.max_retries:
                    raise ProviderUnavailable(
                        f"OpenAI HTTP {exc.code}: {detail or exc.reason}"
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise ProviderUnavailable(
                        f"OpenAI request failed: {exc}"
                    ) from exc
                delay = 2**attempt
            except json.JSONDecodeError as exc:
                raise ProviderUnavailable("OpenAI response was not JSON") from exc
            time.sleep(min(delay, 30.0))
        raise AssertionError("unreachable retry loop")
