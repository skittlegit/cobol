"""Provider-free gates for prospective, blind stage-review requests."""

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location(
        "prepare_r2_stage_reviews", ROOT / "scripts/prepare_r2_stage_reviews.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_historical_audit_covers_all_48_distinct_contexts():
    audit = builder().audit_history(ROOT, ROOT / "data/migration/ai-review")
    assert audit["capture_count"] == 48
    assert len(audit["task_ids"]) == len(audit["session_ids"]) == 48
    assert tuple(audit["case_ids"]) == builder().CASE_IDS


def test_blind_packet_keeps_every_inherited_issue_without_prior_judgments():
    b = builder()
    out = ROOT / "data/migration/ai-review"
    audit = b.audit_history(ROOT, out)
    for spec in audit["specs"]:
        inventory = b.inherited_packet(out, spec.case_id, audit["records"])
        prompt = b.packet(out, spec, "ai_primary", inventory)
        assert "prior_responses" not in prompt
        assert all("decision" not in issue for issue in prompt["inherited_issues"])
        assert all("rationale" not in issue for issue in prompt["inherited_issues"])
        assert "ai_primary" not in json.dumps(prompt["inherited_issues"])
        assert len(prompt["inherited_issues"]) == len(inventory.issues)
        assert [x["index"] for x in prompt["inherited_issues"]] == list(
            range(len(inventory.issues))
        )
        assert [x["text"] for x in prompt["inherited_issues"]] == [
            x.text for x in inventory.issues
        ]
        assert all(x["original_final_sha256"] for x in prompt["inherited_issues"])


def test_snapshot_is_exact_and_deterministic(tmp_path):
    b = builder()
    root = tmp_path / "repo"
    out = root / "out"
    root.mkdir()
    (root / "a.py").write_bytes(b"a=1\n")
    (root / "b.py").write_bytes(b"b=2\n")
    inventory = {
        x: hashlib.sha256((root / x).read_bytes()).hexdigest() for x in ("a.py", "b.py")
    }
    pin = b.save(out, "stage-review/runtime-source-inventory.json", inventory)
    manifest = b.snapshot(root, out, inventory, pin)
    before = (out / "stage-review/runtime-source.zip").read_bytes()
    assert b.snapshot(root, out, inventory, pin) == manifest
    assert (out / "stage-review/runtime-source.zip").read_bytes() == before
    with zipfile.ZipFile(out / "stage-review/runtime-source.zip") as bundle:
        assert bundle.namelist() == sorted(inventory)
        assert bundle.read("a.py") == b"a=1\n"
    (root / "a.py").write_bytes(b"a=2\n")
    with pytest.raises(ValueError, match="runtime"):
        b.snapshot(root, out, inventory, pin)


def test_authorization_is_required_before_freeze(tmp_path):
    with pytest.raises((ValueError, OSError)):
        builder().authorization(tmp_path, "stage-review/authorization.json")


@pytest.fixture
def stage_repository(tmp_path, monkeypatch):
    import shutil

    b = builder()
    actual = ROOT / "data/migration/ai-review"
    audit = b.audit_history(ROOT, actual)
    root = tmp_path / "repo"
    out = root / "data/migration/ai-review"
    shutil.copytree(actual, out, ignore=shutil.ignore_patterns("stage-review"))
    old = json.loads((actual / "revisions/runtime-source-inventory.json").read_bytes())
    for name in (*old, *b.STAGE_SCRIPTS):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, target)
        else:
            target.write_text("# prospective implementation fixture\n")
    proposal_name = "data/migration/coordination/proposed-stage-review-amendment.json"
    proposal = root / proposal_name
    proposal.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / proposal_name, proposal)
    b.save(
        out,
        b.AUTHORIZATION,
        {
            "authorized": True,
            "scope": "prospective_stage_aware_review",
            "proposal": {
                "path": proposal_name,
                "sha256": hashlib.sha256(proposal.read_bytes()).hexdigest(),
            },
        },
    )
    monkeypatch.setattr(b, "audit_history", lambda *args: audit)
    return b, root, out, audit


def test_temporary_freeze_is_prospective_additive_and_idempotent(stage_repository):
    from datetime import timedelta

    b, root, out, audit = stage_repository
    old_files = {
        p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file() and "stage-review" not in p.parts
    }
    protocol = b.prepare(
        root, frozen_at=(audit["completed_at"] + timedelta(seconds=1)).isoformat()
    )
    assert (
        protocol.acceptance_policy == "all_three_include_zero_pre_generation_blockers"
    )
    assert len(protocol.case_inputs) == len(protocol.inherited_issue_packets) == 4
    assert b.prepare(root) == protocol
    assert len(list((out / "stage-review/requests").glob("*/*/request.json"))) == 8
    assert not list(
        (out / "stage-review/requests").glob("*/ai_adjudicator/request.json")
    )
    inventory = json.loads(
        (out / "stage-review/runtime-source-inventory.json").read_bytes()
    )
    assert len(inventory) == 116
    assert set(inventory) == set(
        json.loads((out / "revisions/runtime-source-inventory.json").read_bytes())
    ) | set(b.STAGE_SCRIPTS)
    for pin in protocol.inherited_issue_packets:
        packet = b.contracts.StageInheritedIssuePacket.model_validate_json(
            b.read_pin(out, pin)
        )
        assert len(packet.historical_finals) == 6
        b.contracts.validate_issue_packet(packet, out)
    for name, digest in old_files.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    (root / b.STAGE_SCRIPTS[0]).write_text("# changed after stage freeze\n")
    with pytest.raises(ValueError, match="immutable"):
        b.prepare(root)


def test_freeze_rejects_old_runtime_change_and_premature_time(stage_repository):
    b, root, out, audit = stage_repository
    with pytest.raises(ValueError, match="follow all 48"):
        b.prepare(root, frozen_at=audit["completed_at"].isoformat())
    assert not (out / "stage-review/review-protocol.json").exists()
    old = json.loads((out / "revisions/runtime-source-inventory.json").read_bytes())
    (root / next(iter(old))).write_text("# changed old runtime\n")
    with pytest.raises(ValueError):
        b.prepare(root)
    assert not (out / "stage-review/review-protocol.json").exists()


def test_blind_request_rejects_prior_finals():
    b = builder()
    out = ROOT / "data/migration/ai-review"
    audit = b.audit_history(ROOT, out)
    spec = audit["specs"][0]
    inherited = b.inherited_packet(out, spec.case_id, audit["records"])
    with pytest.raises(ValueError, match="blind"):
        b.packet(out, spec, "ai_primary", inherited, inherited.historical_finals[:2])
    with pytest.raises(ValueError, match="exactly two"):
        b.packet(out, spec, "ai_adjudicator", inherited)


def test_freeze_must_follow_authorization(stage_repository):
    from datetime import timedelta

    b, root, out, audit = stage_repository
    moment = audit["completed_at"] + timedelta(seconds=1)
    path = out / b.AUTHORIZATION
    body = json.loads(path.read_bytes())
    body["authorized_at"] = (moment + timedelta(seconds=1)).isoformat()
    path.write_bytes(b.original.encoded(body))
    with pytest.raises(ValueError, match="prospectively follow authorization"):
        b.prepare(root, frozen_at=moment.isoformat())
    assert not (out / "stage-review/review-protocol.json").exists()
    body["authorized"] = False
    path.write_bytes(b.original.encoded(body))
    with pytest.raises(ValueError, match="authorization required"):
        b.prepare(root)
