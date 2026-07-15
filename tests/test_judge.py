"""T2.4 gates for plausibility judging and human spot-check bookkeeping."""

from __future__ import annotations

import io
import json
import shutil
import urllib.error
from pathlib import Path

import pytest

import cobol_archaeologist.benchmark.judge as judge_module
from cobol_archaeologist.benchmark.judge import (
    FamilyIntegrityError,
    JudgeConfig,
    JudgeConfigurationError,
    Judgement,
    PlausibilityGateError,
    UnsureAdjudication,
    apply_drop_policy,
    judge_benchmark,
    load_judgements,
    plausibility_gate,
    reconstruct_sources,
    record_human_agreement,
    render_prompt,
)
from cobol_archaeologist.cli import main
from cobol_archaeologist.schemas import DriftInstance


ROOT = Path(__file__).resolve().parents[1]
INSTANCES = ROOT / "data" / "benchmark" / "drift_instances.jsonl"
RUBRIC = ROOT / "docs" / "tasks" / "T2.4-judging-rubric.md"


def _instances() -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in INSTANCES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def sources():
    return reconstruct_sources(INSTANCES)


def _config(**updates) -> JudgeConfig:
    values = {
        "endpoint": "https://judge.invalid/v1",
        "api_key": "test-key",
        "model": "gpt-test-judge",
        "model_family": "openai",
    }
    values.update(updates)
    return JudgeConfig(**values)


def _copy_benchmark(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "drift_instances.jsonl"
    shutil.copy2(INSTANCES, target)
    shutil.copy2(
        INSTANCES.with_suffix(".manifest.json"), target.with_suffix(".manifest.json")
    )
    return target


def test_gate_a_refuses_same_family_and_disguised_model_names():
    with pytest.raises(FamilyIntegrityError):
        _config(model="claude-sonnet", model_family="anthropic").validate()
    with pytest.raises(FamilyIntegrityError):
        _config(model="claude-sonnet", model_family="openai").validate()
    _config(model="gemini-test", model_family="google").validate()
    with pytest.raises(JudgeConfigurationError, match="reasoning effort"):
        _config(reasoning_effort="extreme").validate()


def test_endpoint_transport_supports_reasoning_and_reports_api_error(monkeypatch):
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"verdict":"plausible","reason":"ok"}'}}]}
            ).encode("utf-8")

    def succeed(request, timeout):
        captured.update(json.loads(request.data))
        assert timeout == 60.0
        return Response()

    monkeypatch.setattr(judge_module.urllib.request, "urlopen", succeed)
    content = judge_module._endpoint_transport(
        _config(reasoning_effort="high"), "review prompt"
    )
    assert json.loads(content)["verdict"] == "plausible"
    assert captured["reasoning_effort"] == "high"
    assert "temperature" not in captured

    body = b'{"error":{"message":"Unsupported request field"}}'

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://judge.invalid/v1/chat/completions",
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr(judge_module.urllib.request, "urlopen", fail)
    monkeypatch.setattr(judge_module.time, "sleep", lambda _seconds: None)
    with pytest.raises(JudgeConfigurationError, match="Unsupported request field"):
        judge_module._endpoint_transport(_config(), "review prompt")


def test_gate_b_reconstructs_every_mutated_source(sources):
    instances = _instances()
    assert set(sources) == {instance.instance_id for instance in instances}
    assert all(render_prompt(item, sources[item.instance_id]) for item in instances)


def test_gate_b_prompt_contains_clause_and_each_mutated_locus(sources):
    instance = next(item for item in _instances() if item.code_locus.is_interprocedural)
    prompt = render_prompt(instance, sources[instance.instance_id])
    assert instance.regulation_clause.text in prompt
    assert prompt.count("## Mutated locus") == len(instance.code_locus.loci)
    assert "Does this look like drift that could occur in real legacy code" in prompt
    assert "gold_rationale" not in prompt
    assert "provenance" not in prompt


