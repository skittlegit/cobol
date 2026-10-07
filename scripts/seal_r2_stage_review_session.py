"""Seal fresh stage-aware reviews; preserve original v1 captures and rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from stage_review_contracts import (
    StageHostSessionEvents as AIHostSessionEvents,
)
from stage_review_contracts import (
    StageInheritedIssuePacket,
    response_schema_sha256,
    validate_issue_packet,
    validate_stage_response,
)
from stage_review_contracts import (
    StageReviewCapture as AIReviewCapture,
)
from stage_review_contracts import (
    StageReviewProtocol as AIReviewProtocol,
)
from stage_review_contracts import (
    StageReviewRequest as AIReviewRequest,
)
from stage_review_contracts import (
    StageReviewResponse as AIReviewResponse,
)

from cobol_archaeologist.migration.ai_review import (
    AICaseSpec,
    _pinned,
    model_sha256,
    validate_response_evidence,
)
from cobol_archaeologist.migration.ai_review import (
    AIHostSessionEvents as LegacyHostSessionEvents,
)
from cobol_archaeologist.migration.contracts import MigrationEvidencePin


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inside(root: Path, path: Path) -> Path:
    path = path.absolute()
    if root not in path.resolve().parents:
        raise ValueError("review evidence path escapes root")
    if any(p.is_symlink() for p in (path, *path.parents) if root in p.parents):
        raise ValueError("symlink review evidence is forbidden")
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
        p.get("type") not in {"input_text", "output_text"} for p in parts
    ):
        raise ValueError("encrypted launch or non-text content cannot be verified")
    if any(not isinstance(p.get("text"), str) for p in parts):
        raise ValueError("missing exact text content")
    return "".join(p["text"] for p in parts)


def seal_session(
    *,
    root: Path,
    request_path: Path,
    session_path: Path,
    launch_path: Path,
    task_id: str,
    output_dir: Path,
    launch_receipt_path: Path | None = None,
) -> dict:
    root = root.resolve()
    output_dir = inside(root, output_dir)
    request_path = inside(root, request_path)
    launch_path = inside(root, launch_path)
    request_raw, launch_raw = request_path.read_bytes(), launch_path.read_bytes()
    request = AIReviewRequest.model_validate_json(request_raw)
    protocol = AIReviewProtocol.model_validate_json(_pinned(root, request.protocol))
    spec = AICaseSpec.model_validate_json(_pinned(root, request.case_input))
    _pinned(root, request.prompt)
    _pinned(root, protocol.authorization_evidence)
    _pinned(root, protocol.candidate_manifest)
    if (
        request.reviewer not in protocol.reviewers
        or request.case_input not in protocol.case_inputs
        or request.case_id != spec.case_id
    ):
        raise ValueError("request differs from frozen protocol/case identity")
    if request.response_schema_sha256 != protocol.response_schema_sha256 or (
        protocol.response_schema_sha256 != response_schema_sha256()
    ):
        raise ValueError("response schema identity differs")
    authorization = json.loads(_pinned(root, protocol.authorization_evidence))
    if (
        authorization.get("authorized") is not True
        or authorization.get("scope") != "prospective_stage_aware_review"
    ):
        raise ValueError("stage-aware review lacks explicit prospective authorization")
    if request.inherited_issues not in protocol.inherited_issue_packets:
        raise ValueError("inherited issue packet differs from frozen protocol")
    issues = StageInheritedIssuePacket.model_validate_json(
        _pinned(root, request.inherited_issues)
    )
    validate_issue_packet(issues, root)
    if issues.case_id != spec.case_id:
        raise ValueError("inherited issue packet case differs")
    required = (*spec.source_evidence, spec.regulation_evidence, *spec.fixture_evidence)
    for evidence in (*required, *request.prior_responses):
        _pinned(root, evidence)
    raw = session_path.read_bytes()
    # DECISION: preserve the host JSONL bytes before parsing; invalid finals and
    # identity failures remain inspectable and never become successful captures.
    transcript_path = output_dir / "raw-session.jsonl"
    immutable(transcript_path, raw)
    final_path = output_dir / "exact-final.json"
    try:
        rows = [
            json.loads(line)
            for line in raw.decode("utf-8").splitlines()
            if line.strip()
        ]
        finals = [
            r
            for r in rows
            if r.get("type") == "response_item"
            and r.get("payload", {}).get("phase") == "final_answer"
            and r["payload"].get("role") == "assistant"
        ]
        if len(finals) != 1:
            raise ValueError("session must contain exactly one final_answer")
        final_raw = content_text(finals[0]["payload"]).encode("utf-8")
        immutable(final_path, final_raw)
        metas = [r for r in rows if r.get("type") == "session_meta"]
        if len(metas) != 1 or rows[0] != metas[0]:
            raise ValueError("session must start with unique host session metadata")
        meta = metas[0]["payload"]
        actual_task = meta["source"]["subagent"]["thread_spawn"]["agent_path"]
        if actual_task != task_id or not meta.get("id"):
            raise ValueError("host task/session identity differs")
        contexts = [r["payload"] for r in rows if r.get("type") == "turn_context"]
        if not contexts or any(
            c.get("model") != request.reviewer.model
            or c.get("effort") != request.reviewer.reasoning
            for c in contexts
        ):
            raise ValueError("host model or reasoning differs from frozen reviewer")
        started = timestamp(meta.get("timestamp", metas[0]["timestamp"]))
        completed = timestamp(finals[0]["timestamp"])
        if not protocol.frozen_at < started < completed:
            raise ValueError("host timing differs from protocol freeze")
        messages = [
            r
            for r in rows
            if r.get("type") == "response_item"
            and (
                r.get("payload", {}).get("role") == "user"
                or r.get("payload", {}).get("type") == "agent_message"
            )
        ]
        # Environment-only envelopes are host setup, not inherited case context.
        launches = []
        for row in messages:
            payload = row["payload"]
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
        if launch_row["payload"].get("type") == "agent_message" and (
            launch_row["payload"].get("recipient") != actual_task
        ):
            raise ValueError("launch recipient differs from host task identity")
        if rows.index(launch_row) > rows.index(finals[0]):
            raise ValueError("launch follows final")
        receipt_pin = None
        launch_verification = "plaintext_transcript_exact_bytes"
        try:
            captured_launch = content_text(launch_row["payload"]).encode("utf-8")
        except ValueError:
            if launch_receipt_path is None:
                raise
            launch_verification = "host_launch_receipt_encrypted_transcript_payload"
            captured_launch = None
        if captured_launch is not None and captured_launch != launch_raw:
            raise ValueError("initial launch differs from frozen launch bytes")
        if launch_receipt_path is not None:
            receipt_path = inside(root, launch_receipt_path)
            receipt_raw = receipt_path.read_bytes()
            receipt = json.loads(receipt_raw)
            expected = {
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
            if any(receipt.get(k) != v for k, v in expected.items()):
                raise ValueError("host launch receipt binding differs")
            launched = timestamp(receipt["launched_at"])
            if (
                not protocol.frozen_at < launched < completed
                or abs((launched - started).total_seconds()) > 60
            ):
                raise ValueError("host launch receipt timing differs")
            receipt_pin = pin(root, receipt_path, receipt_raw).model_dump(mode="json")
        response = AIReviewResponse.model_validate_json(final_raw)
        if (
            response.case_id != request.case_id
            or response.role != request.reviewer.role
        ):
            raise ValueError("response case or role differs")
        validate_response_evidence(response, required, request)
        validate_stage_response(response, spec, request, issues, root)
        events = AIHostSessionEvents(
            provenance="host_captured_collaboration_session",
            task_id=actual_task,
            session_id=meta["id"],
            reviewer=request.reviewer,
            request_sha256=model_sha256(request),
            final_sha256=digest(final_raw),
            started_at=started,
            completed_at=completed,
            raw_transcript=pin(root, transcript_path, raw),
        )
        event_path = output_dir / "host-events.json"
        for existing in root.rglob("*.json"):
            if existing.resolve() == event_path.resolve():
                continue
            event_raw = existing.read_bytes()
            try:
                payload = json.loads(event_raw)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(payload, dict):
                continue
            event_kind = payload.get("schema_version")
            if event_kind not in {
                "migration-stage-host-session-events-v1",
                "migration-ai-host-session-events-v1",
            }:
                continue
            cls = (
                AIHostSessionEvents
                if event_kind == "migration-stage-host-session-events-v1"
                else LegacyHostSessionEvents
            )
            prior = cls.model_validate_json(event_raw)
            if prior.session_id == events.session_id or prior.task_id == events.task_id:
                raise ValueError("reused review task or session identity")
        event_raw = json_bytes(events.model_dump(mode="json"))
        capture = AIReviewCapture(
            request=pin(root, request_path, request_raw),
            request_sha256=model_sha256(request),
            exact_final=pin(root, final_path, final_raw),
            host_events=pin(root, event_path, event_raw),
        )
        qualifications = {
            "status": "SEALED",
            "stage_policy": protocol.acceptance_policy,
            "case_id": request.case_id,
            "role": request.reviewer.role,
            "task_id": actual_task,
            "session_id": events.session_id,
            "model": request.reviewer.model,
            "reasoning": request.reviewer.reasoning,
            "request_artifact_sha256": digest(request_raw),
            "request_sha256": model_sha256(request),
            "final_sha256": digest(final_raw),
            "launch": pin(root, launch_path, launch_raw).model_dump(mode="json"),
            "launch_receipt": receipt_pin,
            "launch_verification": launch_verification,
            "provider_usage": "not_recorded",
            "identity_limitations": "host_capture_not_external_identity_attestation",
            "independence_limitations": "separate_contexts_do_not_establish_independent_model_errors",
        }
        immutable(event_path, event_raw)
        immutable(
            output_dir / "capture.json", json_bytes(capture.model_dump(mode="json"))
        )
        immutable(output_dir / "qualification.json", json_bytes(qualifications))
        return qualifications
    except (ValueError, KeyError, TypeError) as exc:
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


def validate_capture(out, capture_pin, *, protocol=None, case_pin=None, role=None):
    cap = AIReviewCapture.model_validate_json(_pinned(out, capture_pin))
    req = AIReviewRequest.model_validate_json(_pinned(out, cap.request))
    events = AIHostSessionEvents.model_validate_json(_pinned(out, cap.host_events))
    final_raw = _pinned(out, cap.exact_final)
    response = AIReviewResponse.model_validate_json(final_raw)
    frozen = AIReviewProtocol.model_validate_json(_pinned(out, req.protocol))
    spec = AICaseSpec.model_validate_json(_pinned(out, req.case_input))
    packet = StageInheritedIssuePacket.model_validate_json(
        _pinned(out, req.inherited_issues)
    )
    if (
        req.case_input not in frozen.case_inputs
        or req.inherited_issues not in frozen.inherited_issue_packets
        or req.case_id != spec.case_id
        or req.reviewer not in frozen.reviewers
        or events.reviewer != req.reviewer
        or response.case_id != req.case_id
        or response.role != req.reviewer.role
        or req.response_schema_sha256 != response_schema_sha256()
        or frozen.response_schema_sha256 != response_schema_sha256()
        or cap.request_sha256 != model_sha256(req)
        or events.request_sha256 != cap.request_sha256
        or events.final_sha256 != cap.exact_final.sha256
    ):
        raise ValueError("sealed stage capture identity/schema binding differs")
    if not frozen.frozen_at < events.started_at < events.completed_at:
        raise ValueError("sealed stage capture completion timing differs")
    if protocol is not None and req.protocol != protocol:
        raise ValueError("sealed stage capture protocol differs")
    if case_pin is not None and req.case_input != case_pin:
        raise ValueError("sealed stage capture case differs")
    if role is not None and req.reviewer.role != role:
        raise ValueError("sealed stage capture role differs")
    authorization = json.loads(_pinned(out, frozen.authorization_evidence))
    if (
        authorization.get("authorized") is not True
        or authorization.get("scope") != "prospective_stage_aware_review"
    ):
        raise ValueError("sealed stage capture authorization differs")
    for evidence in (
        req.prompt,
        events.raw_transcript,
        frozen.candidate_manifest,
        *req.prior_responses,
        *spec.source_evidence,
        spec.regulation_evidence,
        *spec.fixture_evidence,
    ):
        _pinned(out, evidence)
    validate_issue_packet(packet, out)
    validate_stage_response(response, spec, req, packet, out)
    return cap, req, events, final_raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "request", "session", "launch", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--launch-receipt", type=Path)
    args = parser.parse_args()
    result = seal_session(
        root=args.root,
        request_path=args.request,
        session_path=args.session,
        launch_path=args.launch,
        task_id=args.task,
        output_dir=args.output,
        launch_receipt_path=args.launch_receipt,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
