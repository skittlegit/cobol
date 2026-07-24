"""Live provider adapters behind the provider-neutral ``DecisionModel`` seam."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from cobol_archaeologist.model.prompt import (
    MODEL_ID,
    MODEL_SEED,
    MODEL_TEMPERATURE,
    AgentResponse,
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
OPENAI_MODEL_ID = "gpt-5.6-sol"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class ProviderUnavailable(RuntimeError):
    pass


def _agent_response(text: str, total_tokens: int) -> AgentResponse:
    match = _JSON_OBJECT.search(text)
    if match is None:
        raise ProviderUnavailable("provider response contained no JSON object")
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise ProviderUnavailable("provider response contained invalid JSON") from exc
    data["token_count"] = total_tokens
    return AgentResponse.model_validate(data)


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
        schema = AgentResponse.model_json_schema()
        user = {
            "question": question,
            "tool_transcript": transcript,
            "response_contract": schema,
            "instruction": (
                "Return exactly one JSON object satisfying response_contract. "
                "Choose one tool call, a finding, or an explicit abstention."
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

    def respond(
        self,
        *,
        system_prompt: str,
        question: str,
        transcript: list[dict[str, Any]],
    ) -> AgentResponse:
        user = {
            "question": question,
            "tool_transcript": transcript,
            "response_contract": AgentResponse.model_json_schema(),
            "instruction": (
                "Return exactly one JSON object satisfying response_contract. "
                "Choose one tool call, a finding, or an explicit abstention. "
                "Set token_count to 0; the adapter replaces it with provider usage."
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
            "temperature": self.temperature,
            "text": {"format": {"type": "json_object"}},
            "store": False,
        }
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
        text = "\n".join(
            part.get("text", "")
            for item in raw.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        usage = raw.get("usage", {})
        total_tokens = int(
            usage.get(
                "total_tokens",
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            )
        )
        return _agent_response(text, total_tokens)

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
