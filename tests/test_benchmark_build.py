"""T2.3 gates for the deterministic benchmark-build orchestrator and CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.build import (
    _semantic_mutation_key,
    build_benchmark,
    manifest_path_for,
)
from cobol_archaeologist.benchmark.surface import (
    ProbeRow,
    per_feature_auc,
    surface_probe_report,
)
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


def test_distinct_mutation_key_ignores_replication_metadata():
    instance = next(
        DriftInstance.model_validate_json(line)
        for line in ARTIFACT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    mutation = instance.provenance.mutation or ""
    left = instance.model_copy(
        update={
            "provenance": instance.provenance.model_copy(
                update={
                    "mutation": (
                        f"{mutation}; validation=compiled; "
                        "diversify=deterministic; stale_source=grid"
                    )
                }
            )
        }
    )
    right = instance.model_copy(
        update={
            "provenance": instance.provenance.model_copy(
                update={
                    "mutation": (
                        f"{mutation}; validation=ast; "
                        "diversify=llm; stale_source=lineage"
                    )
                }
            )
        }
    )

    assert _semantic_mutation_key(left) == _semantic_mutation_key(right)
    assert _semantic_mutation_key(left) != _semantic_mutation_key(
        right.model_copy(
            update={
                "provenance": right.provenance.model_copy(
                    update={"base_program": "OTHER.cbl"}
                )
            }
        )
    )


def test_distinct_mutation_key_ignores_cobol_surface_form_but_not_literals():
    instance = next(
        DriftInstance.model_validate_json(line)
        for line in ARTIFACT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    def with_mutation(mutation: str) -> DriftInstance:
        return instance.model_copy(
            update={
                "provenance": instance.provenance.model_copy(
                    update={"mutation": mutation}
                )
            }
        )

    upper = with_mutation(
        "MO-2; locus=SYNC:2000-CHECK:20-22; "
        'old="IF WS-DAYS > 7 MOVE \'OK\' TO WS-STATUS"; '
        'new="IF WS-DAYS <= 7 MOVE \'OK\' TO WS-STATUS"; '
        "validation=compiled; diversify=deterministic"
    )
    restyled = with_mutation(
        "mo-2;  locus=sync:2000-check:20-22; "
        'old="if ws-days  >  7   move \'OK\' to ws-status"; '
        'new="if ws-days <= 7 move \'OK\' to ws-status"; '
        "validation=ast; diversify=llm"
    )
    changed_literal = with_mutation(
        "MO-2; locus=SYNC:2000-CHECK:20-22; "
        'old="IF WS-DAYS > 7 MOVE \'ok\' TO WS-STATUS"; '
        'new="IF WS-DAYS <= 7 MOVE \'ok\' TO WS-STATUS"'
    )

    assert _semantic_mutation_key(upper) == _semantic_mutation_key(restyled)
    assert _semantic_mutation_key(upper) != _semantic_mutation_key(changed_literal)


def test_distinct_mutation_key_parses_semicolons_and_double_quoted_cobol_literals():
    instance = next(
        DriftInstance.model_validate_json(line)
        for line in ARTIFACT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    def with_mutation(mutation: str) -> DriftInstance:
        return instance.model_copy(
            update={
                "provenance": instance.provenance.model_copy(
                    update={"mutation": mutation}
                )
            }
        )

    upper = with_mutation(
        "MO-2; locus=SYNC:2000-CHECK:20-20; "
        "old='DISPLAY \"OK;READY\"'; new='CONTINUE'; validation=compiled"
    )
    restyled = with_mutation(
        "mo-2; locus=sync:2000-check:20-20; "
        "old='display   \"OK;READY\"'; new='continue'; diversify=llm"
    )
    changed_literal = with_mutation(
        "MO-2; locus=SYNC:2000-CHECK:20-20; "
        "old='DISPLAY \"ok;ready\"'; new='CONTINUE'"
    )

    assert _semantic_mutation_key(upper) == _semantic_mutation_key(restyled)
    assert _semantic_mutation_key(upper) != _semantic_mutation_key(changed_literal)


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
    assert manifest["git_sha"] == subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert manifest["diversify"] == "deterministic"
    assert manifest["schema_version"] == 2
    assert manifest["compiler"]["supported_range"] == ">=3.1.2,<4"
    assert manifest["compiler"]["version_of_record"] == "3.2.0"
    assert manifest["compiler"]["provenance"] in {
        "observed_by_cobc_version",
        "unavailable",
    }
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
    drift_classes = EXPECTED_CLASSES - {"D7_conformant"}
    assert manifest["distinct_mutation_floors"] == {
        drift_class: 4 for drift_class in sorted(drift_classes)
    }
    assert manifest["distinct_mutation_shortfalls"] == {
        drift_class: 0 for drift_class in sorted(drift_classes)
    }
    for drift_class, floor in manifest["distinct_mutation_floors"].items():
        assert manifest["distinct_mutation_counts"][drift_class] >= floor


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


def test_purpose_authored_loci_are_rostered_and_emitted(built_pair):
    first, _, _, _ = built_pair
    purpose_bases = {
        "ACTRECON2.cbl",
        "CKYQUEUE2.cbl",
        "OVDROUT2.cbl",
        "SANCBAT2.cbl",
        "CLSRUN7.cbl",
        "INTROLL2.cbl",
        "CICROLL2.cbl",
    }
    roster = json.loads(
        (
            ROOT / "data" / "benchmark" / "seed" / "base_roster.json"
        ).read_text(encoding="utf-8")
    )

    assert {
        f"train-bases/{name}" for name in purpose_bases
    } <= roster["reservations"].keys()
    assert purpose_bases <= first.manifest["base_counts"].keys()
    assert all(first.manifest["base_counts"][name] > 0 for name in purpose_bases)

    # Purpose-level minima: the repaired classes must exercise the promised
    # number of independent base/locus pairs, not satisfy row floors by styling
    # replicas of a smaller semantic set.
    assert first.manifest["distinct_mutation_counts"]["D2_missing_rule"] >= 6
    assert first.manifest["distinct_mutation_counts"]["D4_stale_reference_data"] >= 4
    assert first.manifest["distinct_mutation_counts"]["D6_dead_code"] >= 6


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
    assert "IF WS-DAYS-PAST-DUE > ZERO" in d3_source
    assert "OR WS-OUTSTANDING-AMT > ZERO" not in d3_source
    assert "IF WS-DAYS-PAST-DUE <= 3" not in d3_source

    d3x = next(
        item
        for item in instances
        if item.drift_type == "D3_contradictory"
        and item.code_locus.is_interprocedural
        and item.provenance.base_program == "OVRLIM1.cbl"
    )
    d3x_source = first.sources[d3x.instance_id].text
    assert "MOVE 'N' TO WS-CONSENT-ON-FILE" in d3x_source
    assert "PERFORM 1500-LOAD-CONSENT" in d3x_source
    assert "IF WS-CONSENT-REC-FOUND = 'Y'" in d3x_source
    assert "IF WS-PROJECTED-BAL > WS-CREDIT-LIMIT" in d3x_source
    assert "IF WS-CONSENT-ON-FILE NOT = 'Y'" in d3x_source
    assert "OR WS-CREDIT-LIMIT = ZERO" in d3x_source
    assert "new='OR WS-CREDIT-LIMIT = ZERO'" in (d3x.provenance.mutation or "")

    # T2.4b / BL-6: D4 is anchored to authentic KYC reference-list hosts (OVD
    # accepted-document tables and UNSC mandated-list registries). MO-4 drops
    # one enumerated member so it drifts from the clause-side enum_set.
    d4_ovd = next(
        item
        for item in instances
        if item.drift_type == "D4_stale_reference_data"
        and item.provenance.base_program == "OVDCHK1.cbl"
    )
    assert "old='NPR'" in (d4_ovd.provenance.mutation or "")
    assert "new='(deleted)'" in (d4_ovd.provenance.mutation or "")
    assert d4_ovd.regulation_clause.clause_id == "5(xiv)"
    # gold_rationale carries the host-specific drift story (not a vague label)
    assert "in-clause enumeration" in d4_ovd.gold_rationale
    assert d4_ovd.provenance.annotator_notes
    d4_unsc = next(
        item
        for item in instances
        if item.drift_type == "D4_stale_reference_data"
        and item.provenance.base_program == "SCRNGATE1.cbl"
    )
    assert "old='S88'" in (d4_unsc.provenance.mutation or "")
    assert "new='(deleted)'" in (d4_unsc.provenance.mutation or "")
    assert d4_unsc.regulation_clause.clause_id == "56(prevention)"
    # UNSC is the deliberately weaker D4: registry completeness, not membership
    assert "registry completeness" in d4_unsc.gold_rationale
    assert d4_unsc.provenance.annotator_notes

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


def test_d4_reference_hosts_are_authentic_and_diverse():
    # T2.4b / BL-6: no cobc/tree-sitter needed -- pure catalog + guard checks.
    from dataclasses import replace

    from cobol_archaeologist.benchmark.build import (
        BuildConfigurationError,
        _assert_d4_reference_hosts,
        _candidate_catalog,
    )

    programs = ROOT / "data" / "benchmark" / "seed" / "programs"
    catalog = _candidate_catalog(ROOT)  # calls the guard; must not raise
    d4 = catalog["D4_stale_reference_data"]
    assert {c.base.filename for c in d4} == {
        "OVDCHK1.cbl",
        "SCRNGATE1.cbl",
        "OVDROUT2.cbl",
        "SANCBAT2.cbl",
    }
    assert all(c.op == "MO-4" for c in d4)
    for candidate in d4:
        cv = candidate.record.clause.current_value
        assert cv is not None and cv.kind == "enum_set" and len(cv.value) >= 2
        # each host must genuinely COPY its reference copybook (guard) ...
        assert candidate.base.files, candidate.base.filename
        assert "COPY" in candidate.base.text.upper()
        # ... and carry an honest, host-specific D4 drift story
        assert candidate.record.check.get("drift_story"), candidate.record.record_id
        # named-identity mnemonic sets drift by losing a mandated entry, not by
        # sprouting a generic substitute token (which the judge reads as artificial)
        assert candidate.record.check.get("d4_mode") == "member_removal", (
            candidate.record.record_id
        )

    # single host -> diversity guard
    with pytest.raises(BuildConfigurationError, match="distinct reference-list hosts"):
        _assert_d4_reference_hosts({"D4_stale_reference_data": [d4[0]]}, programs)

    # build-time-fabricated base text -> authenticity guard
    tampered = replace(d4[0], base=replace(d4[0].base, text=d4[0].base.text + "\n"))
    with pytest.raises(BuildConfigurationError, match="fabricated"):
        _assert_d4_reference_hosts(
            {"D4_stale_reference_data": [tampered, *d4[1:]]}, programs
        )


def test_gate_e_splits_artifact_only_gate_from_with_bases_floor(built_pair):
    first, _, _, _ = built_pair
    rows = [ProbeRow(**row) for row in first.probe_rows]
    assert len(rows) == 200
    assert {row.label for row in rows} == {0, 1}
    aggregate = surface_probe_report(rows, seed=2601, bootstrap_samples=400)
    artifact_only = surface_probe_report(
        rows,
        seed=2601,
        bootstrap_samples=400,
        feature_names=("literal_roundness",),
    )

    # CONTRACT v1.3 / BL-14: only artifact-computable literal roundness is a
    # hard build gate. The aggregate assumes access to bases and is recorded as
    # the mandatory T5.3 surface-baseline floor, not asserted at chance here.
    assert artifact_only.ci_low <= 0.5 <= artifact_only.ci_high, artifact_only
    assert first.manifest["surface_probe"] == {
        "auc": aggregate.auc,
        "ci_low": aggregate.ci_low,
        "ci_high": aggregate.ci_high,
        "samples": 200,
        "per_feature_auc": per_feature_auc(rows),
        "artifact_only_gate": {
            "feature": "literal_roundness",
            "auc": artifact_only.auc,
            "ci_low": artifact_only.ci_low,
            "ci_high": artifact_only.ci_high,
            "passed": True,
            "definition": "bootstrap 95% AUC CI includes 0.5 chance",
        },
        "aggregate_role": "mandatory_t5.3_attacker_with_bases_baseline_floor",
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
    assert manifest["schema_version"] == 2
    assert manifest["compiler"] == {
        "banner": None,
        "name": "GnuCOBOL cobc",
        "provenance": "legacy_version_not_recorded",
        "supported_range": ">=3.1.2,<4",
        "version": None,
        "version_of_record": "3.2.0",
    }
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


def test_bl8_checked_in_manifest_names_the_head_that_generated_it():
    manifest_path = manifest_path_for(ARTIFACT)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def catalogue_state(payload: dict) -> dict:
        """Judge stamps are evidence metadata, not catalogue generations."""

        return {key: value for key, value in payload.items() if key != "judging"}

    relative = manifest_path.relative_to(ROOT).as_posix()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    head_payload = json.loads(
        subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    )
    if catalogue_state(manifest) != catalogue_state(head_payload):
        # A freshly generated, not-yet-recorded manifest correctly names the
        # current HEAD. Requiring a future parent commit made the test fail in
        # the exact interval between generation and commit.
        assert manifest["git_sha"] == head
        return

    commits = subprocess.run(
        ["git", "log", "--format=%H", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    generation_commit = commits[0]
    for commit in commits[1:]:
        historical = json.loads(
            subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
        )
        if catalogue_state(historical) != catalogue_state(manifest):
            break
        generation_commit = commit
    parents = subprocess.run(
        ["git", "show", "-s", "--format=%P", generation_commit],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert manifest["git_sha"] in parents, (
        "checked-in manifest is a stale carry-forward: git_sha must name the "
        "HEAD at generation time (the parent of the commit that first recorded "
        "this catalogue state); later judge-only stamps do not change that state"
    )


def test_bl12_runnable_base_is_repo_native_and_rostered():
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    runnable = next(
        item for item in manifest["codebases"] if item["role"] == "runnable_base"
    )
    assert runnable["pinned_commit"] is None
    assert runnable["pin_status"] == "not_applicable_repo_native"
    assert runnable["location"] == "data/benchmark/seed/programs/**"
    assert runnable["roster"] == "data/benchmark/seed/base_roster.json"
    assert (ROOT / runnable["roster"]).is_file()
    assert (ROOT / "data/benchmark/seed/programs/OVRLIM1.cbl").is_file()
    assert "external upstream pin applies" in runnable["notes"]
