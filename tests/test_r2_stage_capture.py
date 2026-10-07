"""Provider-free capture qualification; synthetic sessions are not live evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cobol_archaeologist.migration.ai_review import (
    model_sha256,
)
from scripts.stage_review_contracts import StageHostSessionEvents as AIHostSessionEvents
from scripts.stage_review_contracts import StageReviewCapture as AIReviewCapture
from scripts.stage_review_contracts import StageReviewProtocol
from scripts.stage_review_contracts import StageReviewRequest as AIReviewRequest
from tests.test_migration_ai_review import pin
from tests.test_stage_review_contracts import stage_graph

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/seal_r2_stage_review_session.py"
sys.path.insert(0, str(SCRIPT.parent))
module_spec = importlib.util.spec_from_file_location("r2_stage_seal", SCRIPT)
assert module_spec is not None and module_spec.loader is not None
seal = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(seal)


@pytest.fixture
def session(tmp_path):
    stage_graph(tmp_path)
    authorization = pin(
        tmp_path,
        "stage-authorization.json",
        {"authorized": True, "scope": "prospective_stage_aware_review"},
    )
    payload = json.loads((tmp_path / "stage-protocol.json").read_bytes())
    payload["authorization_evidence"] = authorization.model_dump(mode="json")
    protocol = StageReviewProtocol(**payload)
    protocol_pin = pin(
        tmp_path, "stage-protocol.json", protocol.model_dump(mode="json")
    )
    for role in ("ai_primary", "independent_ai_verifier", "ai_adjudicator"):
        path = tmp_path / f"stage-requests/{role}.json"
        payload = json.loads(path.read_bytes())
        payload["protocol"] = protocol_pin.model_dump(mode="json")
        pin(tmp_path, f"stage-requests/{role}.json", payload)
    request = AIReviewRequest.model_validate_json(
        (tmp_path / "stage-requests/ai_primary.json").read_bytes()
    )
    (tmp_path / "stage-requests/ai_primary.json").write_bytes(
        json.dumps(request.model_dump(mode="json"), indent=2).encode()
    )
    launch = tmp_path / "launch.txt"
    launch.write_bytes(b"Review the frozen one-case request.\r\n")
    # The launch must be the exact pinned request prompt, not an asserted hash.
    prompt = tmp_path / request.prompt.path
    launch.write_bytes(prompt.read_bytes())
    final = (tmp_path / "stage-finals/ai_primary.json").read_text(encoding="utf-8")
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-10-06T01:00:00Z",
            "payload": {
                "id": "fresh-session",
                "timestamp": "2026-10-06T01:00:00Z",
                "source": {"subagent": {"thread_spawn": {"agent_path": "/root/fresh"}}},
            },
        },
        {
            "type": "turn_context",
            "timestamp": "2026-10-06T01:00:01Z",
            "payload": {
                "model": request.reviewer.model,
                "effort": request.reviewer.reasoning,
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-10-06T01:00:02Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": launch.read_text(encoding="utf-8")},
                ],
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-10-06T02:00:00Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": final}],
            },
        },
    ]
    path = tmp_path / "host-session.jsonl"
    return tmp_path, request, launch, path, rows, final


def run(session):
    root, _, launch, path, rows, _ = session
    path.write_bytes(b"".join((json.dumps(row) + "\r\n").encode() for row in rows))
    return seal.seal_session(
        root=root,
        request_path=root / "stage-requests/ai_primary.json",
        session_path=path,
        launch_path=launch,
        task_id="/root/fresh",
        output_dir=root / "sealed",
    )


def test_exact_bytes_raw_pin_and_canonical_model_hash_are_distinct(session):
    root, request, _, path, _, final = session
    result = run(session)
    capture = AIReviewCapture.model_validate_json(
        (root / "sealed/capture.json").read_bytes()
    )
    events = AIHostSessionEvents.model_validate_json(
        (root / capture.host_events.path).read_bytes()
    )
    assert (root / capture.exact_final.path).read_bytes() == final.encode("utf-8")
    assert (root / events.raw_transcript.path).read_bytes() == path.read_bytes()
    assert capture.request_sha256 == model_sha256(request)
    assert capture.request.sha256 != capture.request_sha256
    assert events.session_id == "fresh-session"
    assert result["status"] == "SEALED"
    assert result["provider_usage"] == "not_recorded"
    assert run(session) == result


@pytest.mark.parametrize(
    "defect,match",
    [
        ("model", "model or reasoning"),
        ("effort", "model or reasoning"),
        ("extra_user", "fresh one-case"),
        ("wrong_launch", "launch differs"),
        ("encrypted_launch", "encrypted launch"),
        ("extra_final", "exactly one final"),
        ("freeze", "protocol freeze"),
    ],
)
def test_capture_rejects_identity_or_context_contamination(session, defect, match):
    _, _, _, _, rows, _ = session
    if defect in {"model", "effort"}:
        rows[1]["payload"][defect] = "different"
    elif defect == "extra_user":
        rows.insert(3, rows[2].copy())
    elif defect == "wrong_launch":
        rows[2]["payload"]["content"][0]["text"] = "model asserts prompt matched"
    elif defect == "encrypted_launch":
        rows[2]["payload"]["content"] = [
            {"type": "encrypted_content", "encrypted_content": "opaque"}
        ]
    elif defect == "extra_final":
        rows.append(rows[-1].copy())
    elif defect == "freeze":
        rows[0]["payload"]["timestamp"] = "2026-10-05T01:00:00Z"
    with pytest.raises(ValueError, match=match):
        run(session)
    assert not (session[0] / "sealed/capture.json").exists()


@pytest.mark.parametrize("defect", ["schema", "case", "role", "evidence"])
def test_invalid_final_is_preserved_unmodified(session, defect):
    root, _, _, path, rows, _ = session
    final = json.loads(rows[-1]["payload"]["content"][0]["text"])
    if defect == "schema":
        final["provider_usage"] = 42
    elif defect == "case":
        final["case_id"] = "migration_other"
    elif defect == "role":
        final["role"] = "independent_ai_verifier"
    else:
        final["evidence"] = final["evidence"][:1]
    text = json.dumps(final, indent=2) + "\r\n"
    rows[-1]["payload"]["content"][0]["text"] = text
    with pytest.raises(ValueError):
        run(session)
    assert (root / "sealed/exact-final.json").read_bytes() == text.encode()
    assert (root / "sealed/raw-session.jsonl").read_bytes() == path.read_bytes()
    assert (root / "sealed/rejection.json").exists()
    assert not (root / "sealed/capture.json").exists()


def test_changed_session_cannot_replace_sealed_bytes(session):
    run(session)
    session[4][1]["timestamp"] = "2026-10-06T01:00:01.001Z"
    with pytest.raises(ValueError, match="refusing to replace"):
        run(session)


def test_request_prompt_integrity_and_output_root_are_checked(session):
    root, request, launch, path, _, _ = session
    (root / request.prompt.path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        run(session)
    with pytest.raises(ValueError, match="escapes root"):
        seal.seal_session(
            root=root,
            request_path=root / "stage-requests/ai_primary.json",
            session_path=path,
            launch_path=launch,
            task_id="/root/fresh",
            output_dir=root.parent / "outside",
        )


def receipt_for(session):
    root, request, launch, _, _, _ = session
    receipt = {
        "schema_version": "migration-ai-host-launch-receipt-v1",
        "provenance": "root_host_captured_tool_invocation_and_return",
        "transport": "collaboration.spawn_agent",
        "fork_turns": "none",
        "task_id": "/root/fresh",
        "returned_task_name": "/root/fresh",
        "request_sha256": model_sha256(request),
        "request_artifact_sha256": seal.digest(
            (root / "stage-requests/ai_primary.json").read_bytes()
        ),
        "launch_sha256": seal.digest(launch.read_bytes()),
        "launched_at": "2026-10-06T01:00:03Z",
        "identity_limitations": "host_capture_not_external_identity_attestation",
    }
    return receipt


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "fork_turns",
        "task_id",
        "launch_sha256",
        "request_artifact_sha256",
        "request_sha256",
        "launched_at",
    ],
)
def test_encrypted_launch_requires_bound_host_receipt(session, defect):
    root, _, launch, path, rows, _ = session
    rows[2]["payload"] = {
        "type": "agent_message",
        "author": "/root",
        "recipient": "/root/fresh",
        "content": [
            {"type": "input_text", "text": "Message Type: NEW_TASK\n"},
            {"type": "encrypted_content", "encrypted_content": "opaque"},
        ],
    }
    path.write_bytes(b"".join((json.dumps(row) + "\n").encode() for row in rows))
    receipt = receipt_for(session)
    if defect:
        receipt[defect] = "2026-10-06T02:01:00Z" if defect == "launched_at" else "bad"
    receipt_path = root / "launch-receipt.json"
    receipt_path.write_bytes(seal.json_bytes(receipt))
    kwargs = {
        "root": root,
        "request_path": root / "stage-requests/ai_primary.json",
        "session_path": path,
        "launch_path": launch,
        "task_id": "/root/fresh",
        "output_dir": root / "sealed",
        "launch_receipt_path": receipt_path,
    }
    if defect:
        with pytest.raises(ValueError, match="host launch receipt"):
            seal.seal_session(**kwargs)
        assert not (root / "sealed/capture.json").exists()
    else:
        result = seal.seal_session(**kwargs)
        assert (
            result["launch_verification"]
            == "host_launch_receipt_encrypted_transcript_payload"
        )
        assert result["launch_receipt"]["sha256"] == seal.digest(
            receipt_path.read_bytes()
        )


@pytest.mark.parametrize("defect", [None, "partial", "extra", "hash", "duplicate"])
def test_adjudicator_can_cite_only_the_exact_bound_prior_pair(session, defect):
    root, _, launch, _, rows, _ = session
    request = AIReviewRequest.model_validate_json(
        (root / "stage-requests/ai_adjudicator.json").read_bytes()
    )
    (root / "stage-requests/ai_primary.json").write_bytes(
        seal.json_bytes(request.model_dump(mode="json"))
    )
    launch.write_bytes((root / request.prompt.path).read_bytes())
    rows[2]["payload"]["content"][0]["text"] = launch.read_text(encoding="utf-8")
    response = json.loads((root / "stage-finals/ai_adjudicator.json").read_bytes())
    response["evidence"].extend(
        p.model_dump(mode="json") for p in request.prior_responses
    )
    if defect == "partial":
        response["evidence"].pop()
    elif defect == "extra":
        response["evidence"].append({"path": "unbound.json", "sha256": "f" * 64})
    elif defect == "hash":
        response["evidence"][-1]["sha256"] = "f" * 64
    elif defect == "duplicate":
        response["evidence"].append(response["evidence"][-1].copy())
    exact = json.dumps(response, indent=2) + "\r\n"
    rows[-1]["payload"]["content"][0]["text"] = exact
    if defect:
        with pytest.raises(ValueError, match="unbound citations"):
            run(session)
        assert not (root / "sealed/capture.json").exists()
    else:
        assert run(session)["status"] == "SEALED"
    assert (root / "sealed/exact-final.json").read_bytes() == exact.encode()


def test_reused_original_context_fails_even_nonstandard_event_filename(session):
    root, _, _, _, rows, _ = session
    old = json.loads((root / "events/ai_primary.json").read_bytes())
    old["session_id"] = rows[0]["payload"]["id"]
    pin(root, "historical/original-session-evidence.json", old)
    with pytest.raises(ValueError, match="reused"):
        run(session)


def test_typed_quote_must_match_actual_evidence_and_invalid_final_is_retained(session):
    root, _, _, _, rows, _ = session
    payload = json.loads(rows[-1]["payload"]["content"][0]["text"])
    payload["post_patch_validation_obligations"][0]["evidence"][0]["quote"] = (
        "invented source evidence"
    )
    exact = json.dumps(payload)
    rows[-1]["payload"]["content"][0]["text"] = exact
    with pytest.raises(ValueError, match="quote absent"):
        run(session)
    assert (root / "sealed/exact-final.json").read_bytes() == exact.encode()


def test_inherited_inventory_cannot_drop_old_issue(session):
    root, request, _, _, _, _ = session
    old_path = root / "finals/ai_primary.json"
    old = json.loads(old_path.read_bytes())
    old["unresolved_issues"] = ["Exact old issue must survive"]
    oldpin = pin(root, "finals/ai_primary.json", old)
    packet = json.loads((root / "inherited.json").read_bytes())
    packet["historical_finals"][0] = oldpin.model_dump(mode="json")
    packetpin = pin(root, "inherited.json", packet)
    protocol = json.loads((root / "stage-protocol.json").read_bytes())
    protocol["inherited_issue_packets"] = [packetpin.model_dump(mode="json")]
    protocolpin = pin(root, "stage-protocol.json", protocol)
    data = request.model_dump(mode="json")
    data.update(
        inherited_issues=packetpin.model_dump(mode="json"),
        protocol=protocolpin.model_dump(mode="json"),
    )
    pin(root, "stage-requests/ai_primary.json", data)
    with pytest.raises(ValueError, match="exhaust"):
        run(session)


def test_legacy_response_schema_cannot_be_sealed_under_stage_identity(session):
    _, _, _, _, rows, _ = session
    payload = json.loads(rows[-1]["payload"]["content"][0]["text"])
    payload["schema_version"] = "migration-ai-review-response-v1"
    rows[-1]["payload"]["content"][0]["text"] = json.dumps(payload)
    with pytest.raises(ValueError, match="migration-stage-review-response-v1"):
        run(session)

