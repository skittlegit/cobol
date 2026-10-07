"""Seal stage generation and separate qualification from actual host bytes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from cobol_archaeologist.migration.ai_review import model_sha256
from cobol_archaeologist.migration.contracts import MigrationEvidencePin

try:
    from scripts.stage_successor import (
        PROPOSAL_ADAPTER,
        SYSTEM_PROMPT,
        SuccessorMigrationRequest,
        build_successor_prompt,
        capture_successor_final,
        successor_run_key,
        validate_configuration4_binding,
    )
except ModuleNotFoundError:
    from stage_successor import (
        PROPOSAL_ADAPTER,
        SYSTEM_PROMPT,
        SuccessorMigrationRequest,
        build_successor_prompt,
        capture_successor_final,
        successor_run_key,
        validate_configuration4_binding,
    )


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inside(root: Path, path: Path) -> Path:
    path = path.absolute()
    if root not in path.resolve().parents:
        raise ValueError("generation evidence path escapes root")
    if any(
        parent.is_symlink()
        for parent in (path, *path.parents)
        if root in parent.parents
    ):
        raise ValueError("symlink generation evidence is forbidden")
    return path.resolve()


def pin(root: Path, path: Path, raw: bytes) -> MigrationEvidencePin:
    return MigrationEvidencePin(
        path=inside(root, path).relative_to(root).as_posix(), sha256=digest(raw)
    )


def immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace immutable capture: {path}")


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("host timestamps must be timezone aware")
    return parsed


def content_text(payload: dict) -> str:
    parts = payload.get("content", [])
    if not parts or any(
        part.get("type") not in {"input_text", "output_text"} for part in parts
    ):
        raise ValueError("encrypted launch or non-text content cannot be verified")
    if any(not isinstance(part.get("text"), str) for part in parts):
        raise ValueError("missing exact text content")
    return "".join(part["text"] for part in parts)


def read_pin(root: Path, value: dict) -> bytes:
    item = MigrationEvidencePin.model_validate(value)
    raw = inside(root, root / item.path).read_bytes()
    if digest(raw) != item.sha256:
        raise ValueError(f"frozen artifact checksum mismatch: {item.path}")
    return raw


def check_freeze(
    *, root: Path, freeze_path: Path, request_path: Path, launch_path: Path
) -> tuple[SuccessorMigrationRequest, dict, dict]:
    freeze = json.loads(inside(root, freeze_path).read_bytes())
    if freeze.get("schema_version") != "migration-stage-successor-runtime-manifest-v1":
        raise ValueError("unsupported generation runtime manifest")
    timestamp(freeze["frozen_at"])
    request_raw = request_path.read_bytes()
    request = SuccessorMigrationRequest.model_validate_json(request_raw)
    request_pin = pin(root, request_path, request_raw).model_dump(mode="json")
    matches = [entry for entry in freeze["requests"] if entry["request"] == request_pin]
    if len(matches) != 1:
        raise ValueError("request must match exactly one frozen generation entry")
    entry = matches[0]
    if entry.get("execution_purpose") != request.execution_purpose:
        raise ValueError("frozen request execution purpose differs")
    if entry["request_sha256"] != model_sha256(request) or entry[
        "run_key"
    ] != successor_run_key(request):
        raise ValueError("frozen request model/run identity differs")
    launch_raw = read_pin(root, entry["launch"])
    if (
        inside(root, root / entry["launch"]["path"]) != launch_path
        or launch_raw != launch_path.read_bytes()
    ):
        raise ValueError("launch differs from frozen generation entry")
    runtime = {item["path"]: item["sha256"] for item in freeze["runtime_sources"]}
    if len(runtime) != len(freeze["runtime_sources"]) or not runtime:
        raise ValueError("runtime inventory must be nonempty and unique")
    for item in freeze["runtime_sources"]:
        read_pin(root, item)
    archive_raw = read_pin(root, freeze["runtime_archive"])
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        if len(archive.namelist()) != len(runtime) or set(archive.namelist()) != set(
            runtime
        ):
            raise ValueError("runtime archive inventory differs")
        if any(digest(archive.read(path)) != value for path, value in runtime.items()):
            raise ValueError("runtime archive source checksum differs")
    runtime_hash = digest(
        json.dumps(runtime, sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        runtime_hash != freeze["runtime_source_sha256"]
        or runtime_hash != request.method.runtime_source_sha256
    ):
        raise ValueError("runtime source inventory identity differs")
    for name in ("runner", "validator", "backend", "validation_protocol"):
        method_pin = entry["method_pins"][name]
        read_pin(root, method_pin)
        if method_pin["sha256"] != getattr(request.method, f"{name}_sha256"):
            raise ValueError(f"{name} method identity differs")
        if (
            name != "validation_protocol"
            and runtime.get(method_pin["path"]) != method_pin["sha256"]
        ):
            raise ValueError(f"{name} is absent from frozen runtime inventory")
    validate_configuration4_binding(request.detector, evidence_root=root)
    staging_root = Path(entry["staging_root"])
    if not staging_root.is_absolute():
        staging_root = root / staging_root
    staging_root = inside(root, staging_root)
    prompt = json.loads(read_pin(root, entry["prompt"]))
    expected_prompt = {
        "system": SYSTEM_PROMPT,
        "user": build_successor_prompt(request),
        "staged_sources": [
            str(staging_root / source.path).replace("\\", "/")
            for source in request.case.frozen_sources
        ],
        "output_schema": PROPOSAL_ADAPTER.json_schema(),
    }
    if prompt != expected_prompt:
        raise ValueError("frozen prompt differs from authorized one-case packet")
    expected = {source.path: source.sha256 for source in request.case.frozen_sources}
    observed = {}
    for source in staging_root.rglob("*"):
        if source.is_symlink():
            raise ValueError("symlink staging input is forbidden")
        if source.is_file():
            checked = inside(root, source)
            observed[checked.relative_to(staging_root).as_posix()] = digest(
                checked.read_bytes()
            )
    if observed != expected:
        raise ValueError("staged source inventory differs from frozen case")
    source_pins = entry["source_pins"]
    if source_pins != [
        {
            "path": (staging_root / source.path).relative_to(root).as_posix(),
            "sha256": source.sha256,
        }
        for source in request.case.frozen_sources
    ]:
        raise ValueError("staging source pins differ from frozen case")
    for item in source_pins:
        read_pin(root, item)
    return request, freeze, entry


def seal_session(
    *,
    root: Path,
    request_path: Path,
    session_path: Path,
    launch_path: Path,
    launch_receipt_path: Path,
    freeze_path: Path,
    task_id: str,
    output_dir: Path,
) -> dict:
    root = root.resolve()
    output_dir = inside(root, output_dir)
    raw = session_path.read_bytes()
    transcript_path = output_dir / "raw-session.jsonl"
    # DECISION: preserve every attempted final and transcript before preflight;
    # malformed or misbound attempts are durable rejections, never repaired patches.
    immutable(transcript_path, raw)
    try:
        rows = [
            json.loads(line)
            for line in raw.decode("utf-8").splitlines()
            if line.strip()
        ]
        finals = [
            row
            for row in rows
            if row.get("type") == "response_item"
            and row.get("payload", {}).get("phase") == "final_answer"
            and row["payload"].get("role") == "assistant"
        ]
        if len(finals) != 1:
            raise ValueError("session must contain exactly one final_answer")
        final_raw = content_text(finals[0]["payload"]).encode("utf-8")
        final_path = output_dir / "exact-final.json"
        immutable(final_path, final_raw)
        request_path, launch_path = (
            inside(root, request_path),
            inside(root, launch_path),
        )
        request, freeze, entry = check_freeze(
            root=root,
            freeze_path=freeze_path,
            request_path=request_path,
            launch_path=launch_path,
        )
        request_raw, launch_raw = request_path.read_bytes(), launch_path.read_bytes()
        metas = [row for row in rows if row.get("type") == "session_meta"]
        if len(metas) != 1 or rows[0] != metas[0]:
            raise ValueError("session must start with unique host metadata")
        meta = metas[0]["payload"]
        actual_task = meta["source"]["subagent"]["thread_spawn"]["agent_path"]
        if (
            actual_task != task_id
            or not isinstance(meta.get("id"), str)
            or not meta["id"]
        ):
            raise ValueError("host task/session identity differs")
        contexts = [row["payload"] for row in rows if row.get("type") == "turn_context"]
        if not contexts or any(
            context.get("model") != request.provider.model
            or context.get("effort") != request.provider.reasoning_effort
            for context in contexts
        ):
            raise ValueError(
                "host model or reasoning differs from frozen generation identity"
            )
        started = timestamp(meta.get("timestamp", metas[0]["timestamp"]))
        completed = timestamp(finals[0]["timestamp"])
        frozen_at = timestamp(freeze["frozen_at"])
        if not frozen_at < started < completed:
            raise ValueError("host timing differs from generation freeze")
        launches = []
        for row in rows:
            if row.get("type") != "response_item":
                continue
            payload = row.get("payload", {})
            if payload.get("role") != "user" and payload.get("type") != "agent_message":
                continue
            parts = payload.get("content", [])
            if (
                payload.get("role") == "user"
                and len(parts) == 1
                and parts[0].get("text", "").startswith("<environment_context>")
                and parts[0].get("text", "").endswith("</environment_context>")
            ):
                continue
            launches.append(row)
        if len(launches) != 1:
            raise ValueError("session is not a fresh one-case context")
        launch_row = launches[0]
        if (
            launch_row["payload"].get("type") == "agent_message"
            and launch_row["payload"].get("recipient") != actual_task
        ):
            raise ValueError("launch recipient differs from host task")
        if rows.index(launch_row) > rows.index(finals[0]):
            raise ValueError("launch follows final")
        verification = "plaintext_transcript_exact_bytes"
        try:
            captured_launch = content_text(launch_row["payload"]).encode("utf-8")
        except ValueError:
            captured_launch = None
            verification = "host_launch_receipt_encrypted_transcript_payload"
        if captured_launch is not None and captured_launch != launch_raw:
            raise ValueError("initial launch differs from frozen launch bytes")
        receipt_path = inside(root, launch_receipt_path)
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        expected_receipt = {
            "schema_version": "migration-ai-host-launch-receipt-v1",
            "provenance": "root_host_captured_tool_invocation_and_return",
            "transport": "collaboration.spawn_agent",
            "fork_turns": "none",
            "task_id": task_id,
            "returned_task_name": actual_task,
            "request_sha256": model_sha256(request),
            "request_artifact_sha256": digest(request_raw),
            "launch_sha256": digest(launch_raw),
            "identity_limitations": "host_capture_not_external_identity_attestation",
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            raise ValueError("host launch receipt binding differs")
        launched = timestamp(receipt["launched_at"])
        if (
            not frozen_at < launched < completed
            or abs((launched - started).total_seconds()) > 60
        ):
            raise ValueError("host launch receipt timing differs")
        for existing in root.rglob("*.json"):
            if existing.resolve() == (output_dir / "capture.json").resolve():
                continue
            try:
                prior = json.loads(existing.read_bytes())
            except (ValueError, UnicodeError):
                continue
            if not isinstance(prior, dict) or prior.get("schema_version") not in {
                "migration-successor-capture-v1",
                "migration-stage-successor-capture-v1",
            }:
                continue
            if (
                prior["session_id"] == meta["id"]
                or prior["task_id"] == actual_task
                or prior["run_key"] == entry["run_key"]
            ):
                raise ValueError("reused generation task, session, or run identity")
        events = {
            "schema_version": "migration-stage-successor-host-session-events-v1",
            "provenance": "host_captured_collaboration_session",
            "execution_purpose": request.execution_purpose,
            "task_id": actual_task,
            "session_id": meta["id"],
            "provider": request.provider.model_dump(mode="json"),
            "request_sha256": model_sha256(request),
            "final_sha256": digest(final_raw),
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "raw_transcript": pin(root, transcript_path, raw).model_dump(mode="json"),
            "launch_receipt": pin(root, receipt_path, receipt_raw).model_dump(
                mode="json"
            ),
        }
        event_path = output_dir / "generation-host-events.json"
        event_raw = json_bytes(events)
        capture = capture_successor_final(
            request,
            final_raw,
            task_id=actual_task,
            session_id=meta["id"],
            started_at=started,
            completed_at=completed,
            host_events=pin(root, event_path, event_raw),
            raw_transcript=pin(root, transcript_path, raw),
        )
        result = {
            "schema_version": "migration-stage-successor-seal-receipt-v1",
            "status": "SEALED",
            "execution_purpose": request.execution_purpose,
            "run_key": capture.run_key,
            "case_id": capture.case_id,
            "task_id": capture.task_id,
            "session_id": capture.session_id,
            "proposal_kind": capture.proposal.kind,
            "provider_usage": "not_recorded",
            "request": pin(root, request_path, request_raw).model_dump(mode="json"),
            "freeze": pin(
                root, inside(root, freeze_path), freeze_path.read_bytes()
            ).model_dump(mode="json"),
            "exact_final": pin(root, final_path, final_raw).model_dump(mode="json"),
            "launch": pin(root, launch_path, launch_raw).model_dump(mode="json"),
            "launch_receipt": pin(root, receipt_path, receipt_raw).model_dump(
                mode="json"
            ),
            "launch_verification": verification,
            "identity_limitations": capture.identity_limitations,
        }
        immutable(event_path, event_raw)
        immutable(
            output_dir / "capture.json", json_bytes(capture.model_dump(mode="json"))
        )
        immutable(output_dir / "seal-receipt.json", json_bytes(result))
        return result
    except (ValueError, KeyError, TypeError, OSError) as exc:
        immutable(
            output_dir / "rejection.json",
            json_bytes(
                {
                    "status": "REJECTED",
                    "error": str(exc),
                    "raw_transcript_sha256": digest(raw),
                }
            ),
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "root",
        "request",
        "session",
        "launch",
        "launch-receipt",
        "freeze",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    result = seal_session(
        root=args.root,
        request_path=args.request,
        session_path=args.session,
        launch_path=args.launch,
        launch_receipt_path=args.launch_receipt,
        freeze_path=args.freeze,
        task_id=args.task,
        output_dir=args.output,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
