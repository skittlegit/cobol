"""T4.1 materialization, gold hiding, provider, and three-track seam gates."""

from __future__ import annotations

import ast
import json
import random
from pathlib import Path

import pytest

from cobol_archaeologist.agent.loop import InvestigationLoop
from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.agent.trajectory import BudgetSpec, Trajectory
from cobol_archaeologist.benchmark.mutate import (
    ProgramSource,
    load_clause_records,
    mutate,
)
from cobol_archaeologist.eval.materialize import (
    MaterializationError,
    materialize,
    materialize_base,
)
from cobol_archaeologist.eval.metrics import evaluate
from cobol_archaeologist.eval.run import (
    EvaluationRunner,
    RunManifest,
    SystemContext,
    assess_run_validity,
    build_system_context,
    infrastructure_failure,
    investigate_all_hunts,
    record_outcome,
    run_key,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model import provider as provider_module
from cobol_archaeologist.model.prompt import AgentResponse, CachedDecisionModel
from cobol_archaeologist.model.provider import (
    AnthropicDecisionModel,
    OllamaDecisionModel,
    OpenAIDecisionModel,
    ProviderUnavailable,
)
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import DriftInstance, DriftPrediction
from cobol_archaeologist.tools import RealToolLayer

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "data" / "benchmark" / "v1-pre" / "test.jsonl"
DEV_SPLIT = ROOT / "data" / "benchmark" / "v1" / "dev.jsonl"
PROGRAMS = ROOT / "data" / "benchmark" / "seed" / "programs"
CLAUSES = ROOT / "data" / "regulations" / "clauses.jsonl"


def _rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _by_operator(operator: str) -> DriftInstance:
    return next(
        row
        for row in _rows()
        if (row.provenance.mutation or "").startswith(f"{operator};")
    )


def _dev_rows() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in DEV_SPLIT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _mutation_field(row: DriftInstance, field: str) -> str:
    mutation = row.provenance.mutation or ""
    return ast.literal_eval(
        next(
            segment.strip().partition("=")[2]
            for segment in mutation.split(";")[1:]
            if segment.strip().startswith(f"{field}=")
        )
    )


@pytest.mark.parametrize("operator", ["MO-1", "MO-1×", "MO-6×"])
def test_materializes_local_copybook_and_interprogram_edits(operator):
    row = _by_operator(operator)
    source = materialize(row)
    old_new = {}
    for segment in row.provenance.mutation.split(";")[1:]:
        key, separator, value = segment.strip().partition("=")
        if separator and key in {"old", "new"}:
            old_new[key] = ast.literal_eval(value)

    assert source.main_file == row.provenance.base_program
    assert len(source.source_sha256) == 64
    assert old_new["new"] in "\n".join(source.files.values())
    if operator == "MO-1×":
        assert any(name.lower().endswith(".cpy") for name in source.files)
    if operator == "MO-6×":
        assert (
            len([name for name in source.files if name.lower().endswith(".cbl")]) >= 2
        )


def test_materializer_blanks_deletion_without_changing_line_count(tmp_path):
    row = _by_operator("MO-2")
    mutation = row.provenance.mutation or ""
    old = ast.literal_eval(
        next(
            segment.strip().partition("=")[2]
            for segment in mutation.split(";")[1:]
            if segment.strip().startswith("old=")
        )
    )
    locus = row.code_locus.loci[0]
    line_count = max(31, locus.line_span[1])
    lines = ["       01 FILLER PIC X.\n"] * line_count
    lines[locus.line_span[0] - 1] = f"       {old}\n"
    (tmp_path / row.provenance.base_program).write_text(
        "".join(lines),
        encoding="utf-8",
    )

    source = materialize(row, programs_root=tmp_path)

    assert old not in source.files[row.provenance.base_program]
    assert len(source.files[row.provenance.base_program].splitlines()) == line_count


def test_materializer_replaces_actual_multiline_non_deletion_block():
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    base = materialize_base(row)
    source = materialize(row)
    base_text = base.files[row.provenance.base_program]
    materialized_text = source.files[row.provenance.base_program]
    new = _mutation_field(row, "new")

    assert new in materialized_text
    assert _mutation_field(row, "old") not in materialized_text
    assert materialized_text.count("\n") == base_text.count("\n")
    assert len(materialized_text.splitlines()) == len(base_text.splitlines())


def test_all_dev_rows_materialize():
    rows = _dev_rows()

    assert len(rows) == 102
    for row in rows:
        source = materialize(row)
        assert source.files


def test_materializer_rejects_zero_normalized_block_matches(tmp_path):
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    source_path = PROGRAMS / "train-bases" / row.provenance.base_program
    text = source_path.read_text(encoding="utf-8")
    old = _mutation_field(row, "old")
    broken = text.replace(
        "IF WS-DAYS-SINCE-ISSUE > 30", "IF WS-DAYS-SINCE-ISSUE > 300"
    )
    assert old not in broken
    (tmp_path / row.provenance.base_program).write_text(broken, encoding="utf-8")

    with pytest.raises(MaterializationError, match="normalized block .* matched 0"):
        materialize(row, programs_root=tmp_path)


def test_materializer_rejects_ambiguous_normalized_block_matches(tmp_path):
    row = next(
        row
        for row in _dev_rows()
        if row.provenance.base_program == "ACTIVAT1.cbl"
        and (row.provenance.mutation or "").startswith("MO-2;")
    )
    source_path = PROGRAMS / "train-bases" / row.provenance.base_program
    text = source_path.read_text(encoding="utf-8")
    old = _mutation_field(row, "old")
    expanded = text + "\n" + old.lower() + "\n"
    (tmp_path / row.provenance.base_program).write_text(expanded, encoding="utf-8")
    broad_locus = row.code_locus.loci[0].model_copy(
        update={"line_span": (row.code_locus.loci[0].line_span[0], 100)}
    )
    ambiguous = row.model_copy(
        update={
            "code_locus": row.code_locus.model_copy(update={"loci": [broad_locus]})
        }
    )

    with pytest.raises(MaterializationError, match="normalized block .* matched 2"):
        materialize(ambiguous, programs_root=tmp_path)


def test_materializer_rejects_source_drift_and_ambiguity(tmp_path):
    row = _by_operator("MO-1")
    (tmp_path / row.provenance.base_program).write_text(
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n",
        encoding="utf-8",
    )
    with pytest.raises(MaterializationError, match="matched 0"):
        materialize(row, programs_root=tmp_path)


def test_materializer_maps_internal_program_id_to_opaque_main_filename(tmp_path):
    row = _rows()[0]
    opaque_name = "OPAQUE-FIXTURE.cbl"
    (tmp_path / opaque_name).write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. INTERNAL-ID.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN.\n"
        "           STOP RUN.\n",
        encoding="utf-8",
    )
    locus = row.code_locus.loci[0].model_copy(
        update={"program": "INTERNAL-ID", "line_span": (4, 5)}
    )
    opaque = row.model_copy(
        update={
            "provenance": row.provenance.model_copy(
                update={"base_program": opaque_name}
            ),
            "code_locus": row.code_locus.model_copy(
                update={"loci": (locus,), "is_interprocedural": False}
            ),
        }
    )

    source = materialize_base(opaque, programs_root=tmp_path)

    assert source.main_file == opaque_name
    assert set(source.files) == {opaque_name}


