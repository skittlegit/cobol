"""Replacement-input authoring preserves historical evidence and real semantics."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.migration.ai_review import AICaseSpec
from cobol_archaeologist.migration.backend import FixtureProtocol

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "revision_authoring", ROOT / "scripts/prepare_r2_review_revisions.py"
)
author = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(author)


@pytest.fixture
def workspace(tmp_path):
    # Read-only source fixture; all authoring occurs in a disposable tree.
    out = tmp_path / "data/migration/ai-review"
    out.mkdir(parents=True)
    source = ROOT / "data/migration/ai-review"
    for name in ("input-preparation.json", "candidate-manifest.json"):
        shutil.copyfile(source / name, out / name)
    shutil.copyfile(
        ROOT / "data/migration/candidate-manifest.json",
        tmp_path / "data/migration/candidate-manifest.json",
    )
    for case in author.CASES:
        shutil.copytree(source / "inputs" / case, out / "inputs" / case)
        shutil.copytree(source / "reviews" / case, out / "reviews" / case)
    # input preparation pins all twelve cases even though just four are revised.
    for case in (source / "inputs").iterdir():
        if case.is_dir() and not (out / "inputs" / case.name).exists():
            shutil.copytree(case, out / "inputs" / case.name)
    baseline = tmp_path / author.BASELINE
    baseline.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / author.BASELINE, baseline)
    return tmp_path


def inventory(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def load(out, case, name="case-input.json", revised=True):
    folder = "revisions/inputs" if revised else "inputs"
    return json.loads((out / folder / case / name).read_bytes())


def prepare_revision(workspace, *, finalize=True):
    """Simulate a baseline receipt in disposable tests, never production evidence."""
    author.prepare(workspace, fixtures_only=True)
    out = workspace / "data/migration/ai-review"
    rows = []
    for case in author.CASES:
        observations = []
        protocol = load(out, case, "fixtures.json")
        for check_id, fixtures in protocol["checks"].items():
            observations.append(
                {
                    "check_id": check_id,
                    "status": "fail",
                    "log": json.dumps(
                        {
                            "fixtures": [
                                {
                                    "fixture_id": f["fixture_id"],
                                    "actual_stdout": "TEST SIMULATION\n",
                                    "expected_stdout": f["expected_stdout"],
                                    "run_result": {
                                        "compiled_ok": True,
                                        "exit_code": 0,
                                        "timed_out": False,
                                        "stdout": "TEST SIMULATION\r\n",
                                    },
                                }
                                for f in fixtures
                            ]
                        }
                    ),
                }
            )
        rows.append(
            {
                "case_id": case,
                "observations": observations,
                "frozen_sources": protocol["frozen_sources"],
                "fixture_protocol_sha256": FixtureProtocol.model_validate(
                    protocol
                ).sha256,
            }
        )
    baseline = workspace / "simulated-baseline.json"
    baseline.write_bytes(author.encoded({"cases": rows}))
    return author.prepare(workspace, baseline_path=baseline) if finalize else baseline


def test_revision_preserves_original_bytes_source_pins_and_candidate_order(workspace):
    before = inventory(workspace)
    result = prepare_revision(workspace)
    for name, raw in before.items():
        assert (workspace / name).read_bytes() == raw
    out = workspace / "data/migration/ai-review"
    prep = json.loads(author.read_pin(out, result))
    assert prep["case_ids"] == list(author.CASES)
    assert prep["candidate_count"] == 4
    assert prep["generation_authorized"] is False
    for case, evidence in zip(author.CASES, prep["case_inputs"], strict=True):
        new = json.loads(author.read_pin(out, evidence))
        old = load(out, case, revised=False)
        AICaseSpec.model_validate(new)
        for field in (
            "instance_id",
            "drift_type",
            "stratum",
            "frozen_sources",
            "source_evidence",
            "regulation_evidence",
            "source_bundle_group",
            "primary_program",
            "affected_hosts",
            "validation_capability",
        ):
            assert new[field] == old[field]
        for pin in [
            *new["source_evidence"],
            new["regulation_evidence"],
            *new["fixture_evidence"],
        ]:
            author.read_pin(out, pin)
        assert not any("reviews/" in p["path"] for p in new["fixture_evidence"])
        assert "independence of model errors" in new["duplicate_source_justification"]
        assert "all reviewers approve" not in new["duplicate_source_justification"]
    after = inventory(workspace)
    prepare_revision(workspace)
    assert inventory(workspace) == after


def test_exact_baseline_logs_are_bound_without_promoting_outcomes(workspace):
    prepare_revision(workspace)
    out = workspace / "data/migration/ai-review"
    raw = (workspace / author.BASELINE).read_bytes()
    originals = {c["case_id"]: c for c in json.loads(raw)["cases"]}
    assert (
        out / "revisions/original-case-baseline-qualification.json"
    ).read_bytes() == raw
    for case in author.CASES:
        observation = load(out, case, "original-observations.json")
        assert observation["qualification"]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert observation["case"] == originals[case]
        assert "not been executed" in observation["limitations"]
        history = load(out, case, "revision-history.json")
        assert len(history["original_review_findings"]) == 3
        for evidence in history["original_review_findings"]:
            author.read_pin(out, evidence)
        fixtures = load(out, case, "fixtures.json")
        FixtureProtocol.model_validate(fixtures)
        authored = out / "revisions/inputs" / case / "fixture-authoring.json"
        assert (
            fixtures["fixture_authoring_evidence_sha256"]
            == hashlib.sha256(authored.read_bytes()).hexdigest()
        )


def test_cutoff_scope_and_changed_boundaries_are_not_regressions(workspace):
    prepare_revision(workspace)
    out = workspace / "data/migration/ai-review"
    for case in author.CASES[:2]:
        spec = load(out, case)
        assert spec["allowed_source_scope"] == [
            {"path": "WSCUTOFF.cpy", "line_spans": [[4, 4]]}
        ]
        checks = load(out, case, "fixtures.json")["checks"]
        intended = {f["fixture_id"]: f for f in checks["intended-regulatory-behavior"]}
        assert intended["above-cap-consent"]["expected_stdout"] == "CONSENT \n"
        assert all(
            f["fixture_id"] != "above-cap-consent"
            for f in checks["class-specific-regression"]
        )
        all_tests = {f["fixture_id"]: f for group in checks.values() for f in group}
        for prefix, values in (
            ("percent", ("999-99", "1000-00", "1000-01")),
            ("cap", ("4999-99", "5000-00", "5000-01")),
        ):
            for value in values:
                assert f"{prefix}-{value}" in all_tests
        assert all_tests["percent-1000-00"]["expected_stdout"] == "ADJUST  \n"
        assert all_tests["cap-5000-01"]["expected_stdout"] == "CONSENT \n"
        assert all_tests["crossover-499999-5000-00"]["expected_stdout"] == "CONSENT \n"
        assert all_tests["crossover-500000-5000-00"]["expected_stdout"] == "ADJUST  \n"
        assert all_tests["crossover-500001-5000-00"]["expected_stdout"] == "ADJUST  \n"
        assert all_tests["above-old-cap"]["expected_stdout"] == "CONSENT \n"
        old_checks = load(out, case, "fixtures.json", revised=False)["checks"]
        for group in old_checks.values():
            for original in group:
                assert all_tests[original["fixture_id"]] == original


def test_blank_and_nearest_capital_boundaries(workspace):
    prepare_revision(workspace)
    out = workspace / "data/migration/ai-review"
    ovd = load(out, "migration_191889", "fixtures.json")["checks"]
    blank = next(
        f
        for f in ovd["intended-regulatory-behavior"]
        if f["fixture_id"] == "blank-document-rejected"
    )
    assert blank["initialize"] == ["MOVE SPACES TO WS-OVD-CODE"]
    assert blank["expected_stdout"] == "REJECT\n"
    assert (
        "unmodeled" in load(out, "migration_191889")["intended_behavior"]["description"]
    )
    capital = load(out, "migration_345332", "fixtures.json")["checks"]
    assert capital["intended-regulatory-behavior"][0]["expected_stdout"] == "N\n"
    nearest = {f["fixture_id"]: f for f in capital["unaffected-outside-locus"]}
    assert nearest["capital-9-99"]["expected_stdout"] == "N\n"
    assert nearest["capital-10-01"]["expected_stdout"] == "Y\n"
    baseline = load(out, "migration_345332", "original-observations.json")["case"]
    observed = next(
        o
        for o in baseline["observations"]
        if o["check_id"] == "intended-regulatory-behavior"
    )
    assert json.loads(observed["log"])["fixtures"][0]["actual_stdout"] == "Y\n"


def test_tampering_fails_before_authoring_and_revisions_are_immutable(workspace):
    out = workspace / "data/migration/ai-review"
    original = out / "inputs/migration_075075/sources/WSCUTOFF.cpy"
    raw = original.read_bytes()
    original.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="checksum"):
        prepare_revision(workspace)
    assert not (out / "revisions").exists()
    original.write_bytes(raw)
    prepare_revision(workspace)
    target = out / "revisions/inputs/migration_075075/fixtures.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="immutable"):
        prepare_revision(workspace)


def test_final_input_waits_for_complete_source_bound_real_execution(workspace):
    out = workspace / "data/migration/ai-review"
    author.prepare(workspace, fixtures_only=True)
    assert not (out / "revisions/inputs/migration_075075/case-input.json").exists()
    with pytest.raises(ValueError, match="executed revised-fixture baseline"):
        author.prepare(workspace)
    checks = {case: load(out, case, "fixtures.json") for case in author.CASES}
    rows = [
        {
            "case_id": case,
            "frozen_sources": fixtures["frozen_sources"],
            "fixture_protocol_sha256": FixtureProtocol.model_validate(fixtures).sha256,
            "observations": [],
        }
        for case, fixtures in checks.items()
    ]
    with pytest.raises(ValueError, match="omits a concrete fixture"):
        author.verified_revised_baseline(author.encoded({"cases": rows}), checks)
    rows[0]["frozen_sources"] = []
    with pytest.raises(ValueError, match="original frozen sources"):
        author.verified_revised_baseline(author.encoded({"cases": rows}), checks)


def wsl_simulation(workspace):
    baseline_path = prepare_revision(workspace, finalize=False)
    baseline = json.loads(baseline_path.read_bytes())
    baseline["execution_environment"] = "linux-wsl"
    script = workspace / "scripts/wsl_migration_backend.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(b"# disposable test identity, never execution evidence\n")
    runtime = {
        "path": "scripts/wsl_migration_backend.py",
        "sha256": author.sha(script.read_bytes()),
    }
    capability = {
        "schema_version": "migration-r2-qualified-wsl-capabilities-v1",
        "execution_environment": "linux-wsl",
        "backend_script": runtime,
        "cases": [],
    }
    for index, row in enumerate(baseline["cases"]):
        backend = {
            "schema_version": "migration-wsl-backend-capability-v1",
            "execution_environment": "linux-wsl",
            "windows_execution_claim": False,
            "compiler_error": None,
            "backend_source_sha256": runtime["sha256"],
            "fixture_protocol_sha256": row["fixture_protocol_sha256"],
            "backend_identity_sha256": str(index + 1) * 64,
            "wsl_binary_sha256": "a" * 64,
            "runner_sha256": "b" * 64,
            "bootstrap_sha256": "c" * 64,
            "case_checks_executed": False,
            "compiler": {
                "platform": "linux-wsl",
                "binary": "/usr/bin/cobc",
                "binary_sha256": "d" * 64,
                "native_binary_sha256": "d" * 64,
                "banner": "TEST SIMULATION",
                "version": "TEST SIMULATION",
            },
        }
        row["backend"] = backend
        for observation in row["observations"]:
            log = json.loads(observation["log"])
            log["backend_identity_sha256"] = backend["backend_identity_sha256"]
            log["fixture_protocol_sha256"] = backend["fixture_protocol_sha256"]
            observation["log"] = json.dumps(log)
        capability["cases"].append({"case_id": row["case_id"], "backend": backend})
    baseline_path.write_bytes(author.encoded(baseline))
    capability_path = workspace / "simulated-capability.json"
    capability_path.write_bytes(author.encoded(capability))
    return baseline_path, capability_path


def test_wsl_requires_qualified_identity_and_exposes_only_case_receipt(workspace):
    baseline_path, capability_path = wsl_simulation(workspace)
    with pytest.raises(ValueError, match="qualified capability evidence"):
        author.prepare(workspace, baseline_path=baseline_path)
    author.prepare(
        workspace, baseline_path=baseline_path, capability_path=capability_path
    )
    out = workspace / "data/migration/ai-review"
    for case in author.CASES:
        spec = load(out, case)
        receipt = load(out, case, "qualified-capability.json")
        assert receipt["case_id"] == case
        assert receipt["backend"]["execution_environment"] == "linux-wsl"
        assert "cases" not in receipt
        assert any(
            p["path"].endswith("qualified-capability.json")
            for p in spec["fixture_evidence"]
        )
        author.read_pin(out, receipt["qualification"])
    assert (
        out / "revisions/qualified-wsl-capabilities.json"
    ).read_bytes() == capability_path.read_bytes()


@pytest.mark.parametrize(
    "defect", ["compiler", "runtime", "check_identity", "qualification"]
)
def test_wsl_identity_tampering_fails_before_final_inputs(workspace, defect):
    baseline_path, capability_path = wsl_simulation(workspace)
    baseline = json.loads(baseline_path.read_bytes())
    capability = json.loads(capability_path.read_bytes())
    if defect == "compiler":
        capability["cases"][0]["backend"]["compiler"]["binary_sha256"] = "0" * 64
    elif defect == "runtime":
        capability["backend_script"]["sha256"] = "0" * 64
    elif defect == "qualification":
        capability["qualification_artifact"] = {
            "path": "missing.json",
            "sha256": "0" * 64,
        }
    else:
        log = json.loads(baseline["cases"][0]["observations"][0]["log"])
        log["backend_identity_sha256"] = "0" * 64
        baseline["cases"][0]["observations"][0]["log"] = json.dumps(log)
    baseline_path.write_bytes(author.encoded(baseline))
    capability_path.write_bytes(author.encoded(capability))
    with pytest.raises((ValueError, FileNotFoundError)):
        author.prepare(
            workspace, baseline_path=baseline_path, capability_path=capability_path
        )
    out = workspace / "data/migration/ai-review"
    assert not (out / "revisions/inputs/migration_075075/case-input.json").exists()
