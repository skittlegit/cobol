"""Provider-free, fail-closed R1.7 decision and migration intake binding.

This separate reporting adapter does not mutate the frozen evaluator runtime or
represent configuration 4 as the older configuration-3 migration contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("data/eval/m4")
LINEAGE = OUTPUT / "gpt6-luna-repeat"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(root: Path, relative: str | Path) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def pin(root: Path, relative: str | Path) -> dict:
    return {"path": str(relative).replace("\\", "/"), "sha256": digest(root / relative)}


def verify_pins(root: Path, pins: list[dict]) -> None:
    for item in pins:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("evidence path escapes repository")
        if digest(path) != item["sha256"]:
            raise ValueError(f"evidence hash mismatch: {item['path']}")


def derive_status(*, host_valid: bool, signed_references_valid: bool,
                  quality_gates: dict[str, bool]) -> str:
    if not quality_gates or any(type(value) is not bool for value in quality_gates.values()):
        raise ValueError("quality gates must be a nonempty boolean mapping")
    if not host_valid or not signed_references_valid:
        return "NOT_EVALUABLE"
    return "GO" if all(quality_gates.values()) else "NO_GO"


def immutable_write(root: Path, relative: str | Path, value: dict) -> dict:
    path = root / relative
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if path.exists() and path.read_bytes() != payload:
        raise ValueError(f"refusing to replace frozen {relative}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    marker = path.with_suffix(path.suffix + ".sha256")
    marker.write_bytes((hashlib.sha256(payload).hexdigest() + "\n").encode())
    return pin(root, relative)


def freeze(root: Path, quality_gates: dict[str, bool]) -> dict:
    report = read(root, OUTPUT / "report.json")
    required = {"t1_f1", "balanced_accuracy", "answer_rate", "answered_accuracy",
                "interprocedural_advantage", "temporal_paired_accuracy", "verified_evidence"}
    if set(quality_gates) != required or quality_gates != report["quality_gates"]:
        raise ValueError("quality gates differ from canonical report")
    evidence = read(root, OUTPUT / "report-evidence-manifest.json")
    verify_pins(root, [{"path": name, "sha256": sha} for name, sha in evidence["inputs"].items()])
    verify_pins(root, [{"path": (OUTPUT / name).as_posix(), "sha256": sha}
                       for name, sha in evidence["outputs"].items()])
    terminal_path = LINEAGE / "diagnostics/r1.6-terminal-receipt.json"
    terminal = read(root, terminal_path)
    verify_pins(root, [
        {"path": (LINEAGE / name).as_posix(), "sha256": sha}
        for name, sha in terminal["file_sha256"].items()
    ])
    run_freeze = read(root, LINEAGE / "run-freeze.json")
    if terminal["pending_official_keys"] != 0:
        raise ValueError("official evaluation has pending keys")
    if terminal["sealed_full_run_tasks"] != 610 or terminal["sealed_temporal_sides"] != 40:
        raise ValueError("incomplete frozen coverage")
    for system in run_freeze["systems"]:
        path = root / LINEAGE / "full" / system / f"{system}.jsonl"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if [record["instance_id"] for record in records] != run_freeze["test_order"]:
            raise ValueError(f"canonical order mismatch: {system}")
    mismatches = terminal["signed_reference_discrepancies"]
    refs_valid = mismatches["full_entries"] == 0 and mismatches["temporal_entries"] == 0
    status = derive_status(host_valid=terminal["host_status"] == "VALID",
                           signed_references_valid=refs_valid, quality_gates=quality_gates)
    decision = {
        "schema_version": "configuration-4-detector-decision-v1",
        "configuration": 4,
        "model_id": run_freeze["model_id"],
        "reasoning_effort": run_freeze["reasoning_effort"],
        "status": status,
        "comparison_scope": terminal["comparison_scope"],
        "host_replay_status": terminal["host_status"],
        "release_provenance_valid": refs_valid,
        "signed_reference_discrepancies": mismatches,
        "quality_gates": quality_gates,
        "quality_gates_all_pass": all(quality_gates.values()),
        "quality_interpretation": "Measured quality failures remain descriptive evidence; provenance failure prevents an evaluable release conclusion.",
        "decision_rule": "NOT_EVALUABLE if host validity or required signed-reference provenance fails; otherwise GO only if all frozen quality gates pass, else NO_GO.",
        "provenance_rule_basis": "T8.1 requires exact source/tool identity; STATUS fail-closes promotion and migration on required hashes. Signed-reference mismatches fail that provenance requirement even when host replay is VALID.",
        "method_changes": False,
        "completed_results_rerun": False,
        "provider_calls": 0,
        "inputs": [pin(root, path) for path in [
            terminal_path, LINEAGE / "run-freeze.json", OUTPUT / "report.json",
            OUTPUT / "report-evidence-manifest.json", "docs/tasks/T8.1-work-order.md",
            "scripts/freeze_r1_7.py",
        ]],
    }
    decision_pin = immutable_write(root, OUTPUT / "detector-decision.json", decision)
    candidate_path = "data/migration/candidate-manifest.json"
    candidates = read(root, candidate_path)
    for name, item in candidates["files"].items():
        verify_pins(root, [{"path": f"data/migration/{name}", "sha256": item["sha256"]}])
    intake = {
        "schema_version": "r2-detector-input-roster-v1",
        "state": "FROZEN_INTAKE_R2_1_NOT_STARTED",
        "decision": decision_pin,
        "configuration": 4,
        "detector_led": {"active": status == "GO", "eligible_findings": [], "count": 0},
        "oracle_assisted": {
            "candidate_count": candidates["case_count"],
            "candidate_ids": [json.loads(line)["case_id"] for line in
                              (root / "data/migration/candidate-roster.jsonl").read_text(encoding="utf-8").splitlines()],
            "generation_authorized": False,
            "remaining_gate": "R2.1 must validate/promote exact reviewed migration cases and source/runtime bindings; candidates are not generation requests.",
        },
        "candidate_manifest": pin(root, candidate_path),
        "candidate_files": [pin(root, f"data/migration/{name}") for name in candidates["files"]],
        "temporal_review_manifest": pin(root, "data/benchmark/t6-v2/final/manifest.json"),
        "provider_calls": 0,
        "migration_contract": "Configuration-4 intake adapter; never relabel this decision as configuration 3. Existing configuration-3 live APIs cannot consume it directly.",
        "next_section": "R2.1_WHEN_REQUESTED",
    }
    if status == "GO":
        raise ValueError("GO requires a verified finding roster; empty findings cannot be frozen")
    intake_pin = immutable_write(root, OUTPUT / "r2-input-roster.json", intake)
    manifest = {
        "schema_version": "canonical-detector-evaluation-manifest-v1",
        "canonical_root": OUTPUT.as_posix(),
        "evidence_store": LINEAGE.as_posix(),
        "storage_policy": "Unversioned canonical reports and decision bind the immutable model cohort. Frozen evidence paths remain unchanged because signed requests and receipts embed them.",
        "decision": decision_pin,
        "r2_input_roster": intake_pin,
        "artifacts": [pin(root, OUTPUT / name) for name in [
            "report.json", "report.md", "performance-profile.json", "performance-profile.md",
            "report-evidence-manifest.json", "release-accounting.json", "compatibility-receipt.json",
        ]],
        "terminal_receipt": pin(root, terminal_path),
        "completed_results_rerun": False,
    }
    immutable_write(root, OUTPUT / "evaluation-manifest.json", manifest)
    return decision


if __name__ == "__main__":
    report = read(ROOT, OUTPUT / "report.json")
    decision = freeze(ROOT, report["quality_gates"])
    print(json.dumps({"status": decision["status"], "provider_calls": 0}))
