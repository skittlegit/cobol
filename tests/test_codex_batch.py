"""ChatGPT-Codex batch execution gates for the M4 rerun."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec
from cobol_archaeologist.eval import codex_batch as codex_batch_module
from cobol_archaeologist.eval.baselines import OracleSliceContext, RAGDenseContext
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
    validate_baseline_envelope,
)
from cobol_archaeologist.eval.codex_live import (
    CONFIG2_SMOKE_IDS,
    CONFIG2_SMOKE_SEED,
    REQUIRED_SMOKE_ROWS,
    _manifest,
    _mode_rows,
    batch_size_for,
    build_agent_prompt,
    build_baseline_prompt,
    codex_exec_arguments,
    select_baseline_clause,
)
from cobol_archaeologist.eval.codex_tool import (
    ToolLogEntry,
    ToolRequest,
    execute_tool_request,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.prompt import HUNT_PROMPTS
from cobol_archaeologist.model.verify import (
    LexicalEntailer,
    StaticClaim,
    VerificationTier,
)
from cobol_archaeologist.schemas import DriftInstance, RegulationClause

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"


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
    responses = {hunt: _abstention() for hunt in AGENT_HUNTS}
    envelope = CodexBatchEnvelope(
        results=[
            {
                "alias": "drift_900000",
                **responses,
            }
        ]
    )

    validate_agent_envelope(envelope, ["drift_900000"])
    assert [item.hunt for item in envelope.results[0].hunts] == list(AGENT_HUNTS)

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


def test_baseline_batch_returns_omitted_aliases_for_conservative_retry() -> None:
    envelope = CodexBaselineEnvelope(
        results=[
            {
                "alias": "drift_900000",
                "clause_index": None,
                "response": _abstention(),
            }
        ]
    )

    assert validate_baseline_envelope(
        envelope,
        ["drift_900000", "drift_900001"],
        system_id="oracle_slice",
    ) == ["drift_900001"]
    with pytest.raises(ValueError, match="unexpected"):
        validate_baseline_envelope(
            envelope,
            ["drift_900001"],
            system_id="oracle_slice",
        )


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


def test_submitted_abstention_discards_attached_finding_fields() -> None:
    submitted = SubmittedResponse(
        kind="abstain",
        thought="No.",
        prediction=None,
        claim="A speculative finding-shaped claim",
        exec_probe=None,
        static_claim=StaticClaim(literal="SHOULD-NOT-EMIT"),
        abstention_reason="No evidence.",
        final_answer="Abstained.",
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

    assert response.kind == "abstain"
    assert response.prediction is None
    assert response.claim is None
    assert response.static_claim is None
    assert "speculative finding-shaped claim" in (response.raw_provider_text or "")


def test_host_input_binding_failure_abstains_without_infrastructure_error() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))[
        "d1"
    ][-1]
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
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])

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

    selection_failure = bind_submitted_response(
        submitted,
        instance_id="drift_910001",
        clause=clause,
        token_count=100,
        prebinding_error="rag_dense finding requires clause_index",
    )
    assert selection_failure.kind == "abstain"
    assert "requires clause_index" in (selection_failure.abstention_reason or "")
    assert selection_failure.raw_provider_text == submitted.model_dump_json()


def test_host_binding_canonicalizes_leaf_value_target_path() -> None:
    """A provider's ``value`` wrapper names the leaf itself, not a child."""

    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))[
        "d1"
    ][-1]
    projected = _provider_projection(final)
    projected["prediction"]["target_path"] = "value"
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **projected,
        }
    )
    clause = RegulationClause(
        doc="RBI-Test",
        clause_id="1",
        version="2026-01-01",
        effective_date="2026-01-01",
        text="Complete the update within seven days.",
        current_value={
            "kind": "duration_days",
            "value": 7,
            "comparator": "at_most",
        },
    )

    response = bind_submitted_response(
        submitted,
        instance_id="drift_910001",
        clause=clause,
        token_count=100,
    )

    assert response.kind == "finding"
    assert response.prediction is not None
    assert response.prediction.target_path is None


def test_invalid_interprocedural_flag_abstains_only_submitted_hunt() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))[
        "d1"
    ][-1]
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
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])

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
            "static_claim": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])
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
            "static_claim": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])
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