def test_system_context_contains_no_gold_or_mutation_fields():
    row = _by_operator("MO-1")
    serialized = build_system_context(row).model_dump_json().lower()
    for prohibited in (
        "instance_id",
        "drift_type",
        "gold_rationale",
        "mutation",
        "old=",
        "new=",
        "line_level",
    ):
        assert prohibited not in serialized


def test_provider_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable, match="ANTHROPIC_API_KEY"):
        AnthropicDecisionModel()


def test_openai_provider_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable, match="OPENAI_API_KEY"):
        OpenAIDecisionModel()


def test_ollama_provider_is_local_structured_and_credential_free(monkeypatch):
    captured = {}
    response_text = json.dumps(
        {
            "kind": "abstain",
            "thought": "Evidence is insufficient.",
            "abstention_reason": "No supported code fact.",
            "final_answer": "Abstained.",
            "token_count": 0,
        }
    )
    raw_response = {
        "model": "qwen3:4b",
        "done": True,
        "message": {"role": "assistant", "content": response_text},
        "prompt_eval_count": 11,
        "eval_count": 7,
    }

    class FakeHTTPResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(raw_response).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHTTPResponse()

    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read")
    model = OllamaDecisionModel(model_id="qwen3:4b", timeout_s=9)
    result = model.respond(
        system_prompt="system",
        question="question",
        transcript=[],
    )

    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert request.get_header("Authorization") is None
    assert captured["timeout"] == 9
    assert payload["model"] == "qwen3:4b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0.0, "seed": 2601}
    assert payload["format"]["title"] == "AgentResponse"
    assert payload["format"]["$defs"]["DriftPrediction"]["properties"]["instance_id"][
        "enum"
    ] == ["drift_000000"]
    assert "must-not-be-read" not in json.dumps(payload)
    assert result.kind == "abstain"
    assert result.token_count == 18
    assert result.raw_provider_text == response_text


