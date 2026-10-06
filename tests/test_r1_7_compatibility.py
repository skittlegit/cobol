"""Fail-closed checks for the archived signed-request compatibility receipt."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_r1_7_compatibility", ROOT / "scripts/audit_r1_7_compatibility.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.fixture
def archived_request(tmp_path):
    source = ROOT / audit.ARCHIVE
    target = tmp_path / audit.ARCHIVE
    preparation = json.loads((source / "request-preparation.json").read_text(encoding="utf-8"))
    row = preparation["request_order"][0]
    preparation["request_order"] = [row]
    preparation["task_count"] = 1
    (target / "requests").mkdir(parents=True)
    (target / "request-preparation.json").write_text(json.dumps(preparation), encoding="utf-8")
    key = row["run_key"]
    shutil.copyfile(source / "requests" / f"{key}.json", target / "requests" / f"{key}.json")
    shutil.copytree(source / "task-staging" / key, target / "task-staging" / key)
    return tmp_path, target, row


def test_archive_integrity_does_not_claim_live_original_path(archived_request):
    root, _, _ = archived_request
    receipt = audit.audit_archive(root, expected_count=1)
    assert receipt["exact_prompt_and_request_bytes_preserved"]
    assert not receipt["original_canonical_trial_present"]
    assert not receipt["archive_is_active_cli_alias"]
    assert receipt["provider_calls_performed"] == 0


def test_changed_prompt_bytes_fail_before_model_replay(archived_request):
    root, target, row = archived_request
    path = target / "requests" / f"{row['run_key']}.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="request artifact checksum"):
        audit.audit_archive(root, expected_count=1)


def test_changed_staged_source_fails_checksum(archived_request):
    root, target, row = archived_request
    stage = target / "task-staging" / row["run_key"]
    manifest = json.loads((stage / "staging-manifest.json").read_text(encoding="utf-8"))
    path = stage / manifest["files"][0]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="staging byte mismatch"):
        audit.audit_archive(root, expected_count=1)


def test_changed_manifest_pin_is_rejected(archived_request):
    root, target, _ = archived_request
    path = target / "request-preparation.json"
    preparation = json.loads(path.read_text(encoding="utf-8"))
    preparation["request_order"][0]["staging_manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(preparation), encoding="utf-8")
    with pytest.raises(ValueError, match="staging manifest checksum"):
        audit.audit_archive(root, expected_count=1)


def test_repinning_artifact_does_not_bypass_signed_request_model(archived_request):
    root, target, row = archived_request
    path = target / "requests" / f"{row['run_key']}.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    request["prompt"] += "changed signed prompt"
    path.write_text(json.dumps(request), encoding="utf-8")
    preparation_path = target / "request-preparation.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    preparation["request_order"][0]["request_artifact_sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")
    with pytest.raises(ValueError):
        audit.audit_archive(root, expected_count=1)
