"""Run pinned real WSL checks for one exact stage generation capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cobol_archaeologist.migration.backend import FixtureProtocol
from cobol_archaeologist.migration.validate import MigrationValidation

try:
    from scripts import seal_r2_stage_generation_session as sealer
    from scripts.stage_successor import (
        SuccessorCapture,
        replay_successor_capture,
        validate_successor_migration,
    )
    from scripts.wsl_migration_backend import WSLValidationBackend
except ModuleNotFoundError:
    import seal_r2_stage_generation_session as sealer
    from stage_successor import (
        SuccessorCapture,
        replay_successor_capture,
        validate_successor_migration,
    )
    from wsl_migration_backend import WSLValidationBackend


def load_fixtures(case, evidence_root: Path) -> FixtureProtocol:
    candidates = []
    for item in case.fixture_evidence:
        raw = sealer.read_pin(evidence_root, {"path": item.path, "sha256": item.sha256})
        body = json.loads(raw)
        if body.get("schema_version") == "migration-execution-fixtures-v1":
            candidates.append(FixtureProtocol.model_validate(body))
    if len(candidates) != 1:
        raise ValueError("case must pin exactly one execution fixture protocol")
    fixture = candidates[0]
    if fixture.case_id != case.case_id or [
        s.model_dump(mode="json") for s in fixture.frozen_sources
    ] != [s.model_dump(mode="json") for s in case.frozen_sources]:
        raise ValueError("fixture case/source binding differs")
    return fixture


def read_terminal(path: Path, run_key: str, purpose: str):
    if not path.exists():
        return None
    body = json.loads(path.read_bytes())
    if body.get("run_key") != run_key:
        raise ValueError("terminal validation identity differs")
    if body.get("execution_purpose") != purpose:
        raise ValueError("terminal validation purpose differs")
    checksum = path.with_suffix(path.suffix + ".sha256")
    if not checksum.exists() or checksum.read_text(
        encoding="ascii"
    ).strip() != sealer.digest(path.read_bytes()):
        raise ValueError("terminal validation checksum differs or is missing")
    record = MigrationValidation.model_validate(body["validation"])
    if record.run_key != run_key:
        raise ValueError("terminal validation record identity differs")
    return body


def check_backend(case, evidence_root: Path, capability: dict):
    qualified = []
    for item in case.fixture_evidence:
        if Path(item.path).name == "qualified-capability.json":
            raw = sealer.read_pin(
                evidence_root, {"path": item.path, "sha256": item.sha256}
            )
            qualified.append(json.loads(raw)["backend"])
    if len(qualified) != 1 or qualified[0] != capability:
        raise ValueError("current qualified backend identity differs")
    return qualified[0]


def validate(*, root: Path, freeze_path: Path, capture_dir: Path, output_path: Path):
    root = root.resolve()
    capture_dir = sealer.inside(root, capture_dir)
    output_path = sealer.inside(root, output_path)
    receipt = json.loads((capture_dir / "seal-receipt.json").read_bytes())
    for name in ("request", "freeze", "exact_final", "launch", "launch_receipt"):
        sealer.read_pin(root, receipt[name])
    if sealer.inside(root, root / receipt["freeze"]["path"]) != freeze_path.resolve():
        raise ValueError("validation freeze differs from sealed capture")
    request_path = root / receipt["request"]["path"]
    launch_path = root / receipt["launch"]["path"]
    request, _, entry = sealer.check_freeze(
        root=root,
        freeze_path=freeze_path.resolve(),
        request_path=request_path,
        launch_path=launch_path,
    )
    capture = SuccessorCapture.model_validate_json(
        (capture_dir / "capture.json").read_bytes()
    )
    # DECISION: Reconcile authentic session bytes again before admitting a
    # validation attempt; this replay performs no provider or compiler call.
    sealer.seal_session(
        root=root,
        freeze_path=freeze_path.resolve(),
        request_path=request_path,
        session_path=root / capture.raw_transcript.path,
        launch_path=launch_path,
        task_id=capture.task_id,
        output_dir=capture_dir,
        launch_receipt_path=root / receipt["launch_receipt"]["path"],
    )
    replay_successor_capture(
        request,
        capture,
        exact_final=sealer.read_pin(root, receipt["exact_final"]),
        evidence_root=root,
    )
    fixture = load_fixtures(request.case, root / "data/migration/ai-review")
    capture_pin = sealer.pin(
        root, capture_dir / "capture.json", (capture_dir / "capture.json").read_bytes()
    ).model_dump(mode="json")
    terminal = read_terminal(output_path, capture.run_key, request.execution_purpose)
    if terminal is not None:
        if (
            terminal.get("request") != receipt["request"]
            or terminal.get("freeze") != receipt["freeze"]
            or terminal.get("capture") != capture_pin
        ):
            raise ValueError("terminal validation evidence bindings differ")
        check_backend(
            request.case, root / "data/migration/ai-review", terminal["backend"]
        )
        return terminal
    staging = Path(entry["staging_root"])
    if not staging.is_absolute():
        staging = root / staging
    files = {
        s.path: (staging / s.path).read_bytes().decode("utf-8")
        for s in request.case.frozen_sources
    }
    backend = WSLValidationBackend(fixture)
    capability = check_backend(
        request.case, root / "data/migration/ai-review", backend.capability_receipt()
    )
    record = validate_successor_migration(
        request, capture, base_files=files, backend=backend
    )
    result = {
        "schema_version": "migration-stage-validation-receipt-v1",
        "run_key": capture.run_key,
        "execution_purpose": request.execution_purpose,
        "validation": record.model_dump(mode="json"),
        "request": receipt["request"],
        "freeze": receipt["freeze"],
        "capture": capture_pin,
        "backend": capability,
        "mandatory_validation_obligations": list(
            request.mandatory_validation_obligations
        ),
        "scope_limitations_retained": request.case.model_dump(mode="json").get(
            "scope_limitations", []
        ),
        "post_patch_validation_obligations_retained": request.case.model_dump(
            mode="json"
        )["post_patch_validation_obligations"],
        "historical_evidence_qualifications_retained": request.case.model_dump(
            mode="json"
        )["historical_evidence_qualifications"],
        "reporting_limitations": list(request.case.reporting_limitations),
        "provider_usage": "not_recorded",
    }
    raw = sealer.json_bytes(result)
    sealer.immutable(output_path, raw)
    sealer.immutable(
        output_path.with_suffix(output_path.suffix + ".sha256"),
        (sealer.digest(raw) + "\n").encode("ascii"),
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "freeze", "capture", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(
                root=args.root,
                freeze_path=args.freeze,
                capture_dir=args.capture,
                output_path=args.output,
            ),
            sort_keys=True,
        )
    )