def test_batched_d1_uses_class_minimum_and_emits_with_one_bound_code_fact() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    cached = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))
    final = json.loads(json.dumps(cached["d1"][-1]))
    paragraph_locus = next(
        locus
        for locus in final["prediction"]["code_locus"]["loci"]
        if locus["paragraph"] == "2000-CALC"
    )
    final["prediction"]["code_locus"] = {
        "loci": [paragraph_locus],
        "slice_vars": final["prediction"]["code_locus"]["slice_vars"],
        "is_interprocedural": False,
    }
    final["prediction"]["labels"]["line_level"] = [
        {"program": "CLOSPEN2", "line": 22, "file": None}
    ]
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])
    observation = StubToolLayer(fixture / "corpus").read_paragraph(
        "CLOSPEN2", "2000-CALC"
    )
    logs = [
        ToolLogEntry(
            alias="drift_900000",
            hunt="D1_stale_threshold",
            sequence=1,
            tool="read_paragraph",
            arguments={"program": "CLOSPEN2", "name": "2000-CALC"},
            observation_summary=observation.model_dump_json(),
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
        # Config 1 supplied a global 3; config 2 must ignore it in favour of D1=1.
        min_successful_observations=3,
        model_id="gpt-5.6-luna",
    )

    assert not outcome.abstained
    assert outcome.verification_tier == VerificationTier.STATIC


def test_malformed_static_claim_token_fails_before_batched_verifier(
    monkeypatch,
) -> None:
    records_path = (
        ROOT
        / "data"
        / "eval"
        / "m4-config2"
        / "smoke-pre-amendment-e6a7762"
        / "agent.jsonl"
    )
    records = [
        EvaluationRecord.model_validate_json(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record = next(row for row in records if row.instance_id == "drift_377860")
    trace = next(row for row in record.agent_hunts if row.hunt == "D5_boundary_error")
    response = next(
        row
        for row in reversed(trace.trajectory.model_responses)
        if row.kind == "finding"
    )
    projected = _provider_projection(response.model_dump(mode="json"))
    projected.pop("tool", None)
    projected.pop("arguments", None)
    submitted = SubmittedResponse.model_validate(projected)
    logs = [
        ToolLogEntry(
            alias="drift_900000",
            hunt="D5_boundary_error",
            sequence=step.step,
            tool=step.tool,
            arguments=step.arguments,
            observation_summary=step.observation_summary,
            observation_truncated=step.observation_truncated,
            error=step.error,
            latency_ms=step.latency_ms or 0,
        )
        for step in trace.trajectory.steps
    ]

    def forbidden_verify(*_args, **_kwargs):
        raise AssertionError("malformed static claim must not reach verify()")

    monkeypatch.setattr(codex_batch_module, "verify", forbidden_verify)
    outcome = finalize_agent_hunt(
        hunt_name="D5_boundary_error",
        submitted=submitted,
        clause=record.gold.regulation_clause,
        program_scope="KYCSYNC2",
        instance_id=record.instance_id,
        logs=logs,
        tools=object(),
        budget=BudgetSpec(max_tokens=65_536),
        entailer=LexicalEntailer(),
        token_count=100,
        min_successful_observations=1,
        model_id="gpt-5.6-luna",
    )

    assert outcome.abstained
    assert outcome.verification is None
    assert outcome.abstention_reason.startswith(
        "policy evidence guard: static-claim source-token validator:"
    )
    assert "comparator" in outcome.abstention_reason
    assert "verifier" not in outcome.abstention_reason


def test_batched_d2_keeps_four_observation_absence_floor() -> None:
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    cached = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))
    final = cached["d2"][-1]
    submitted = SubmittedResponse.model_validate(
        {
            "exec_probe": None,
            "static_claim": None,
            "abstention_reason": None,
            **_provider_projection(final),
        }
    )
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])
    logs = [
        ToolLogEntry(
            alias="drift_900000",
            hunt="D2_missing_rule",
            sequence=1,
            tool="grep",
            arguments={"pattern": "CKYCR-DEADLINE"},
            observation_summary='{"matches":[],"pattern":"CKYCR-DEADLINE"}',
            observation_truncated=False,
            error=None,
            latency_ms=1,
        )
    ]

    outcome = finalize_agent_hunt(
        hunt_name="D2_missing_rule",
        submitted=submitted,
        clause=clause,
        program_scope="KYCSYNC1",
        instance_id="drift_910002",
        logs=logs,
        tools=StubToolLayer(fixture / "corpus"),
        budget=BudgetSpec(max_tokens=10_000),
        entailer=LexicalEntailer(),
        token_count=100,
        min_successful_observations=1,
        model_id="gpt-5.6-luna",
    )

    assert outcome.abstained
    assert outcome.abstention_reason == (
        "batched evidence minimum not met: "
        "1 successful observation(s), 4 required for D2_missing_rule"
    )