def test_ollama_provider_rejects_non_loopback_endpoint():
    with pytest.raises(ValueError, match="local HTTP loopback"):
        OllamaDecisionModel(endpoint="https://example.com/api/chat")


def test_openai_provider_forces_one_response_function_without_persisting(
    monkeypatch,
):
    captured = {}
    response_text = json.dumps(
        {
            "kind": "abstain",
            "thought": "Evidence is insufficient.",
            "abstention_reason": "No supported code fact.",
            "final_answer": "Abstained.",
            "token_count": 0,
        }
    )
    raw_response = {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": "submit_agent_response",
                "arguments": response_text,
            }
        ],
        "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    }

    class FakeHTTPResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(raw_response).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHTTPResponse()

    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen)
    model = OpenAIDecisionModel(
        api_key="test-only-key",
        model_id="gpt-5.6-sol",
        timeout_s=9,
    )
    result = model.respond(
        system_prompt="system",
        question="question",
        transcript=[],
    )

    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert request.get_header("Authorization") == "Bearer test-only-key"
    assert captured["timeout"] == 9
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["temperature"] == 0.0
    assert payload["tool_choice"] == {
        "type": "function",
        "name": "submit_agent_response",
    }
    assert payload["parallel_tool_calls"] is False
    assert len(payload["tools"]) == 1
    response_tool = payload["tools"][0]
    assert response_tool["type"] == "function"
    assert response_tool["name"] == "submit_agent_response"
    assert response_tool["strict"] is False
    provider_input = json.loads(payload["input"])
    provider_instruction = provider_input["instruction"]
    response_schema = response_tool["parameters"]
    assert response_schema["title"] == "AgentResponse"
    assert "Call submit_agent_response exactly once and stop" in provider_instruction
    assert "code_locus (loci, slice_vars, is_interprocedural)" in (provider_instruction)
    prediction_id = response_schema["$defs"]["DriftPrediction"]["properties"][
        "instance_id"
    ]
    assert "provenance" not in response_schema["$defs"]["DriftPrediction"]["properties"]
    assert "raw_provider_text" not in response_schema["properties"]
    assert "contract_error" not in response_schema["properties"]
    assert "allOf" not in response_schema
    assert "requires both a complete prediction" in response_schema["description"]
    assert (
        "Required and complete"
        in response_schema["properties"]["prediction"]["description"]
    )
    assert (
        "Required and non-empty"
        in response_schema["properties"]["claim"]["description"]
    )
    assert prediction_id["enum"] == ["drift_000000"]
    assert payload["store"] is False
    assert "test-only-key" not in json.dumps(payload)
    assert result.kind == "abstain"
    assert result.token_count == 18
    assert result.raw_provider_text == response_text


def test_openai_provider_omits_temperature_for_reasoning_effort(monkeypatch):
    captured = {}
    model = OpenAIDecisionModel(
        api_key="test-only-key",
        model_id="gpt-5.6-luna",
        reasoning_effort="low",
    )

    def fake_request(request):
        captured["payload"] = json.loads(request.data)
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "submit_agent_response",
                    "arguments": json.dumps(
                        {
                            "kind": "abstain",
                            "thought": "No supported finding.",
                            "abstention_reason": "insufficient evidence",
                            "token_count": 0,
                        }
                    ),
                }
            ],
            "usage": {"total_tokens": 9},
        }

    monkeypatch.setattr(model, "_request", fake_request)
    model.respond(system_prompt="system", question="question", transcript=[])

    assert captured["payload"]["reasoning"] == {"effort": "low"}
    assert "temperature" not in captured["payload"]
    assert captured["payload"]["store"] is False


