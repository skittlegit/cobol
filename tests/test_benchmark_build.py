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
    first = build_benchmark(seed=2601, out_path=left, min_instances=200)
    second = build_benchmark(seed=2601, out_path=right, min_instances=200)
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
    assert manifest["seed"] == 2601
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


def test_corrective_manifest_has_complete_operator_and_judge_gates(built_pair):
    first, _, _, _ = built_pair
    manifest = first.manifest

    assert manifest["diversify_mode"] == "deterministic"
    assert manifest["judge_family"] == "openai"
    assert manifest["class_shortfalls"] == {
        drift_class: 0 for drift_class in sorted(EXPECTED_CLASSES)
    }
    assert manifest["operator_floors"] == {
        "MO-1×": 12,
        "MO-3": 15,
        "MO-3×": 12,
        "MO-6×": 12,
    }
    assert manifest["operator_shortfalls"] == {
        operator: 0 for operator in manifest["operator_floors"]
    }
    for operator, floor in manifest["operator_floors"].items():
        assert manifest["operator_counts"][operator] >= floor


def test_corrective_build_wires_every_authored_program_group(built_pair):
    first, _, _, _ = built_pair
    train_bases = {
        "ACTIVAT1.cbl",
        "BOIDENT3.cbl",
        "CICREP1.cbl",
        "CLOSPEN6.cbl",
        "GRVAGE2.cbl",
        "INTCOMP1.cbl",
        "KYCSCHED2.cbl",
        "KYCSYNC3.cbl",
        "LATEFEE2.cbl",
        "NOTICE1.cbl",
        "REFADJ1.cbl",
        "UNSOLIC1.cbl",
    }
    expected = {
        *train_bases,
        "REFADJ2.cbl",
        "BATCHCT2.cbl",
        "TRNVAL1.cbl",
    }
    assert expected <= set(first.manifest["base_counts"])
    assert first.manifest["corrective_base_floor"] == 32
    assert first.manifest["corrective_base_shortfalls"] == {
        name: 0 for name in sorted(train_bases)
    }
    assert all(first.manifest["base_counts"][name] >= 32 for name in train_bases)


def test_gate_d_interprocedural_floor_or_documented_shortfall(built_pair):
    first, _, _, _ = built_pair
    manifest = first.manifest
    actual = manifest["interprocedural_count"]
    assert actual >= 30 or manifest["shortfalls"]["interprocedural"] == 30 - actual
    assert manifest["shortfalls"]["interprocedural"] == max(0, 30 - actual)


def test_scale_mutations_use_plausible_legacy_shapes(built_pair):
    first, _, output, _ = built_pair
    instances = [
        DriftInstance.model_validate_json(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    d2 = next(
        item
        for item in instances
        if item.drift_type == "D2_missing_rule"
        and item.provenance.base_program == "KYCSYNC2.cbl"
    )
    d2_source = first.sources[d2.instance_id].text
    assert "2000-SET-SYNC-STATUS" in d2_source
    assert "MOVE 'PENDING' TO WS-SYNC-STATUS" in d2_source
    assert "IF WS-CUST-ID NOT = SPACES" in d2_source
    assert "MOVE 'READY' TO WS-SYNC-STATUS" in d2_source
    assert "IF WS-DAYS-SINCE-UPD = ZERO" in d2_source
    assert "IF WS-DAYS-SINCE-UPD > 7" not in d2_source
    assert "new='(deleted)'" in (d2.provenance.mutation or "")

    d3 = next(
        item
        for item in instances
        if item.drift_type == "D3_contradictory"
        and not item.code_locus.is_interprocedural
        and item.provenance.base_program == "LATEFEE1.cbl"
    )
    d3_source = first.sources[d3.instance_id].text
    assert "IF WS-DAYS-PAST-DUE > 3" in d3_source
    assert "OR WS-OUTSTANDING-AMT > ZERO" in d3_source
    assert "IF WS-DAYS-PAST-DUE <= 3" not in d3_source

    d3x = next(
        item
        for item in instances
        if item.drift_type == "D3_contradictory"
        and item.code_locus.is_interprocedural
        and item.provenance.base_program == "OVRLIM1.cbl"
    )
    d3x_source = first.sources[d3x.instance_id].text
    assert "MOVE 'N' TO WS-CONSENT-ON-FILE" not in d3x_source
    assert "PERFORM 1500-LOAD-CONSENT" in d3x_source
    assert "IF WS-CONSENT-REC-FOUND = 'Y'" in d3x_source
    assert "IF WS-PROJECTED-BAL > WS-CREDIT-LIMIT" in d3x_source
    assert "IF WS-CONSENT-ON-FILE NOT = 'Y'" in d3x_source
    assert "old=\"MOVE 'N' TO WS-CONSENT-ON-FILE\"" in (d3x.provenance.mutation or "")
    assert "new='(deleted)'" in (d3x.provenance.mutation or "")

    d4 = next(
        item for item in instances if item.drift_type == "D4_stale_reference_data"
    )
    assert "old='D'" in (d4.provenance.mutation or "")
    assert "new='W'" in (d4.provenance.mutation or "")

    d6 = next(
        item
        for item in instances
        if item.drift_type == "D6_dead_code"
        and item.provenance.base_program == "CLOSPEN5.cbl"
    )
    d6_source = first.sources[d6.instance_id].text
    assert "PROGRAM-ID. CLOSPEN5" in d6_source
    assert "WS-PEN-ENABLED        PIC X(1) VALUE 'N'." in d6_source
    assert "IF PENALTY-ON" in d6_source
    assert "COMPUTE WS-PENALTY-AMT = 500 * WS-DELAY-DAYS" in d6_source
    assert "WS-COMPLIANCE-FLAG" not in d6_source
    assert "old=\"VALUE 'Y'\"" in (d6.provenance.mutation or "")
    assert "new=\"VALUE 'N'\"" in (d6.provenance.mutation or "")
    assert len(d6.code_locus.loci) == 2


def test_gate_e_surface_probe_sample_is_at_chance(built_pair):
    first, _, _, _ = built_pair
    rows = [ProbeRow(**row) for row in first.probe_rows]
    assert len(rows) == 200
    assert {row.label for row in rows} == {0, 1}
    report = surface_probe_report(rows, seed=2601, bootstrap_samples=400)
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
