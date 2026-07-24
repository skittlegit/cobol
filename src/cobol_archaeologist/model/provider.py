"""Live Anthropic DecisionModel adapter for T4 runs."""

from __future__ import annotations

import json
import os
import re
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


class ProviderUnavailable(RuntimeError):
    pass


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
        match = _JSON_OBJECT.search(text)
        if match is None:
            raise ProviderUnavailable("Anthropic response contained no JSON object")
        data = json.loads(match.group())
        usage = raw.get("usage", {})
        data["token_count"] = int(
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        )
        return AgentResponse.model_validate(data)