def test_openai_provider_rejects_multiple_response_function_calls(monkeypatch):
    model = OpenAIDecisionModel(api_key="test-only-key")
    response_text = json.dumps(
        {
            "kind": "abstain",
            "thought": "No supported finding.",
            "abstention_reason": "insufficient evidence",
            "token_count": 0,
        }
    )

    def fake_request(request):
        return {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "submit_agent_response",
                    "arguments": response_text,
                },
                {
                    "type": "function_call",
                    "name": "submit_agent_response",
                    "arguments": response_text,
                },
            ],
            "usage": {"total_tokens": 12},
        }

    monkeypatch.setattr(model, "_request", fake_request)
    result = model.respond(
        system_prompt="system",
        question="question",
        transcript=[],
    )

    assert result.kind == "abstain"
    assert result.contract_error is not None
    assert "expected exactly one submit_agent_response call" in result.contract_error
    assert result.token_count == 12


def test_openai_provider_owns_placeholder_identity_not_model_output():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    raw["prediction"]["instance_id"] = "invented-semantic-name"
    raw.pop("final_answer", None)

    result = provider_module._agent_response(
        json.dumps(raw),
        17,
        prediction_instance_id="drift_000000",
    )

    assert result.prediction is not None
    assert result.prediction.instance_id == "drift_000000"
    assert result.final_answer == result.claim
    assert result.token_count == 17


def test_openai_provider_canonicalizes_only_target_path_notation():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    raw["prediction"]["target_path"] = "current_value.value.past_due_grace"
    composite = provider_module._agent_response(json.dumps(raw), 1)
    assert composite.prediction is not None
    assert composite.prediction.target_path == "past_due_grace"

    raw["prediction"]["regulation_clause"]["current_value"] = {
        "kind": "duration_days",
        "value": 7,
        "comparator": "at_most",
        "note": None,
    }
    raw["prediction"]["target_path"] = "current_value.value"
    leaf = provider_module._agent_response(json.dumps(raw), 1)
    assert leaf.prediction is not None
    assert leaf.prediction.target_path is None


def test_openai_provider_normalizes_non_applicable_arguments_null():
    raw = {
        "kind": "abstain",
        "thought": "Evidence is insufficient.",
        "tool": None,
        "arguments": None,
        "prediction": None,
        "abstention_reason": "No supported code fact.",
        "token_count": 0,
    }

    result = provider_module._agent_response(json.dumps(raw), 5)

    assert result.contract_error is None
    assert result.arguments == {}
    assert result.token_count == 5
    assert result.raw_provider_text == json.dumps(raw)


def test_openai_provider_reparents_unambiguous_prediction_siblings():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    for field in ("claim", "exec_probe", "static_claim", "final_answer"):
        if field in raw:
            raw["prediction"][field] = raw.pop(field)
    raw["prediction"]["token_count"] = raw.pop("token_count", 0)

    result = provider_module._agent_response(
        json.dumps(raw),
        13,
        prediction_instance_id="drift_000000",
    )

    assert result.contract_error is None
    assert result.kind == "finding"
    assert result.prediction is not None
    assert result.claim
    assert result.token_count == 13


def test_openai_provider_canonicalizes_unambiguous_locus_wire_shape():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    prediction = raw["prediction"]
    prediction["is_interprocedural"] = prediction["code_locus"]["is_interprocedural"]
    prediction["},"] = ":null"
    ref = prediction["labels"]["line_level"][0]
    line = ref.pop("line")
    ref["program"] = "COPYBOOK_ALIAS"
    ref["file"] = line

    result = provider_module._agent_response(
        json.dumps(raw),
        13,
        prediction_instance_id="drift_000000",
    )

    assert result.contract_error is None
    assert result.prediction is not None
    normalized_ref = result.prediction.labels.line_level[0]
    assert normalized_ref.line == line
    assert normalized_ref.file is None
    assert normalized_ref.program == "LATEFEE1"
    assert result.prediction.code_locus.is_interprocedural is False


def test_openai_provider_rejects_conflicting_prediction_sibling():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    raw["prediction"]["claim"] = "A conflicting nested claim."

    result = provider_module._agent_response(
        json.dumps(raw),
        13,
        prediction_instance_id="drift_000000",
    )

    assert result.kind == "abstain"
    assert result.contract_error is not None
    assert "prediction.claim: Extra inputs are not permitted" in result.contract_error