def test_agent_prompt_is_gold_hidden_and_pins_per_hunt_real_tool_investigation() -> (
    None
):
    fixture = Path(__file__).parent / "fixtures" / "hunts"
    final = json.loads((fixture / "cached_decisions.json").read_text(encoding="utf-8"))[
        "d1"
    ][-1]
    clause = RegulationClause.model_validate(final["prediction"]["regulation_clause"])

    prompt = build_agent_prompt(
        [
            {
                "alias": "drift_900000",
                "program_scope": "CLOSPEN2",
                "clause": clause.model_dump(mode="json"),
            }
        ],
        tool_command="/support/.venv/bin/python -m cobol_archaeologist.eval.codex_tool",
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
    assert "are exact substrings copied from a cited tool" in prompt
    assert '{"literal":"7","comparator":">="}' in prompt
    assert "source `>=`; clause `at_most`" in prompt
    normalized_prompt = " ".join(prompt.split())
    assert "claim is the citation hypothesis" in normalized_prompt
    assert "without COBOL identifiers or implementation facts" in normalized_prompt
    assert "never an absolute task path" in normalized_prompt
    assert 'read_paragraph {"program":"...","name":"..."}' in prompt
    assert 'grep {"pattern":"..."}' in prompt
    assert "gpt-5.6-luna" not in prompt


def test_baseline_prompt_requires_visible_clause_selection_and_clean_claim() -> None:
    dense_prompt = " ".join(
        build_baseline_prompt(
            "rag_dense",
            [{"alias": "drift_900000", "context": {"retrieved_clauses": []}}],
        ).split()
    )
    oracle_prompt = " ".join(
        build_baseline_prompt(
            "oracle_slice",
            [{"alias": "drift_900000", "context": {"clause": {}}}],
        ).split()
    )

    assert "zero-based index" in dense_prompt
    assert "context.retrieved_clauses" in dense_prompt
    assert "Set clause_index to null" in oracle_prompt
    assert "claim is the citation hypothesis" in dense_prompt
    assert "without COBOL identifiers or implementation facts" in dense_prompt
    assert "never a default verdict" in dense_prompt


def test_baseline_clause_selection_is_limited_to_visible_context() -> None:
    clause = RegulationClause(
        doc="RBI-Test",
        clause_id="1",
        version="2026-01-01",
        effective_date="2026-01-01",
        text="The issuer must act within seven days.",
        current_value=None,
    )
    dense = RAGDenseContext.model_validate(
        {
            "clause_query": "seven days",
            "retrieved_clauses": [
                {"clause": clause.model_dump(mode="json"), "score": 1.0}
            ],
            "program": "PROGRAM SOURCE",
        }
    )
    oracle = OracleSliceContext(
        clause=clause,
        program="PROGRAM SOURCE",
        slices=[],
    )

    assert select_baseline_clause("rag_dense", 0, dense) == clause
    assert select_baseline_clause("oracle_slice", None, oracle) == clause
    with pytest.raises(ValueError, match="requires clause_index"):
        select_baseline_clause("rag_dense", None, dense)
    with pytest.raises(ValueError, match="outside 1 visible retrievals"):
        select_baseline_clause("rag_dense", 1, dense)
    with pytest.raises(ValueError, match="must be non-negative"):
        select_baseline_clause("rag_dense", -1, dense)
    with pytest.raises(ValueError, match="must be null"):
        select_baseline_clause("oracle_slice", 0, oracle)


def test_oracle_batch_is_bounded_for_large_slice_payloads() -> None:
    assert batch_size_for("agent") == 2
    assert batch_size_for("plain_llm") == 5
    assert batch_size_for("rag_dense") == 5
    assert batch_size_for("rag_reranker") == 5
    assert batch_size_for("oracle_slice") == 2


def test_config2_smoke_is_seeded_stratified_reproducible_and_pinned() -> None:
    rows = [
        DriftInstance.model_validate_json(line)
        for line in SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    selected = _mode_rows(rows, "smoke", smoke_seed=CONFIG2_SMOKE_SEED)
    replay = _mode_rows(rows, "smoke", smoke_seed=CONFIG2_SMOKE_SEED)

    assert REQUIRED_SMOKE_ROWS == 7
    assert [row.instance_id for row in selected] == list(CONFIG2_SMOKE_IDS)
    assert [row.instance_id for row in replay] == list(CONFIG2_SMOKE_IDS)
    assert len({row.drift_type for row in selected}) == 7
    assert [row.instance_id for row in selected] != [
        row.instance_id for row in rows[:REQUIRED_SMOKE_ROWS]
    ]
    with pytest.raises(ValueError, match="pinned config-2 smoke seed"):
        _mode_rows(rows, "smoke", smoke_seed=CONFIG2_SMOKE_SEED + 1)


def test_config2_manifest_records_seed_and_selected_ids() -> None:
    rows = [
        DriftInstance.model_validate_json(line)
        for line in SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected = _mode_rows(rows, "smoke", smoke_seed=CONFIG2_SMOKE_SEED)

    manifest = _manifest(
        system_id="agent",
        mode="smoke",
        rows=selected,
        commit="a" * 40,
        cli_version="codex-cli test",
        smoke_seed=CONFIG2_SMOKE_SEED,
        smoke_instance_ids=CONFIG2_SMOKE_IDS,
    )

    assert manifest.smoke_seed == CONFIG2_SMOKE_SEED
    assert manifest.smoke_instance_ids == list(CONFIG2_SMOKE_IDS)
    assert manifest.smoke_rows == REQUIRED_SMOKE_ROWS
    assert manifest.total == REQUIRED_SMOKE_ROWS


def test_codex_cli_arguments_pin_luna_low_and_chatgpt_safe_modes() -> None:
    args = codex_exec_arguments(
        codex_binary="/home/user/.local/bin/codex",
        task_root="/home/user/tasks/task-1",
        model_id="gpt-5.6-luna",
        reasoning_effort="low",
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
    assert 'model_reasoning_effort="low"' in args


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
