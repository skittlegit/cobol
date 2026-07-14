"""T2.3 gates for the deterministic benchmark-build orchestrator and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.build import build_benchmark, manifest_path_for
from cobol_archaeologist.benchmark.surface import ProbeRow, surface_probe_report
from cobol_archaeologist.cli import main
from cobol_archaeologist.schemas import DriftInstance


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "benchmark" / "drift_instances.jsonl"


EXPECTED_CLASSES = {
    "D1_stale_threshold",
    "D2_missing_rule",
    "D3_contradictory",
    "D4_stale_reference_data",
    "D5_boundary_error",
    "D6_dead_code",
    "D7_conformant",
}


@pytest.fixture(scope="module")
def built_pair(tmp_path_factory):
    root = tmp_path_factory.mktemp("t23-build")
    left = root / "left" / "drift_instances.jsonl"
    right = root / "right" / "drift_instances.jsonl"
    first = build_benchmark(seed=2306, out_path=left, min_instances=200)
    second = build_benchmark(seed=2306, out_path=right, min_instances=200)
    return first, second, left, right


def test_gate_a_same_seed_is_byte_identical(built_pair):
    _, _, left, right = built_pair
    assert left.read_bytes() == right.read_bytes()
    assert manifest_path_for(left).read_bytes() == manifest_path_for(right).read_bytes()


def test_gate_b_scale_schema_and_class_coverage(built_pair):
    first, _, output, _ = built_pair
    instances = [
        DriftInstance.model_validate_json(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(instances) >= 200
    assert len({instance.instance_id for instance in instances}) == len(instances)
    assert {instance.drift_type for instance in instances} == EXPECTED_CLASSES
    assert all(
        DriftInstance.model_validate_json(instance.model_dump_json()) == instance
        for instance in instances
    )
    assert all(
        "diversify=deterministic" in (instance.provenance.mutation or "")
        for instance in instances
    )
    assert first.manifest["instance_count"] == len(instances)


def test_gate_c_manifest_accounts_for_floors_rejects_and_validation(built_pair):
    first, _, output, _ = built_pair
    manifest = json.loads(manifest_path_for(output).read_text(encoding="utf-8"))
    assert manifest == first.manifest
    assert manifest["seed"] == 2306
    assert manifest["git_sha"]
    assert manifest["diversify"] == "deterministic"
    assert sum(manifest["operator_counts"].values()) == manifest["instance_count"]
    assert sum(manifest["base_counts"].values()) == manifest["instance_count"]
    assert (
        sum(manifest["validation_level_counts"].values()) == manifest["instance_count"]
    )
    assert isinstance(manifest["rejects_by_reason"], dict)
    assert set(manifest["class_counts"]) == EXPECTED_CLASSES
    for drift_class, floor in manifest["class_floors"].items():
        actual = manifest["class_counts"][drift_class]
        assert manifest["shortfalls"][drift_class] == max(0, floor - actual)


def test_gate_d_interprocedural_floor_or_documented_shortfall(built_pair):
    first, _, _, _ = built_pair
    manifest = first.manifest
    actual = manifest["interprocedural_count"]
    assert actual >= 30 or manifest["shortfalls"]["interprocedural"] == 30 - actual
    assert manifest["shortfalls"]["interprocedural"] == max(0, 30 - actual)


def test_gate_e_surface_probe_sample_is_at_chance(built_pair):
    first, _, _, _ = built_pair
    rows = [ProbeRow(**row) for row in first.probe_rows]
    assert len(rows) == 200
    assert {row.label for row in rows} == {0, 1}
    report = surface_probe_report(rows, seed=2306, bootstrap_samples=400)
    assert report.ci_low <= 0.5 <= report.ci_high, report
    assert first.manifest["surface_probe"] == {
        "auc": report.auc,
        "ci_low": report.ci_low,
        "ci_high": report.ci_high,
        "samples": 200,
    }


def test_cli_llm_mode_refuses_without_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = main(
        [
            "benchmark-build",
            "--seed",
            "1",
            "--out",
            str(tmp_path / "unused.jsonl"),
            "--diversify",
            "llm",
        ]
    )
    assert result != 0
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_cli_rejects_nonpositive_minimum(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "benchmark-build",
                "--seed",
                "1",
                "--out",
                str(tmp_path / "unused.jsonl"),
                "--min-instances",
                "0",
            ]
        )


def test_checked_in_synthetic_v1_matches_its_manifest():
    instances = [
        DriftInstance.model_validate_json(line)
        for line in ARTIFACT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(manifest_path_for(ARTIFACT).read_text(encoding="utf-8"))
    assert len(instances) == manifest["instance_count"] >= 200
    assert manifest["validation_level_counts"] == {"compiled": len(instances)}
    assert manifest["shortfalls"] == {
        "D1_stale_threshold": 0,
        "D2_missing_rule": 0,
        "D3_contradictory": 0,
        "D4_stale_reference_data": 0,
        "D5_boundary_error": 0,
        "D6_dead_code": 0,
        "D7_conformant": 0,
        "interprocedural": 0,
        "minimum_instances": 0,
    }