def test_openai_provider_turns_malformed_finding_into_typed_abstention():
    raw = json.loads(
        (ROOT / "tests" / "fixtures" / "agent" / "unverified_responses.json").read_text(
            encoding="utf-8"
        )
    )[0]
    raw["prediction"]["labels"]["line_level"][0]["line"] = 999_999

    result = provider_module._agent_response(json.dumps(raw), 23)

    assert result.kind == "abstain"
    assert result.prediction is None
    assert result.abstention_reason is not None
    assert result.abstention_reason.startswith(
        "response contract rejected proposed output:"
    )
    assert "matches no locus span" in result.abstention_reason
    assert result.token_count == 23
    assert result.contract_error == result.abstention_reason
    assert result.raw_provider_text

    reparsed = json.loads(result.raw_provider_text)
    reparsed["prediction"]["labels"]["line_level"][0]["line"] = reparsed["prediction"][
        "code_locus"
    ]["loci"][0]["line_span"][0]
    repaired = provider_module._agent_response(json.dumps(reparsed), 11)
    assert repaired.kind == "finding"
    assert repaired.contract_error is None


@pytest.mark.parametrize(
    "provider_text", ["not JSON", '{"kind": "abstain"} trailing {}']
)
def test_openai_provider_turns_malformed_text_into_typed_abstention(provider_text):
    result = provider_module._agent_response(provider_text, 29)

    assert result.kind == "abstain"
    assert result.prediction is None
    assert result.abstention_reason is not None
    assert result.abstention_reason.startswith(
        "response contract rejected provider output:"
    )
    assert result.token_count == 29


def test_week7_mutation_real_tool_agent_eval_seam(tmp_path):
    record = next(
        item
        for item in load_clause_records(CLAUSES)
        if item.record_id == "KYC-ckycr-update"
    )
    base = ProgramSource.from_path(
        PROGRAMS / "KYCSYNC2.cbl",
        touched_variables=("WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"),
    )
    emitted = mutate(base, record, "MO-1", random.Random(2404))
    (tmp_path / emitted.source.filename).write_text(
        emitted.source.text,
        encoding="utf-8",
    )
    for name, text in emitted.source.files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    responses = tmp_path / "responses.json"
    responses.write_text(
        json.dumps(
            [
                {
                    "kind": "tool",
                    "thought": "Find the mutated SLA literal through the real facade.",
                    "tool": "grep",
                    "arguments": {"pattern": "14"},
                    "token_count": 8,
                },
                {
                    "kind": "abstain",
                    "thought": "This seam checks transport, not model accuracy.",
                    "abstention_reason": "seam fixture stops after real evidence",
                    "final_answer": "Abstained after real-tool seam evidence.",
                    "token_count": 8,
                },
            ]
        ),
        encoding="utf-8",
    )
    tools = RealToolLayer(corpus_root=tmp_path, copybook_paths=[tmp_path])
    trajectory = InvestigationLoop(
        tools,
        model=CachedDecisionModel(responses),
        clock=lambda: 100.0,
    ).run("Check the CKYCR update deadline.")

    assert [step.tool for step in trajectory.steps] == ["grep"]
    assert trajectory.steps[0].error is None
    assert "14" in trajectory.steps[0].observation_summary

    evaluation = EvaluationRecord(
        instance_id=emitted.instance.instance_id,
        gold=emitted.instance,
        trajectory=trajectory,
        abstained=True,
        abstention_reason=trajectory.abstention_reason,
        system_id="week7-seam",
        source_sha256="0" * 64,
        run_key="week7-seam",
    )
    score = evaluate([evaluation])["overall"]["t1_detection"]
    assert score["fn"] == 1
    assert score["answer_rate"] == 0


