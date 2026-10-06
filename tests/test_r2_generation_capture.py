"""Synthetic host sessions qualify capture logic, never live provider evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from cobol_archaeologist.migration.ai_review import model_sha256
from cobol_archaeologist.migration.successor import (
    SuccessorCapture,
    SuccessorMigrationRequest,
    successor_run_key,
)
from tests.test_migration_successor import SOURCE, proposal, request

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/seal_r2_generation_session.py"
SPEC = importlib.util.spec_from_file_location("generation_seal", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
seal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seal)


@pytest.fixture
def session(tmp_path):
    def save(name, value):
        raw = value if isinstance(value, bytes) else seal.json_bytes(value)
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"path": name, "sha256": seal.digest(raw)}

    payload = request().model_dump(mode="json")
    method_pins = {
        name: save(f"runtime/{name}.py", f"# {name}\n".encode())
        for name in ("runner", "validator", "backend")
    }
    method_pins["validation_protocol"] = save(
        "validation.json", {"capability": "synthetic"}
    )
    for name, value in method_pins.items():
        payload["method"][f"{name}_sha256"] = value["sha256"]
    payload["case"]["validation_protocol_sha256"] = method_pins["validation_protocol"][
        "sha256"
    ]
    runtime_sources = [method_pins[name] for name in ("runner", "validator", "backend")]
    runtime_hash = seal.digest(
        json.dumps(
            {p["path"]: p["sha256"] for p in runtime_sources},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    payload["method"]["runtime_source_sha256"] = runtime_hash
    decision = save(
        "decision.json",
        {
            "configuration": 4,
            "status": "NOT_EVALUABLE",
            "schema_version": "configuration-4-detector-decision-v1",
        },
    )
    payload["detector"].update(
        {
            "detector_decision": decision,
            "evaluation_manifest": save("eval.json", {}),
            "input_roster": save(
                "intake.json",
                {
                    "configuration": 4,
                    "decision": decision,
                    "detector_led": {
                        "active": False,
                        "count": 0,
                        "eligible_findings": [],
                    },
                },
            ),
        }
    )
    req = SuccessorMigrationRequest.model_validate(payload)
    request_pin = save("request.json", req.model_dump(mode="json"))
    launch = save("launch.txt", b"Generate the frozen one-case request.\r\n")
    source = save("staging/DEMO.cbl", SOURCE.encode())
    freeze = {
        "schema_version": "migration-successor-runtime-manifest-v1",
        "frozen_at": "2026-10-06T00:00:00Z",
        "runtime_sources": runtime_sources,
        "runtime_source_sha256": runtime_hash,
        "requests": [
            {
                "request": request_pin,
                "request_sha256": model_sha256(req),
                "launch": launch,
                "run_key": successor_run_key(req),
                "staging_root": str(tmp_path / "staging"),
                "source_pins": [source],
                "method_pins": method_pins,
            }
        ],
    }
    save("freeze.json", freeze)
    receipt = {
        "schema_version": "migration-ai-host-launch-receipt-v1",
        "provenance": "root_host_captured_tool_invocation_and_return",
        "transport": "collaboration.spawn_agent",
        "fork_turns": "none",
        "task_id": "/root/generation",
        "returned_task_name": "/root/generation",
        "request_sha256": model_sha256(req),
        "request_artifact_sha256": request_pin["sha256"],
        "launch_sha256": launch["sha256"],
        "launched_at": "2026-10-06T01:00:03Z",
        "identity_limitations": "host_capture_not_external_identity_attestation",
    }
    save("launch-receipt.json", receipt)
    final = json.dumps(proposal(), indent=2) + "\r\n"
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-10-06T01:00:00Z",
            "payload": {
                "id": "generation-session",
                "timestamp": "2026-10-06T01:00:00Z",
                "source": {
                    "subagent": {"thread_spawn": {"agent_path": "/root/generation"}}
                },
            },
        },
        {
            "type": "turn_context",
            "timestamp": "2026-10-06T01:00:01Z",
            "payload": {"model": "gpt-6-luna", "effort": "max"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-10-06T01:00:02Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Generate the frozen one-case request.\r\n",
                    }
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
    return tmp_path, req, rows, final


def run(session, output="sealed"):
    root, _, rows, _ = session
    transcript = root / "session.jsonl"
    transcript.write_bytes(
        b"".join((json.dumps(row) + "\r\n").encode() for row in rows)
    )
    return seal.seal_session(
        root=root,
        request_path=root / "request.json",
        session_path=transcript,
        launch_path=root / "launch.txt",
        launch_receipt_path=root / "launch-receipt.json",
        freeze_path=root / "freeze.json",
        task_id="/root/generation",
        output_dir=root / output,
    )


def test_exact_final_and_actual_host_identity_are_sealed(session):
    root, req, _, final = session
    result = run(session)
    capture = SuccessorCapture.model_validate_json(
        (root / "sealed/capture.json").read_bytes()
    )
    assert capture.provider_usage == "not_recorded"
    assert capture.provider.model == "gpt-6-luna"
    assert (
        capture.task_id == "/root/generation"
        and capture.session_id == "generation-session"
    )
    assert capture.run_key == successor_run_key(req)
    assert (root / "sealed/exact-final.json").read_bytes() == final.encode()
    assert (root / "sealed/raw-session.jsonl").read_bytes() == (
        root / "session.jsonl"
    ).read_bytes()
    assert run(session) == result


@pytest.mark.parametrize(
    "defect,match",
    [
        ("model", "model or reasoning"),
        ("effort", "model or reasoning"),
        ("extra_context", "fresh one-case"),
        ("launch", "launch differs"),
        ("task", "task/session"),
        ("freeze_time", "generation freeze"),
        ("extra_final", "exactly one final"),
    ],
)
def test_model_context_and_timing_fail_closed(session, defect, match):
    root, _, rows, final = session
    if defect in {"model", "effort"}:
        rows[1]["payload"][defect] = "different"
    elif defect == "extra_context":
        rows.insert(3, rows[2].copy())
    elif defect == "launch":
        rows[2]["payload"]["content"][0]["text"] = "different launch"
    elif defect == "task":
        rows[0]["payload"]["source"]["subagent"]["thread_spawn"]["agent_path"] = (
            "/root/wrong"
        )
    elif defect == "freeze_time":
        rows[0]["payload"]["timestamp"] = "2026-10-05T01:00:00Z"
    else:
        rows.append(rows[-1].copy())
    with pytest.raises(ValueError, match=match):
        run(session)
    assert (root / "sealed/raw-session.jsonl").exists()
    assert (root / "sealed/rejection.json").exists()
    assert not (root / "sealed/capture.json").exists()
    if defect != "extra_final":
        assert (root / "sealed/exact-final.json").read_bytes() == final.encode()


@pytest.mark.parametrize(
    "target",
    [
        "request.json",
        "runtime/backend.py",
        "validation.json",
        "staging/DEMO.cbl",
        "decision.json",
    ],
)
def test_frozen_request_source_and_runtime_tamper_rejected(session, target):
    root, _, _, _ = session
    path = root / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        run(session)
    assert not (root / "sealed/capture.json").exists()


@pytest.mark.parametrize(
    "field",
    [
        "fork_turns",
        "request_sha256",
        "request_artifact_sha256",
        "launch_sha256",
        "returned_task_name",
        "launched_at",
    ],
)
def test_encrypted_launch_is_bound_to_host_return_receipt(session, field):
    root, _, rows, _ = session
    rows[2]["payload"] = {
        "type": "agent_message",
        "author": "/root",
        "recipient": "/root/generation",
        "content": [{"type": "encrypted_content", "encrypted_content": "opaque"}],
    }
    receipt = json.loads((root / "launch-receipt.json").read_bytes())
    receipt[field] = "2026-10-06T02:01:00Z" if field == "launched_at" else "bad"
    (root / "launch-receipt.json").write_bytes(seal.json_bytes(receipt))
    with pytest.raises(ValueError, match="host launch receipt"):
        run(session)


def test_encrypted_launch_valid_receipt_and_explicit_abstention(session):
    root, _, rows, _ = session
    rows[2]["payload"] = {
        "type": "agent_message",
        "author": "/root",
        "recipient": "/root/generation",
        "content": [{"type": "encrypted_content", "encrypted_content": "opaque"}],
    }
    rows[-1]["payload"]["content"][0]["text"] = (
        '{"kind":"abstention","reason":"cannot safely remediate"}'
    )
    result = run(session)
    assert result["proposal_kind"] == "abstention"
    assert (
        result["launch_verification"]
        == "host_launch_receipt_encrypted_transcript_payload"
    )
    assert (
        SuccessorCapture.model_validate_json(
            (root / "sealed/capture.json").read_bytes()
        ).proposal.kind
        == "abstention"
    )


@pytest.mark.parametrize(
    "final",
    ["not json", '{"kind":"patch","usage":42}', '{"kind":"abstention","reason":" "}'],
)
def test_malformed_final_preserved_without_improvement(session, final):
    root, _, rows, _ = session
    rows[-1]["payload"]["content"][0]["text"] = final
    with pytest.raises(ValueError):
        run(session)
    assert (root / "sealed/exact-final.json").read_bytes() == final.encode()
    assert not (root / "sealed/capture.json").exists()


def test_task_session_or_run_cannot_be_reused(session):
    run(session)
    with pytest.raises(ValueError, match="reused generation"):
        run(session, output="second")


@pytest.mark.parametrize("field", ["task_id", "session_id", "run_key"])
def test_each_identity_component_independently_prevents_reuse(session, field):
    root, _, _, _ = session
    run(session)
    prior_path = root / "sealed/capture.json"
    prior = json.loads(prior_path.read_bytes())
    for key in ("task_id", "session_id", "run_key"):
        if key != field:
            prior[key] = "f" * 64 if key == "run_key" else f"another-{key}"
    # A separate prior ledger entry shares only the selected identity component.
    # This synthetic test checks collision handling, not prior evidence validity.
    prior_path.write_bytes(seal.json_bytes(prior))
    with pytest.raises(ValueError, match="reused generation"):
        run(session, output="second")


def test_changed_transcript_cannot_overwrite_seal(session):
    run(session)
    session[2][1]["timestamp"] = "2026-10-06T01:00:01.001Z"
    with pytest.raises(ValueError, match="refusing to replace"):
        run(session)
