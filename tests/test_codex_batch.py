"""ChatGPT-Codex batch execution gates for the M4 rerun."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec
from cobol_archaeologist.eval.codex_batch import (
    AGENT_HUNTS,
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    CodexUsage,
    SubmittedResponse,
    allocate_tokens,
    bind_submitted_response,
    finalize_agent_hunt,
    parse_codex_events,
    sanitized_codex_environment,
    strict_codex_schema,
    validate_agent_envelope,
)
from cobol_archaeologist.eval.codex_live import (
    build_agent_prompt,
    codex_exec_arguments,
)
from cobol_archaeologist.eval.codex_tool import (
    ToolLogEntry,
    ToolRequest,
    execute_tool_request,
)
from cobol_archaeologist.model.prompt import HUNT_PROMPTS
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import RegulationClause


def _abstention(reason: str = "insufficient evidence") -> SubmittedResponse:
    return SubmittedResponse(
        kind="abstain",
        thought="The available evidence does not support a finding.",
        prediction=None,
        claim=None,
        exec_probe=None,
        static_claim=None,
        abstention_reason=reason,
        final_answer=f"Abstained: {reason}",
    )


def _provider_projection(response: dict) -> dict:
    projected = {
        key: value
        for key, value in response.items()
        if key not in {"token_count", "raw_provider_text", "contract_error"}
    }
    prediction = projected.get("prediction")
    if prediction is not None:
        projected["prediction"] = {
            key: value
            for key, value in prediction.items()
            if key not in {"instance_id", "regulation_clause"}
        }
    return projected


def test_codex_environment_never_forwards_api_keys() -> None:
    env = sanitized_codex_environment(
        {
            "PATH": "safe",
            "OPENAI_API_KEY": "must-not-leak",
            "CODEX_API_KEY": "must-not-leak",
            "AZURE_OPENAI_API_KEY": "must-not-leak",
        }
    )

    assert env["PATH"] == "safe"
    assert "OPENAI_API_KEY" not in env
    assert "CODEX_API_KEY" not in env
    assert "AZURE_OPENAI_API_KEY" not in env


def test_agent_batch_requires_exact_alias_and_hunt_parity() -> None:
    responses = {
        hunt: _abstention()
        for hunt in AGENT_HUNTS
    }
    envelope = CodexBatchEnvelope(
        results=[
            {
                "alias": "drift_900000",
                **responses,
            }
        ]
    )

    validate_agent_envelope(envelope, ["drift_900000"])
    assert [item.hunt for item in envelope.results[0].hunts] == list(
        AGENT_HUNTS
    )

    with pytest.raises(ValidationError):
        CodexBatchEnvelope(
            results=[
                {
                    "alias": "drift_900000",
                    **{
                        hunt: response
                        for hunt, response in responses.items()
                        if hunt != "D7_conformant"
                    },
                }
            ]
        )

    with pytest.raises(ValueError, match="aliases do not match"):
        validate_agent_envelope(envelope, ["drift_900001"])


def test_token_allocation_is_exact_and_deterministic() -> None:
    assert allocate_tokens(10, 3) == [4, 3, 3]
    assert allocate_tokens(0, 2) == [0, 0]
    assert sum(allocate_tokens(101, 7)) == 101
    with pytest.raises(ValueError, match="positive"):
        allocate_tokens(10, 0)


def test_codex_jsonl_parser_preserves_raw_events_and_usage() -> None:
    final = json.dumps(
        {
            "results": [
                {
                    "alias": "drift_900000",
                    "hunts": [
                        {
                            "hunt": hunt,
                            "response": _abstention().model_dump(mode="json"),
                        }
                        for hunt in AGENT_HUNTS
                    ],
                }
            ]
        }
    )
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": final},
            }
        ),
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 75,
                    "output_tokens": 20,
                },
            }
        ),
    ]

    parsed = parse_codex_events("\n".join(lines))

    assert parsed.final_message == final
    assert parsed.thread_id == "thread-1"
    assert parsed.usage == CodexUsage(
        input_tokens=100,
        cached_input_tokens=75,
        output_tokens=20,
    )
    assert len(parsed.events) == 3


def test_submitted_response_cannot_mix_abstention_and_finding() -> None:
    with pytest.raises(ValueError):
        SubmittedResponse(
            kind="abstain",
            thought="No.",
            prediction=None,
            claim="A finding-shaped claim",
            exec_probe=None,
            static_claim=None,
            abstention_reason="No evidence.",
            final_answer="Abstained.",
        )


def test_host_input_binding_failure_abstains_without_infrastructure_error() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads(
        (fixture / "cached_decisions.json").read_text(encoding="utf-8")
    )["d1"][-1]
    projected = _provider_projection(final)
    projected["prediction"]["drift_type"] = "D5_boundary_error"
    projected["prediction"]["target_path"] = None
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **projected,
        }
    )
    clause = RegulationClause.model_validate(
        final["prediction"]["regulation_clause"]
    )

    response = bind_submitted_response(
        submitted,
        instance_id="drift_910001",
        clause=clause,
        token_count=100,
    )

    assert response.kind == "abstain"
    assert response.prediction is None
    assert response.contract_error is None
    assert "host-input binding" in response.abstention_reason
    assert response.raw_provider_text == submitted.model_dump_json()


def test_invalid_interprocedural_flag_abstains_only_submitted_hunt() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads(
        (fixture / "cached_decisions.json").read_text(encoding="utf-8")
    )["d1"][-1]
    projected = _provider_projection(final)
    projected["prediction"]["code_locus"] = {
        "loci": [
            {
                "program": "PROGRAM-A",
                "paragraph": "1000-MAIN",
                "file": "PROGRAM-A.cbl",
                "line_span": [10, 12],
            },
            {
                "program": "PROGRAM-B",
                "paragraph": "2000-CHECK",
                "file": "PROGRAM-B.cbl",
                "line_span": [20, 22],
            },
        ],
        "slice_vars": ["WS-VALUE"],
        "is_interprocedural": False,
    }
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **projected,
        }
    )
    clause = RegulationClause.model_validate(
        final["prediction"]["regulation_clause"]
    )

    response = bind_submitted_response(
        submitted,
        instance_id="drift_910002",
        clause=clause,
        token_count=100,
    )

    assert response.kind == "abstain"
    assert response.prediction is None
    assert "loci spanning >1 program" in (response.abstention_reason or "")
    assert '"is_interprocedural":false' in (response.raw_provider_text or "")
    assert response.contract_error is None


def test_empty_provider_narrative_uses_only_its_own_semantic_fields() -> None:
    submitted = _abstention("No verified evidence.").model_copy(
        update={"thought": "", "final_answer": ""}
    )
    clause = RegulationClause(
        doc="RBI-Test",
        clause_id="1",
        version="2026-01-01",
        effective_date="2026-01-01",
        text="A test clause.",
        current_value=None,
    )

    response = bind_submitted_response(
        submitted,
        instance_id="drift_910001",
        clause=clause,
        token_count=10,
    )

    assert response.thought == "No verified evidence."
    assert response.final_answer == "Abstained: No verified evidence."
    assert '"thought":""' in response.raw_provider_text
    assert '"final_answer":""' in response.raw_provider_text


def test_codex_tool_uses_only_descriptor_alias_and_logs_bounded_result(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "cases" / "drift_900000"
    case_dir.mkdir(parents=True)
    (tmp_path / "descriptor.json").write_text(
        json.dumps(
            {
                "aliases": {
                    "drift_900000": {
                        "source_dir": "cases/drift_900000",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class Observation(BaseModel):
        value: str

    class FakeTools:
        def grep(self, pattern: str) -> Observation:
            return Observation(value=pattern)

    request = ToolRequest(
        alias="drift_900000",
        hunt="D1_stale_threshold",
        tool="grep",
        arguments={"pattern": "SEVEN"},
    )
    result = execute_tool_request(
        request,
        task_root=tmp_path,
        tool_factory=lambda source: FakeTools(),
    )

    assert result.error is None
    assert json.loads(result.observation_summary) == {"value": "SEVEN"}
    logged = json.loads((tmp_path / "tool_log.jsonl").read_text(encoding="utf-8"))
    assert logged["alias"] == "drift_900000"
    assert logged["tool"] == "grep"

    with pytest.raises(KeyError, match="unknown case alias"):
        execute_tool_request(
            request.model_copy(update={"alias": "drift_900001"}),
            task_root=tmp_path,
            tool_factory=lambda source: FakeTools(),
        )


def test_codex_tool_descriptor_cannot_escape_task_root(tmp_path: Path) -> None:
    (tmp_path / "descriptor.json").write_text(
        json.dumps(
            {
                "aliases": {
                    "drift_900000": {
                        "source_dir": "../outside",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    request = ToolRequest(
        alias="drift_900000",
        hunt=AGENT_HUNTS[0],
        tool="grep",
        arguments={"pattern": "X"},
    )

    with pytest.raises(ValueError, match="escapes task root"):
        execute_tool_request(request, task_root=tmp_path)


def test_codex_tool_gives_each_hunt_an_independent_eight_call_cap(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "cases" / "drift_900000"
    case_dir.mkdir(parents=True)
    (tmp_path / "descriptor.json").write_text(
        json.dumps(
            {
                "aliases": {
                    "drift_900000": {
                        "source_dir": "cases/drift_900000",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class Observation(BaseModel):
        value: str

    class FakeTools:
        def grep(self, pattern: str) -> Observation:
            return Observation(value=pattern)

    request = ToolRequest(
        alias="drift_900000",
        hunt="D1_stale_threshold",
        tool="grep",
        arguments={"pattern": "SEVEN"},
    )
    for _ in range(8):
        execute_tool_request(
            request,
            task_root=tmp_path,
            tool_factory=lambda source: FakeTools(),
        )

    other_hunt = execute_tool_request(
        request.model_copy(update={"hunt": "D2_missing_rule"}),
        task_root=tmp_path,
        tool_factory=lambda source: FakeTools(),
    )
    assert other_hunt.sequence == 9

    with pytest.raises(
        RuntimeError,
        match="drift_900000/D1_stale_threshold",
    ):
        execute_tool_request(
            request,
            task_root=tmp_path,
            tool_factory=lambda source: FakeTools(),
        )
    assert len((tmp_path / "tool_log.jsonl").read_text().splitlines()) == 9


def test_batched_finding_cannot_emit_around_policy_guard_or_verifier() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    cached = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))
    final = cached["d1"][-1]
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(
        final["prediction"]["regulation_clause"]
    )
    # The proposed finding has one successful but class-insufficient tool call.
    # The outer policy guard must withhold it before verification/emission.
    logs = [
        ToolLogEntry(
            alias="drift_900000",
            hunt="D1_stale_threshold",
            sequence=1,
            tool="read_program",
            arguments={"program": "CLOSPEN2"},
            observation_summary='{"program":"CLOSPEN2","path":"x","paragraphs":[]}',
            observation_truncated=False,
            error=None,
            latency_ms=1,
        )
    ]
    outcome = finalize_agent_hunt(
        hunt_name="D1_stale_threshold",
        submitted=submitted,
        clause=clause,
        program_scope="CLOSPEN2",
        instance_id="drift_910001",
        logs=logs,
        tools=StubToolLayer(fixture / "corpus"),
        budget=BudgetSpec(max_tokens=10_000),
        entailer=LexicalEntailer(),
        token_count=100,
        min_successful_observations=1,
        model_id="gpt-5.6-luna",
    )

    assert outcome.abstained
    assert outcome.finding is None
    assert outcome.trajectory.finding is None
    assert "policy evidence guard" in outcome.abstention_reason


def test_batched_verified_finding_retains_whole_verification_result() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    cached = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))
    rows = cached["d1"]
    final = rows[-1]
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(
        final["prediction"]["regulation_clause"]
    )
    observations = [
        StubToolLayer(fixture / "corpus").resolve_copybook("WSDAYBAS"),
        StubToolLayer(fixture / "corpus").read_paragraph("CLOSPEN2", "2000-CALC"),
    ]
    logs = [
        ToolLogEntry(
            alias="drift_900000",
            hunt="D1_stale_threshold",
            sequence=index,
            tool=row["tool"],
            arguments=row["arguments"],
            observation_summary=observation.model_dump_json(),
            observation_truncated=False,
            error=None,
            latency_ms=1,
        )
        for index, (row, observation) in enumerate(
            zip(rows[:2], observations, strict=True),
            start=1,
        )
    ]
    logs.append(
        ToolLogEntry(
            alias="drift_900000",
            hunt="D2_missing_rule",
            sequence=3,
            tool="grep",
            arguments={"pattern": "UNRELATED"},
            observation_summary='{"matches":[],"pattern":"UNRELATED"}',
            observation_truncated=False,
            error=None,
            latency_ms=1,
        )
    )
    outcome = finalize_agent_hunt(
        hunt_name="D1_stale_threshold",
        submitted=submitted,
        clause=clause,
        program_scope="CLOSPEN2",
        instance_id="drift_910001",
        logs=logs,
        tools=StubToolLayer(fixture / "corpus"),
        budget=BudgetSpec(max_tokens=10_000),
        entailer=LexicalEntailer(),
        token_count=100,
        min_successful_observations=1,
        model_id="gpt-5.6-luna",
    )

    assert not outcome.abstained
    assert outcome.verification is not None
    assert outcome.trajectory.verification == outcome.verification
    assert len(outcome.verification.tier_attempts) >= 2
    assert [step.tool for step in outcome.trajectory.steps] == [
        "resolve_copybook",
        "read_paragraph",
    ]


def test_agent_prompt_is_gold_hidden_and_pins_per_hunt_real_tool_investigation() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads(
        (fixture / "cached_decisions.json").read_text(encoding="utf-8")
    )["d1"][-1]
    clause = RegulationClause.model_validate(
        final["prediction"]["regulation_clause"]
    )

    prompt = build_agent_prompt(
        [
            {
                "alias": "drift_900000",
                "program_scope": "CLOSPEN2",
                "clause": clause.model_dump(mode="json"),
            }
        ],
        tool_command="/support/.venv/bin/python -m "
        "cobol_archaeologist.eval.codex_tool",
    )

    assert "provenance" not in prompt
    assert "gold_rationale" not in prompt
    assert "mutation" not in prompt
    assert "at least 3 successful" in prompt
    assert "D7 is not a default verdict" in prompt
    assert all(instruction in prompt for instruction in HUNT_PROMPTS.values())
    assert "caller, callee, and slice observations" in prompt
    assert "including scalar, list, or enum-valued leaves" in prompt
    assert "emit only when all four negative observations are present" in prompt
    assert "Each D1-D7 HUNT has an independent transcript" in prompt
    assert "there is no shared hunt" in prompt
    assert "program names the containing executable program" in prompt
    normalized_prompt = " ".join(prompt.split())
    assert "claim is the citation hypothesis" in normalized_prompt
    assert "without COBOL identifiers or implementation facts" in normalized_prompt
    assert "never an absolute task path" in normalized_prompt
    assert 'read_paragraph {"program":"...","name":"..."}' in prompt
    assert 'grep {"pattern":"..."}' in prompt
    assert "gpt-5.6-luna" not in prompt


def test_codex_cli_arguments_pin_luna_high_and_chatgpt_safe_modes() -> None:
    args = codex_exec_arguments(
        codex_binary="/home/user/.local/bin/codex",
        task_root="/home/user/tasks/task-1",
        model_id="gpt-5.6-luna",
        reasoning_effort="high",
    )

    assert args[:5] == [
        "env",
        "-u",
        "OPENAI_API_KEY",
        "-u",
        "CODEX_API_KEY",
    ]
    assert "--ephemeral" in args
    assert "--ignore-user-config" in args
    assert "--sandbox" in args
    assert "workspace-write" in args
    assert args[args.index("-m") + 1] == "gpt-5.6-luna"
    assert 'model_reasoning_effort="high"' in args


def test_codex_schema_requires_every_nullable_key_without_defaults() -> None:
    schema = strict_codex_schema(CodexBaselineEnvelope)

    def walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
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
                "prefixItems",
                "uniqueItems",
            ):
                assert keyword not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