def test_append_only_runner_resumes_without_duplicate_execution(tmp_path):
    rows = _rows()[:2]
    runner = EvaluationRunner(
        tmp_path / "records.jsonl",
        tmp_path / "manifest.json",
    )
    manifest = RunManifest(
        system_id="fixture",
        model_id="none",
        repository_commit="a" * 40,
        prompt_version="test",
        split_path="test.jsonl",
        total=2,
    )
    calls: list[str] = []

    def execute(gold, context, key):
        calls.append(gold.instance_id)
        assert "drift_type" not in context.model_dump_json()
        return infrastructure_failure(
            gold,
            system_id="fixture",
            source_sha256="0" * 64,
            key=key,
            reason="fixture has no provider",
        )

    def key_factory(gold):
        return f"key:{gold.instance_id}"
    first = runner.run(
        rows,
        manifest=manifest,
        key_factory=key_factory,
        executor=execute,
    )
    second = runner.run(
        rows,
        manifest=manifest,
        key_factory=key_factory,
        executor=execute,
    )

    assert len(first) == len(second) == 2
    assert calls == [row.instance_id for row in rows]
    assert len((tmp_path / "records.jsonl").read_text().splitlines()) == 2


def test_runner_persists_smoke_selection_identity_before_execution(tmp_path):
    row = _rows()[0]
    runner = EvaluationRunner(
        tmp_path / "records.jsonl",
        tmp_path / "manifest.json",
    )
    manifest = RunManifest(
        system_id="fixture",
        model_id="none",
        repository_commit="a" * 40,
        prompt_version="test",
        split_path="test.jsonl",
        run_mode="smoke",
        smoke_rows=1,
        smoke_seed=20260726,
        smoke_instance_ids=[row.instance_id],
        total=1,
    )

    def execute(gold, _context, key):
        persisted = RunManifest.model_validate_json(
            runner.manifest_path.read_text(encoding="utf-8")
        )
        assert persisted.smoke_seed == 20260726
        assert persisted.smoke_instance_ids == [row.instance_id]
        return infrastructure_failure(
            gold,
            system_id="fixture",
            source_sha256="0" * 64,
            key=key,
            reason="offline gate",
        )

    runner.run(
        [row],
        manifest=manifest,
        key_factory=lambda gold: f"key:{gold.instance_id}",
        executor=execute,
    )


def test_run_key_pins_model_and_tool_versions():
    base = {
        "instance_id": "drift_000001",
        "source_sha256": "0" * 64,
        "system_id": "agent",
        "model_id": "gpt-5.6-sol",
        "budgets": {"max_steps": 8},
        "prompt_version": "m4-live-v1",
        "tool_version": "tools@abc",
        "commit": "a" * 40,
    }
    key = run_key(**base)
    assert key != run_key(**{**base, "model_id": "gpt-5.6-terra"})
    assert key != run_key(**{**base, "tool_version": "tools@def"})


def test_benchmark_runner_promotes_provider_failure_to_infrastructure():
    class BrokenProvider:
        model_id = "broken"
        temperature = 0.0
        seed = None

        def respond(self, **_kwargs):
            raise ProviderUnavailable("transient provider failure")

    gold = _by_operator("MO-1")
    tools = RealToolLayer(corpus_root=PROGRAMS, copybook_paths=[PROGRAMS])
    with pytest.raises(RuntimeError, match="ProviderUnavailable"):
        investigate_all_hunts(
            build_system_context(gold),
            tools=tools,
            model_factory=BrokenProvider,
        )


def _abstained_record(
    *,
    system_id: str,
    responses: list[AgentResponse],
    contract_repairs: int = 0,
) -> EvaluationRecord:
    gold = _by_operator("MO-1")
    trajectory = Trajectory(
        question="offline validity fixture",
        steps=[],
        model_responses=responses,
        verification=None,
        finding=None,
        abstained=True,
        abstention_reason="fixture abstention",
        budget=BudgetSpec(max_steps=8, max_tokens=1000),
        budget_exhausted=False,
        tokens_used=sum(response.token_count for response in responses),
        contract_repairs=contract_repairs,
        final_answer="Abstained: fixture abstention",
        model_id="offline",
        seed=0,
    )
    return EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        trajectory=trajectory,
        abstained=True,
        abstention_reason="fixture abstention",
        system_id=system_id,
        source_sha256="0" * 64,
        run_key=f"{system_id}:fixture",
    )


def _semantic_abstention() -> AgentResponse:
    return AgentResponse(
        kind="abstain",
        thought="No supported finding.",
        abstention_reason="no supported finding",
        token_count=1,
    )