def test_gate_c_stratified_50_run_is_deterministic_and_updates_manifest(
    tmp_path, sources
):
    left_input = _copy_benchmark(tmp_path / "left")
    right_input = _copy_benchmark(tmp_path / "right")
    left_out = tmp_path / "left" / "judgements.jsonl"
    right_out = tmp_path / "right" / "judgements.jsonl"

    def plausible(_config, _prompt):
        return json.dumps(
            {"verdict": "plausible", "reason": "credible maintenance drift"}
        )

    left = judge_benchmark(
        instances_path=left_input,
        output_path=left_out,
        config=_config(),
        sample=50,
        seed=2400,
        transport=plausible,
        source_index=sources,
    )
    right = judge_benchmark(
        instances_path=right_input,
        output_path=right_out,
        config=_config(),
        sample=50,
        seed=2400,
        transport=plausible,
        source_index=sources,
    )
    assert left_out.read_bytes() == right_out.read_bytes()
    assert left == right
    judgements = load_judgements(left_out)
    assert len(judgements) == 50
    assert {item.drift_type for item in judgements} == {
        "D1_stale_threshold",
        "D2_missing_rule",
        "D3_contradictory",
        "D4_stale_reference_data",
        "D5_boundary_error",
        "D6_dead_code",
        "D7_conformant",
    }
    assert {item.is_interprocedural for item in judgements} == {False, True}
    manifest = json.loads(
        left_input.with_suffix(".manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["judging"]["model"] == "gpt-test-judge"
    assert manifest["judging"]["model_family"] == "openai"
    assert manifest["judging"]["sample"]["plausible_rate"] == 1.0
    assert manifest["judging"]["sample"]["gate_passed"] is True


def test_judging_checkpoints_each_verdict_and_resumes_after_endpoint_failure(
    tmp_path, sources
):
    instances = _copy_benchmark(tmp_path)
    output = tmp_path / "judgements.jsonl"
    call_count = 0

    def interrupted(_config, _prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise JudgeConfigurationError("HTTP 401: permission changed")
        return json.dumps(
            {"verdict": "plausible", "reason": "credible maintenance drift"}
        )

    with pytest.raises(JudgeConfigurationError, match=r"2/\d+ judgements checkpointed"):
        judge_benchmark(
            instances_path=instances,
            output_path=output,
            config=_config(),
            sample=7,
            seed=2400,
            transport=interrupted,
            source_index=sources,
        )
    assert len(load_judgements(output)) == 2

    resumed_calls = 0

    def plausible(_config, _prompt):
        nonlocal resumed_calls
        resumed_calls += 1
        return json.dumps(
            {"verdict": "plausible", "reason": "credible maintenance drift"}
        )

    report = judge_benchmark(
        instances_path=instances,
        output_path=output,
        config=_config(),
        sample=7,
        seed=2400,
        transport=plausible,
        source_index=sources,
    )
    assert report["resumed_count"] == 2
    assert resumed_calls == report["sample_size"] - 2
    assert len(load_judgements(output)) == report["sample_size"]


def test_judging_reuses_matching_instance_ids_without_endpoint_calls(
    tmp_path, sources, monkeypatch
):
    instances = _copy_benchmark(tmp_path)
    prior = tmp_path / "prior.jsonl"
    output = tmp_path / "reused.jsonl"

    def plausible(_config, _prompt):
        return json.dumps(
            {"verdict": "plausible", "reason": "credible maintenance drift"}
        )

    initial = judge_benchmark(
        instances_path=instances,
        output_path=prior,
        config=_config(),
        sample=7,
        seed=2400,
        transport=plausible,
        source_index=sources,
    )

    def unexpected_call(_config, _prompt):
        raise AssertionError("matching cached judgement should bypass the endpoint")

    def unexpected_reconstruction(_path):
        raise AssertionError("a fully cached selection does not need source rebuilding")

    monkeypatch.setattr(
        judge_module, "reconstruct_sources", unexpected_reconstruction
    )
    reused = judge_benchmark(
        instances_path=instances,
        output_path=output,
        config=_config(),
        sample=7,
        seed=2400,
        reuse_path=prior,
        transport=unexpected_call,
    )
    assert reused["reused_count"] == initial["sample_size"]
    assert output.read_bytes() == prior.read_bytes()


def test_gate_d_plausibility_threshold_is_exactly_ninety_percent():
    passing = [
        Judgement(
            instance_id=f"drift_{index:06d}",
            drift_type="D1_stale_threshold",
            is_interprocedural=False,
            verdict="plausible" if index < 45 else "implausible",
            reason="reviewed",
            model="gpt-test-judge",
            model_family="openai",
        )
        for index in range(50)
    ]
    assert plausibility_gate(passing) == 0.9
    with pytest.raises(PlausibilityGateError):
        plausibility_gate(
            [
                item.model_copy(update={"verdict": "implausible"})
                if index == 44
                else item
                for index, item in enumerate(passing)
            ]
        )


def test_gate_e_drop_policy_separates_implausible_and_unsure(tmp_path):
    instances = _instances()[:3]
    source = tmp_path / "instances.jsonl"
    source.write_text(
        "\n".join(item.model_dump_json() for item in instances) + "\n", encoding="utf-8"
    )
    judgements = [
        Judgement(
            instance_id=instance.instance_id,
            drift_type=instance.drift_type,
            is_interprocedural=instance.code_locus.is_interprocedural,
            verdict=verdict,
            reason=f"{verdict} reason",
            model="gpt-test-judge",
            model_family="openai",
        )
        for instance, verdict in zip(
            instances, ("plausible", "implausible", "unsure"), strict=True
        )
    ]
    accepted = tmp_path / "accepted.jsonl"
    rejected = tmp_path / "rejected"
    report = apply_drop_policy(source, judgements, accepted, rejected)
    assert report == {
        "accepted": 1,
        "implausible": 1,
        "unsure": 1,
        "adjudicated": 0,
    }
    assert len(accepted.read_text(encoding="utf-8").splitlines()) == 1
    assert (rejected / "implausible.jsonl").is_file()
    assert (rejected / "unsure.jsonl").is_file()

    adjudicated = apply_drop_policy(
        source,
        judgements,
        accepted,
        rejected,
        [
            UnsureAdjudication(
                instance_id=instances[2].instance_id,
                verdict="plausible",
                reason="Natural conformant maintenance edit.",
            )
        ],
    )
    assert adjudicated == {
        "accepted": 2,
        "implausible": 1,
        "unsure": 0,
        "adjudicated": 1,
    }
    assert not (rejected / "unsure.jsonl").read_text(encoding="utf-8")


def test_gate_f_records_exactly_fifteen_human_reviews(tmp_path):
    instances = _instances()[:15]
    judgements_path = tmp_path / "judgements.jsonl"
    judgements = [
        Judgement(
            instance_id=instance.instance_id,
            drift_type=instance.drift_type,
            is_interprocedural=instance.code_locus.is_interprocedural,
            verdict="plausible",
            reason="judge reason",
            model="gpt-test-judge",
            model_family="openai",
        )
        for instance in instances
    ]
    judgements_path.write_text(
        "\n".join(item.model_dump_json() for item in judgements) + "\n",
        encoding="utf-8",
    )
    reviews = tmp_path / "human.jsonl"
    reviews.write_text(
        "\n".join(
            json.dumps(
                {
                    "instance_id": item.instance_id,
                    "verdict": "implausible" if index == 0 else "plausible",
                    "reason": "human review",
                }
            )
            for index, item in enumerate(judgements)
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"judging": {}}), encoding="utf-8")
    agreement = record_human_agreement(judgements_path, reviews, manifest)
    assert agreement == {"reviewed": 15, "agreed": 14, "rate": 14 / 15}
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["judging"]["human_agreement"] == agreement


def test_rubric_has_three_worked_seed_examples():
    text = RUBRIC.read_text(encoding="utf-8")
    assert text.count("### Example") == 3
    for program in ("BOIDENT1", "LATEFEE1", "CLOSPEN5"):
        assert program in text


def test_cli_judge_refuses_missing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = main(
        [
            "benchmark-judge",
            "--input",
            str(INSTANCES),
            "--out",
            str(tmp_path / "unused.jsonl"),
            "--sample",
            "50",
            "--model",
            "gpt-test-judge",
            "--model-family",
            "openai",
        ]
    )
    assert result != 0
    assert "OPENAI_API_KEY" in capsys.readouterr().err
