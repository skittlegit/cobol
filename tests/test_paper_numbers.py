"""The anonymous paper must reject changed numbers and stale source bindings."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "paper_builder", ROOT / "scripts/build_paper.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def paper_root(tmp_path):
    for path in [
        *builder.SOURCES.values(),
        "paper/manuscript.template.md",
        "paper/references.json",
    ]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    return tmp_path


def test_every_numeric_cell_roundtrips_and_build_is_deterministic(paper_root):
    first = builder.build(paper_root)
    assert first == builder.build(paper_root)
    assert first == builder.build(paper_root, check=True)
    mapping = json.loads((paper_root / "paper/claim-map.json").read_bytes())
    assert mapping["state"] == "DRAFT_SUBMISSION_GATES_PENDING"
    for claim in mapping["claims"].values():
        document = json.loads((paper_root / claim["source"]).read_bytes())
        assert builder.resolve(document, claim["json_pointer"]) == claim["value"]
    assert any(
        c["json_pointer"].startswith("/metrics/attacker_with_bases/")
        for c in mapping["claims"].values()
    )
    assert all(
        c["source_sha256"] == mapping["source_hashes"][c["source"]]
        for c in mapping["claims"].values()
    )


@pytest.mark.parametrize(
    "name",
    [
        "manuscript.md",
        "manuscript.html",
        "numbers.md",
        "numbers.html",
        "claim-map.json",
    ],
)
def test_hand_edit_fails_audit(paper_root, name):
    builder.build(paper_root)
    path = paper_root / "paper" / name
    path.write_bytes(path.read_bytes() + b"\n42\n")
    with pytest.raises(ValueError, match="hand-edited"):
        builder.build(paper_root, check=True)


def test_changed_measurement_fails_audit(paper_root):
    builder.build(paper_root)
    path = paper_root / builder.SOURCES["m5"]
    report = json.loads(path.read_bytes())
    report["headline_result"]["agent_f1"] = 0.9
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="Stale"):
        builder.build(paper_root, check=True)


def test_private_path_and_priority_claim_rejected(paper_root):
    path = paper_root / "paper/manuscript.template.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nC:/Users/private/work\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="private path"):
        builder.build(paper_root)


def test_priority_claim_rejected(paper_root):
    path = paper_root / "paper/references.json"
    references = json.loads(path.read_bytes())
    references["novelty_claim"] = "first"
    path.write_text(json.dumps(references), encoding="utf-8")
    with pytest.raises(ValueError, match="priority"):
        builder.build(paper_root)


def test_manual_numeric_prose_rejected(paper_root):
    path = paper_root / "paper/manuscript.template.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nThe score was 0.99.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Unbound quantitative"):
        builder.build(paper_root)


def test_full_result_sections_are_included(paper_root):
    result = builder.outputs(paper_root)
    mapping = json.loads(result["claim-map.json"])
    pairs = {(c["source"], c["json_pointer"]) for c in mapping["claims"].values()}
    for source, sections in builder.SECTIONS.items():
        document = json.loads((paper_root / builder.SOURCES[source]).read_bytes())
        expected = {
            (builder.SOURCES[source], p)
            for section in sections
            for p, _ in builder.leaves(document[section], "/" + section)
        }
        assert expected <= pairs


def test_scalar_failure_counts_retained_and_private_failure_bodies_excluded(paper_root):
    mapping = json.loads(builder.outputs(paper_root)["claim-map.json"])
    matching = [c for c in mapping["claims"].values()
                if c["source"] == builder.SOURCES["m5"] and c["json_pointer"] == "/t6/failures"]
    assert len(matching) == 1 and matching[0]["value"] == 8
    assert list(builder.leaves({"failures": 8})) == [("/failures", 8)]
    assert list(builder.leaves({"failures": {"exit_code": 1, "private": "C:/Users/private/log"}})) == []
    assert list(builder.leaves({"failures": [1, {"exit_code": 2}]})) == []


def binding_fixture(
    root, deployment_status="PASS", container="PASS", release_status="IDENTICAL"
):
    commit = "a" * 40
    benchmark_hash = builder.sha((root / builder.SOURCES["benchmark"]).read_bytes())
    source = root / "deploy/offline.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"# pinned deployment source\n")
    measured_path = root / "deploy/measured-receipt.json"
    measured_path.write_text(json.dumps({"status": "PASS", "container_execution": "PASS",
                                         "os_network_isolation": "verified"}), encoding="utf-8")
    measured_pin = {"path": "deploy/measured-receipt.json", "sha256": builder.sha(measured_path.read_bytes())}
    contents = {
        "migration_report": (
            "data/migration/report.json",
            {
                "schema_version": "migration-stage-report-v1",
                "status": "COMPLETE",
                "tracks": {
                    "oracle_assisted": {
                        "denominator": 4,
                        "evaluated": 4,
                        "outcomes": {"pass": 3, "fail": 1, "abstention": 0},
                    },
                    "detector_led": {
                        "status": "inactive",
                        "denominator": 0,
                        "eligible": 0,
                    },
                },
                "distinct_oracle_source_bundles": 3,
                "provider_usage": "not_recorded",
                "raw_validation_logs": {
                    "private": "C:/Users/private/output",
                    "exit_code": 0,
                },
            },
        ),
        "release_manifest": (
            "release/manifest.json",
            {
                "schema_version": "licensed-benchmark-release-v1",
                "profile": "successor",
                "git_commit": commit,
                "benchmark_manifest_sha256": benchmark_hash,
                "files": [{"path": "deploy/offline.py", "sha256": builder.sha(source.read_bytes())}],
            },
        ),
        "release_two_builds": (
            "release/two-builds.json",
            {
                "status": release_status,
                "git_commit": commit,
                "archive_sha256": "b" * 64,
                "second_archive_sha256": "b" * 64,
            },
        ),
        "release_unpacked_validation": (
            "release/unpacked-validation.json",
            {"status": "VALID", "git_commit": commit, "archive_sha256": "b" * 64},
        ),
        "deployment_receipt": (
            "deploy/receipt.json",
            {
                "status": deployment_status,
                "source_commit": commit,
                "measured_receipt": measured_pin,
                "container_execution": container,
                "os_network_isolation": "verified",
                "source_pins": [
                    {
                        "path": "deploy/offline.py",
                        "sha256": builder.sha(source.read_bytes()),
                    }
                ],
            },
        ),
    }
    binding = {
        "schema_version": "paper-finalization-binding-v1",
        "source_commit": commit,
        "benchmark_manifest": {
            "path": builder.SOURCES["benchmark"],
            "sha256": benchmark_hash,
        },
    }
    for name, (relative, content) in contents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding="utf-8")
        binding[name] = {"path": relative, "sha256": builder.sha(path.read_bytes())}
    path = root / "paper/finalization-binding.json"
    path.write_text(json.dumps(binding), encoding="utf-8")
    return path.relative_to(root)


def test_only_completed_gates_enable_submission(paper_root):
    binding = binding_fixture(paper_root)
    result = builder.build(paper_root, binding_path=binding)
    assert result["state"] == "SUBMISSION_READY"
    assert builder.build(paper_root, check=True, binding_path=binding) == result
    mapping = json.loads((paper_root / "paper/claim-map.json").read_bytes())
    assert mapping["gates_pending"] == []
    migration = [
        c
        for c in mapping["claims"].values()
        if c["source"] == "data/migration/report.json"
    ]
    assert any(
        c["json_pointer"] == "/tracks/detector_led/denominator" and c["value"] == 0
        for c in migration
    )
    assert not any("raw_validation_logs" in c["json_pointer"] for c in migration)
    assert (
        "The oracle-assisted track evaluated"
        in (paper_root / "paper/manuscript.md").read_text()
    )


@pytest.mark.parametrize(
    "deployment,container,release",
    [
        (
            "PASS_STANDALONE_CONTAINER_NOT_EXECUTED",
            "unavailable_Docker_daemon_not_running",
            "IDENTICAL",
        ),
        ("PASS", "PASS", "INCOMPLETE"),
        ("INCOMPLETE", "PASS", "IDENTICAL"),
    ],
)
def test_incomplete_gates_retain_draft(paper_root, deployment, container, release):
    binding = binding_fixture(paper_root, deployment, container, release)
    assert (
        builder.build(paper_root, binding_path=binding)["state"]
        == "DRAFT_SUBMISSION_GATES_PENDING"
    )
    assert "Anonymous draft" in (paper_root / "paper/manuscript.md").read_text()


def test_commit_and_stale_finalization_pins_rejected(paper_root):
    binding_path = binding_fixture(paper_root)
    path = paper_root / binding_path
    binding = json.loads(path.read_bytes())
    binding["source_commit"] = "c" * 40
    path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        builder.build(paper_root, binding_path=binding_path)
    binding["source_commit"] = "a" * 40
    path.write_text(json.dumps(binding), encoding="utf-8")
    report_path = paper_root / binding["migration_report"]["path"]
    report_path.write_bytes(report_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Stale finalization"):
        builder.build(paper_root, binding_path=binding_path)


def test_terminal_migration_never_alone_finalizes(paper_root):
    binding_fixture(paper_root)
    result = builder.build(paper_root)
    assert result["state"] == "DRAFT_SUBMISSION_GATES_PENDING"


@pytest.mark.parametrize(
    "artifact,field,value",
    [
        ("migration_report", "status", "INCOMPLETE"),
        ("deployment_receipt", "os_network_isolation", "not_verified"),
    ],
)
def test_partial_migration_and_unverified_isolation_stay_draft(
    paper_root, artifact, field, value
):
    binding_path = binding_fixture(paper_root)
    path = paper_root / binding_path
    binding = json.loads(path.read_bytes())
    receipt = paper_root / binding[artifact]["path"]
    content = json.loads(receipt.read_bytes())
    content[field] = value
    receipt.write_text(json.dumps(content), encoding="utf-8")
    binding[artifact]["sha256"] = builder.sha(receipt.read_bytes())
    path.write_text(json.dumps(binding), encoding="utf-8")
    assert (
        builder.build(paper_root, binding_path=binding_path)["state"]
        == "DRAFT_SUBMISSION_GATES_PENDING"
    )