def test_run_validity_reports_all_failed_gates_with_frozen_precedence():
    rejected = AgentResponse(
        kind="abstain",
        thought="Contract failure.",
        abstention_reason="contract failure",
        token_count=1,
        raw_provider_text="bad",
        contract_error="bad JSON",
    )
    contract_record = _abstained_record(
        system_id="rag_reranker",
        responses=[rejected, *[_semantic_abstention() for _ in range(4)]],
        contract_repairs=1,
    )
    contract = assess_run_validity([contract_record], system_id="rag_reranker")
    assert contract.status == "HALTED_CONTRACT_REJECTIONS"
    assert contract.contract_rejection_rate == 0.2
    assert len(contract.failed_gates) == 2

    agent = assess_run_validity(
        [_abstained_record(system_id="agent", responses=[_semantic_abstention()])],
        system_id="agent",
    )
    assert agent.status == "INVALID_AGENT_RUN"
    assert len(agent.failed_gates) == 2

    not_evaluable = assess_run_validity(
        [
            _abstained_record(
                system_id="oracle_slice",
                responses=[_semantic_abstention()],
            )
        ],
        system_id="oracle_slice",
    )
    assert not_evaluable.status == "NOT_EVALUABLE"


def test_run_validity_accepts_a_verified_non_null_prediction():
    gold = _by_operator("MO-1")
    prediction = DriftPrediction.from_gold(gold)
    verified = Trajectory.model_validate_json(
        (
            ROOT / "tests" / "fixtures" / "agent" / "golden_late_fee_trajectory.json"
        ).read_text(encoding="utf-8")
    ).verification
    response = AgentResponse(
        kind="finding",
        thought="A verified fixture finding.",
        prediction=prediction,
        claim=prediction.rationale,
        final_answer=prediction.rationale,
        token_count=1,
    )
    trajectory = Trajectory(
        question="offline validity fixture",
        steps=[],
        model_responses=[response],
        verification=verified,
        finding=prediction,
        abstained=False,
        abstention_reason=None,
        budget=BudgetSpec(max_steps=1, max_tokens=100),
        budget_exhausted=False,
        tokens_used=1,
        final_answer=prediction.rationale,
        model_id="offline",
        seed=0,
    )
    record = EvaluationRecord(
        instance_id=gold.instance_id,
        gold=gold,
        prediction=prediction,
        confidence=0.85,
        verification=verified,
        trajectory=trajectory,
        abstained=False,
        system_id="rag_reranker",
        source_sha256="0" * 64,
        run_key="valid:fixture",
    )

    assert assess_run_validity([record], system_id="rag_reranker").status == "VALID"


def test_agent_record_persists_all_seven_hunts_and_validity_counts_them():
    hunt_cache = ROOT / "tests" / "fixtures" / "hunts" / "cached_decisions.json"
    corpus = ROOT / "tests" / "fixtures" / "hunts" / "corpus"
    raw = json.loads(hunt_cache.read_text(encoding="utf-8"))
    clause = raw["d1"][-1]["prediction"]["regulation_clause"]
    cache_keys = iter(["d1", "d2", "d3", "d4", "d5", "d6", "d7"])
    batch = investigate_all_hunts(
        SystemContext(
            clause=clause,
            program_scope="CLOSPEN1",
            question="offline seven-hunt fixture",
        ),
        tools=StubToolLayer(corpus),
        model_factory=lambda: CachedDecisionModel(
            hunt_cache,
            cache_key=next(cache_keys),
        ),
        entailer=LexicalEntailer(),
    )
    prediction = batch.selected.finding
    assert prediction is not None
    gold_payload = prediction.model_dump(mode="json")
    gold_payload["gold_rationale"] = gold_payload.pop("rationale")
    gold_payload["provenance"] = {
        "source": "real_curated",
        "base_program": "CLOSPEN1.cbl",
    }
    gold = DriftInstance.model_validate(gold_payload)
    record = record_outcome(
        gold,
        batch,
        system_id="agent",
        source_sha256="0" * 64,
        key="seven-hunts",
    )

    assert len(record.agent_hunts) == 7
    assert sum(trace.selected for trace in record.agent_hunts) == 1
    validity = assess_run_validity([record], system_id="agent")
    assert validity.provider_turns == sum(
        len(trace.trajectory.model_responses) for trace in record.agent_hunts
    )
    assert validity.provider_turns > len(record.trajectory.model_responses)
