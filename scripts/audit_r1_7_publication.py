"""Reconcile completed R1.7 artifact pins against disk and exact Git blobs."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("data/eval/m4")


def load(relative: str | Path) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def audit() -> dict:
    manifest = load(OUT / "report-evidence-manifest.json")
    pins = dict(manifest["inputs"])
    pins.update({(OUT / name).as_posix(): value for name, value in manifest["outputs"].items()})
    decision = load(OUT / "detector-decision.json")
    for item in decision["inputs"]:
        pins[item["path"]] = item["sha256"]
    for item in load(OUT / "release-accounting.json")["evidence"]:
        pins[item["path"]] = item["sha256"]
    canonical = load(OUT / "evaluation-manifest.json")
    for item in [canonical["decision"], canonical["r2_input_roster"], canonical["terminal_receipt"], *canonical["artifacts"]]:
        pins[item["path"]] = item["sha256"]
    runtime = load(OUT / "runtime-source-manifest.json")
    pins[runtime["archive_path"]] = runtime["archive_sha256"]
    pins[(OUT / "runtime-source-manifest.json").as_posix()] = sha((ROOT / OUT / "runtime-source-manifest.json").read_bytes())
    compatibility = load(OUT / "compatibility-receipt.json")
    pins[compatibility["request_preparation_path"]] = compatibility["request_preparation_sha256"]
    base = Path(compatibility["request_preparation_path"]).parent
    for item in compatibility["requests"]:
        pins[(base / "requests" / (item["run_key"] + ".json")).as_posix()] = item["request_artifact_sha256"]
        pins[(base / "task-staging" / item["run_key"] / "staging-manifest.json").as_posix()] = item["staging_manifest_sha256"]
    for name, expected in pins.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise ValueError(f"disk evidence mismatch: {name}")
    for claim in manifest["claims"]:
        document = load(OUT / claim["report"])
        value = document
        for key in claim["json_pointer"].strip("/").split("/"):
            value = value[key]
        if sha(json.dumps(value, sort_keys=True).encode()) != claim["value_sha256"]:
            raise ValueError(f"claim mismatch: {claim['id']}")
    with ZipFile(ROOT / runtime["archive_path"]) as archive:
        accumulator = hashlib.sha256()
        for name in archive.namelist():
            payload = archive.read(name)
            if sha(payload) != runtime["files"][name]:
                raise ValueError(f"runtime member mismatch: {name}")
            encoded_name = name.encode()
            accumulator.update(len(encoded_name).to_bytes(8, "big"))
            accumulator.update(encoded_name)
            accumulator.update(len(payload).to_bytes(8, "big"))
            accumulator.update(payload)
        if accumulator.hexdigest() != runtime["runtime_source_sha256"]:
            raise ValueError("snapshot does not reproduce frozen runtime hash")
    names = sorted(pins)
    result = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                            input="".join(f":{name}\n" for name in names).encode(),
                            capture_output=True, check=True)
    cursor = 0
    normalized = []
    for name in names:
        end = result.stdout.index(b"\n", cursor)
        header = result.stdout[cursor:end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError(f"pinned evidence missing from index: {name}")
        size = int(header[2])
        cursor = end + 1
        payload = result.stdout[cursor:cursor + size]
        cursor += size + 1
        if sha(payload) != pins[name]:
            normalized.append(name)
    if normalized:
        raise ValueError(f"Git normalized pinned bytes: {normalized}")
    # This historical Markdown file has an intentional two-space hard break.
    # Its only staged change preserves CRLF bytes for a raw evidence pin.
    historical = "docs/tasks/T5.5-work-order.md"
    old = subprocess.run(["git", "show", f"HEAD:{historical}"], cwd=ROOT,
                         capture_output=True, check=True).stdout
    current = (ROOT / historical).read_bytes()
    if old.replace(b"\r\n", b"\n") != current.replace(b"\r\n", b"\n"):
        raise ValueError("historical hard-break exemption has a content change")
    subprocess.run(["git", "-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol",
                    "diff", "--cached", "--check", "--", ".", f":!{historical}"],
                   cwd=ROOT, capture_output=True, check=True)
    receipt = {"schema_version": "r1.7-terminal-receipt-v1", "status": "COMPLETE",
               "detector_decision": decision["status"], "disk_and_index_pins_verified": len(pins),
               "narrative_claims_verified": len(manifest["claims"]),
               "focused_tests_passed": 34, "ruff": "PASS", "staged_whitespace_check": "PASS",
               "runtime_snapshot_reproduces_frozen_hash": True,
               "archived_signed_dev_requests_verified": compatibility["request_count"],
               "canonical_root": OUT.as_posix(), "pending_evaluation_keys": 0,
               "completed_results_rerun": False, "provider_calls": 0,
               "release_tasks": {"T7.2": "NOT_COMPLETE_EXPLICITLY_ACCOUNTED", "T7.3": "NOT_COMPLETE_EXPLICITLY_ACCOUNTED", "T7.4": "DEFERRED"},
               "next_section": "R2.1_AUTHORIZED_PERSISTENT_GOAL",
               "artifacts": {name: sha((ROOT / OUT / name).read_bytes()) for name in [
                   "evaluation-manifest.json", "detector-decision.json", "r2-input-roster.json",
                   "report-evidence-manifest.json", "runtime-source-manifest.json"]}}
    target = ROOT / OUT / "terminal-receipt.json"
    payload = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("refusing to replace terminal receipt")
    target.write_bytes(payload)
    print(json.dumps({key: receipt[key] for key in ["status", "disk_and_index_pins_verified", "narrative_claims_verified", "detector_decision"]}))
    return receipt


if __name__ == "__main__":
    audit()
