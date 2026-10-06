"""Revised review chains remain additive, blind, source-pinned and fail closed."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location(
        "revision_request_builder", ROOT / "scripts/prepare_r2_revision_reviews.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def write(out, name, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def repository(tmp_path):
    builder = module()
    root = tmp_path / "repo"
    out = root / "data/migration/ai-review"
    shutil.copytree(
        ROOT / "data/migration/ai-review",
        out,
        ignore=shutil.ignore_patterns("revisions"),
    )
    inventory = json.loads((out / "runtime-source-inventory.json").read_bytes())
    for name in set(inventory) | set(builder.REVISION_SCRIPTS):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    protocol = builder.AIReviewProtocol.model_validate_json(
        (out / "review-protocol.json").read_bytes()
    )
    originals = {
        builder.AICaseSpec.model_validate_json(builder.read_pin(out, p)).case_id: p
        for p in protocol.case_inputs
    }
    pins = []
    for case_id in builder.CASE_IDS:
        case = json.loads(builder.read_pin(out, originals[case_id]))
        case["duplicate_source_justification"] += " Revised bounded proposal."
        revised_fixtures = []
        for old in case["fixture_evidence"]:
            name = f"revisions/inputs/{case_id}/{Path(old['path']).name}"
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(builder.read_pin(out, old))
            revised_fixtures.append(builder.pin_file(out, name).model_dump())
        case["fixture_evidence"] = revised_fixtures
        pins.append(write(out, f"revisions/inputs/{case_id}/case-input.json", case))
    write(
        out,
        "revisions/input-preparation.json",
        {
            "case_inputs": pins,
            "candidate_count": 4,
            "hidden_metadata_supplied": False,
            "generation_authorized": False,
        },
    )
    return builder, root, out, originals


def test_revision_protocol_blind_and_original_bytes_unchanged(repository):
    builder, root, out, originals = repository
    before = {
        p.relative_to(out).as_posix(): p.read_bytes()
        for p in out.rglob("*")
        if p.is_file() and "revisions" not in p.relative_to(out).parts
    }
    protocol = builder.prepare(root, frozen_at="2026-10-07T00:00:00Z")
    assert len(protocol.case_inputs) == 4
    assert (
        protocol.runtime_source_sha256
        == builder.pin_file(out, "revisions/runtime-source-inventory.json").sha256
    )
    inventory = json.loads(
        (out / "revisions/runtime-source-inventory.json").read_bytes()
    )
    assert "scripts/wsl_migration_backend.py" in inventory
    assert (
        inventory["scripts/wsl_migration_backend.py"]
        == hashlib.sha256(
            (root / "scripts/wsl_migration_backend.py").read_bytes()
        ).hexdigest()
    )
    for case_pin in protocol.case_inputs:
        spec = builder.AICaseSpec.model_validate_json(builder.read_pin(out, case_pin))
        old = builder.AICaseSpec.model_validate_json(
            builder.read_pin(out, originals[spec.case_id])
        )
        assert spec.source_evidence == old.source_evidence
        assert spec.regulation_evidence == old.regulation_evidence
        for role in builder.ROLES[:2]:
            name = f"revisions/requests/{spec.case_id}/{role}"
            request = builder.AIReviewRequest.model_validate_json(
                (out / name / "request.json").read_bytes()
            )
            assert request.protocol.path == "revisions/review-protocol.json"
            assert not request.prior_responses
            packet = json.loads((out / name / "prompt.json").read_bytes())
            assert "prior_responses" not in packet
            assert "revision-history" not in json.dumps(packet)
            for other in set(builder.CASE_IDS) - {spec.case_id}:
                assert other not in json.dumps(packet)
    assert all((out / name).read_bytes() == raw for name, raw in before.items())
    assert builder.prepare(root) == protocol


@pytest.mark.parametrize("field", ["source_evidence", "regulation_evidence"])
def test_changed_source_or_regulation_pin_rejected(repository, field):
    builder, _root, out, originals = repository
    prep = json.loads((out / "revisions/input-preparation.json").read_bytes())
    pin = prep["case_inputs"][0]
    body = json.loads(builder.read_pin(out, pin))
    if field == "source_evidence":
        body[field][0]["path"] = "inputs/other-source.cbl"
    else:
        body[field]["path"] = "inputs/other-regulation.json"
    prep["case_inputs"][0] = write(out, pin["path"], body)
    write(out, "revisions/input-preparation.json", prep)
    with pytest.raises(ValueError, match="source/regulation/identity"):
        builder.verified_inputs(out, originals)


def test_old_runtime_change_rejected_before_freeze(repository):
    builder, root, out, _originals = repository
    name = next(iter(json.loads((out / "runtime-source-inventory.json").read_bytes())))
    (root / name).write_text("changed frozen source\n")
    with pytest.raises(ValueError, match="runtime"):
        builder.prepare(root, frozen_at="2026-10-07T00:00:00Z")
    assert not (out / "revisions/review-protocol.json").exists()


def test_original_terminal_receipt_required(repository):
    builder, root, out, _originals = repository
    body = json.loads((out / "original-review-receipt.json").read_bytes())
    body["reviews"].pop()
    write(out, "original-review-receipt.json", body)
    with pytest.raises(ValueError, match="36 terminal"):
        builder.prepare(root, frozen_at="2026-10-07T00:00:00Z")


def test_adjudicator_requires_new_sealed_independent_captures(repository):
    builder, root, out, _originals = repository
    builder.prepare(root, frozen_at="2026-10-07T00:00:00Z")
    case_id = builder.CASE_IDS[0]
    with pytest.raises(ValueError, match="both sealed independent revision"):
        builder.adjudicator(case_id, root=root)
    old_captures = [
        builder.pin_file(out, f"reviews/{case_id}/{role}/capture.json")
        for role in builder.ROLES[:2]
    ]
    with pytest.raises(ValueError, match="protocol differs"):
        builder.adjudicator(case_id, root=root, captures=old_captures)


def test_adjudicator_binds_both_new_finals(repository):
    builder, root, out, _originals = repository
    builder.prepare(root, frozen_at="2026-10-07T00:00:00Z")
    helper_spec = importlib.util.spec_from_file_location(
        "request_test_helper", ROOT / "tests/test_r2_review_requests.py"
    )
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    case_id = builder.CASE_IDS[0]
    captures = []
    finals = []
    for role in builder.ROLES[:2]:
        name = f"revisions/requests/{case_id}/{role}"
        request = builder.AIReviewRequest.model_validate_json(
            (out / name / "request.json").read_bytes()
        )
        pins = helper.capture(
            builder, out, request, name, "2026-10-07T01:00:00Z", "2026-10-07T02:00:00Z"
        )
        captures.append(pins[0])
        finals.append(builder.MigrationEvidencePin.model_validate(pins[2]))
    request = builder.adjudicator(
        case_id, root=root, captures=captures, materialized_at="2026-10-07T03:00:00Z"
    )
    assert request.prior_responses == tuple(finals)
    packet = json.loads(builder.read_pin(out, request.prompt))
    assert [row["pin"] for row in packet["prior_responses"]] == [
        p.model_dump() for p in finals
    ]
