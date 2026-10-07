"""Synthetic promotion gates; host sessions here never count as live evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_migration_ai_review import pin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "stage_promotion_gate", ROOT / "scripts/promote_r2_stage_review_roster.py"
)
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)
B, C = P.builder, P.C


def seal(out, spec, role, request, response, start, task):
    end = start + timedelta(seconds=1)
    launch = out / request.prompt.path
    text = response.model_dump_json()
    rows = [
        {
            "type": "session_meta",
            "timestamp": start.isoformat(),
            "payload": {
                "id": "session-" + task,
                "timestamp": start.isoformat(),
                "source": {"subagent": {"thread_spawn": {"agent_path": task}}},
            },
        },
        {
            "type": "turn_context",
            "timestamp": start.isoformat(),
            "payload": {
                "model": request.reviewer.model,
                "effort": request.reviewer.reasoning,
            },
        },
        {
            "type": "response_item",
            "timestamp": start.isoformat(),
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": launch.read_text()}],
            },
        },
        {
            "type": "response_item",
            "timestamp": end.isoformat(),
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": text}],
            },
        },
    ]
    session = out / f"synthetic-sessions/{spec.case_id}/{role}.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("".join(json.dumps(row) + "\n" for row in rows))
    P.sealer.seal_session(
        root=out,
        request_path=out / f"stage-review/requests/{spec.case_id}/{role}/request.json",
        session_path=session,
        launch_path=launch,
        task_id=task,
        output_dir=out / f"stage-review/reviews/{spec.case_id}/{role}",
    )


def synthetic_response(out, spec, request, packet, role_index):
    quote = B.read_pin(out, spec.source_evidence[0]).decode().splitlines()[0]
    issues = []
    for old in packet.issues:
        category = (
            "scope_limitation"
            if role_index == 1 and old.index == 0
            else "post_patch_validation_obligation"
        )
        issues.append(
            C.StageReviewIssue(
                category=category,
                text=old.text,
                inherited_issue_index=old.index,
                rationale="Synthetic schema qualification; no semantic approval claim",
                evidence=[{"pin": spec.source_evidence[0], "quote": quote}],
            )
        )
    extra = C.StageReviewIssue(
        category="post_patch_validation_obligation",
        text="Synthetic obligation " + request.reviewer.role,
        rationale="Actual future patch must be validated",
        evidence=[{"pin": spec.source_evidence[0], "quote": quote}],
    )
    data = {
        "case_id": spec.case_id,
        "role": request.reviewer.role,
        "decision": "include",
        "rationale": "Synthetic fixture for deterministic promotion integrity",
        "scope_judgment": "finite",
        "intended_fixture_judgment": "synthetic",
        "regression_fixture_judgment": "synthetic",
        "capability_judgment": "synthetic",
        "duplicate_source_judgment": "dependent",
        "evidence": [
            *spec.source_evidence,
            spec.regulation_evidence,
            *spec.fixture_evidence,
        ],
        "inherited_issue_classifications": issues,
        "scope_limitations": [i for i in issues if i.category == "scope_limitation"],
        "post_patch_validation_obligations": [
            i for i in issues if i.category == "post_patch_validation_obligation"
        ]
        + [extra],
        "classification_disagreements_resolved": [0]
        if role_index == 2 and issues
        else [],
    }
    return C.StageReviewResponse(**data)


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("stage-promotion-template")
    out = root / "data/migration/ai-review"
    actual = ROOT / "data/migration/ai-review"
    history = B.audit_history(ROOT, actual)
    shutil.copytree(actual, out, ignore=shutil.ignore_patterns("stage-review"))
    inventory = json.loads(
        (actual / "revisions/runtime-source-inventory.json").read_bytes()
    )
    for name in (*inventory, *B.STAGE_SCRIPTS):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    name = "data/migration/coordination/proposed-stage-review-amendment.json"
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)
    pin(
        out,
        B.AUTHORIZATION,
        {
            "authorized": True,
            "scope": "prospective_stage_aware_review",
            "proposal": {
                "path": name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            },
        },
    )
    audit = B.audit_history
    B.audit_history = lambda *args: history
    try:
        protocol = B.prepare(
            root, frozen_at=(history["completed_at"] + timedelta(seconds=1)).isoformat()
        )
        for spec, packet_pin in zip(
            history["specs"], protocol.inherited_issue_packets, strict=True
        ):
            packet = C.StageInheritedIssuePacket.model_validate_json(
                B.read_pin(out, packet_pin)
            )
            start = protocol.frozen_at + timedelta(seconds=10)
            for n, role in enumerate(B.ROLES):
                request = (
                    C.StageReviewRequest.model_validate_json(
                        (
                            out
                            / f"stage-review/requests/{spec.case_id}/{role}/request.json"
                        ).read_bytes()
                    )
                    if n < 2
                    else B.adjudicator(
                        spec.case_id, root=root, materialized_at=start.isoformat()
                    )
                )
                response = synthetic_response(out, spec, request, packet, n)
                seal(
                    out,
                    spec,
                    role,
                    request,
                    response,
                    start,
                    f"/root/synthetic-{spec.case_id}-{role}",
                )
                start += timedelta(seconds=3)
    finally:
        B.audit_history = audit
    return root, history


@pytest.fixture
def graph(template, tmp_path, monkeypatch):
    source, history = template
    root = tmp_path / "repo"
    shutil.copytree(source, root)
    out = root / "data/migration/ai-review"
    # The template's absolute launch location must follow this disposable copy.
    # Prompt/request/final/host evidence bytes remain exactly unchanged.
    for path in (out / "stage-review/requests").glob("*/*/launch.txt"):
        path.write_bytes(
            path.read_bytes().replace(
                source.as_posix().encode(), root.as_posix().encode()
            )
        )
        contract_path = path.with_name("launch-contract.json")
        contract = json.loads(contract_path.read_bytes())
        contract["launch"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        contract_path.write_bytes(B.original.encoded(contract))
    monkeypatch.setattr(B, "audit_history", lambda *args: history)
    return root, out, history


def test_full_60_context_lineage_union_and_replay(graph):
    root, out, _ = graph
    before = {
        p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file()
    }
    result = P.promote(root)
    assert result["accepted_case_ids"] == list(B.CASE_IDS)
    assert result["generation_denominators"] == {
        "detector_led": 0,
        "oracle_assisted": 4,
        "combined": 4,
    }
    assert (
        result["stage_review_capture_count"] + result["historical_review_capture_count"]
        == 60
    )
    assert result["generation_authorized"] is False
    cases = C.load_stage_canonical_roster(
        root / "data/migration/cases.jsonl",
        review_evidence_root=out,
        protocol_path=out / "stage-review/review-protocol.json",
        disposition_path=out / "stage-review/disposition.json",
    )
    assert len(cases) == 4
    for case in cases:
        assert case.scope_limitations
        assert {
            i.text
            for i in case.post_patch_validation_obligations
            if i.inherited_issue_index is None
        } == {"Synthetic obligation " + role for role in B.ROLES}
    assert P.promote(root) == result
    for name, digest in before.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest


def test_missing_role_cannot_publish(graph):
    root, out, _ = graph
    (
        out / f"stage-review/reviews/{B.CASE_IDS[-1]}/ai_adjudicator/capture.json"
    ).unlink()
    with pytest.raises(OSError):
        P.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_current_runtime_and_snapshot_are_checked_before_promotion(graph):
    root, _, _ = graph
    (root / B.STAGE_SCRIPTS[0]).write_text("changed")
    with pytest.raises(ValueError):
        P.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def mutate_final(out, case, role, change):
    cap_path = f"stage-review/reviews/{case}/{role}/capture.json"
    cap = json.loads((out / cap_path).read_bytes())
    final_path = cap["exact_final"]["path"]
    value = json.loads((out / final_path).read_bytes())
    change(value)
    final = pin(out, final_path, value)
    event_path = cap["host_events"]["path"]
    event = json.loads((out / event_path).read_bytes())
    raw_path = event["raw_transcript"]["path"]
    rows = [json.loads(line) for line in (out / raw_path).read_text().splitlines()]
    rows[-1]["payload"]["content"][0]["text"] = (out / final_path).read_text()
    raw = pin(out, raw_path, "".join(json.dumps(row) + "\n" for row in rows).encode())
    event.update(final_sha256=final.sha256, raw_transcript=raw.model_dump())
    event_pin = pin(out, event_path, event)
    cap.update(exact_final=final.model_dump(), host_events=event_pin.model_dump())
    pin(out, cap_path, cap)


def test_excluded_subset_preserves_every_chain_and_denominator(graph):
    root, out, _ = graph
    excluded = B.CASE_IDS[1]
    mutate_final(
        out, excluded, "ai_adjudicator", lambda f: f.update(decision="exclude")
    )
    result = P.promote(root)
    assert result["status"] == "COMPLETE_WITH_EXCLUSIONS"
    assert result["accepted_case_ids"] == [c for c in B.CASE_IDS if c != excluded]
    assert result["stage_excluded_case_ids"] == [excluded]
    assert result["generation_denominators"]["combined"] == 3
    assert result["stage_review_capture_count"] == 12
    assert (out / f"stage-review/evidence/{excluded}.json").exists()


@pytest.mark.parametrize(
    "defect",
    ["quote", "evidence", "disagreement", "omit_classification", "omit_category"],
)
def test_bad_classification_cannot_publish_even_for_excluded_cases(graph, defect):
    root, out, _ = graph
    role = "ai_adjudicator" if defect == "disagreement" else "ai_primary"

    def change(f):
        f["decision"] = "exclude"
        if defect == "quote":
            f["post_patch_validation_obligations"][-1]["evidence"][0]["quote"] = (
                "SYNTHETIC QUOTE ABSENT FROM SOURCE"
            )
        elif defect == "evidence":
            f["evidence"] = f["evidence"][:1]
        elif defect == "disagreement":
            f["classification_disagreements_resolved"] = []
        elif defect == "omit_classification":
            f["inherited_issue_classifications"] = f["inherited_issue_classifications"][
                1:
            ]
        else:
            f["post_patch_validation_obligations"] = f[
                "post_patch_validation_obligations"
            ][1:]

    mutate_final(out, B.CASE_IDS[0], role, change)
    with pytest.raises(ValueError):
        P.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_historical_context_reuse_is_not_fresh(graph):
    root, out, history = graph
    name = f"stage-review/reviews/{B.CASE_IDS[0]}/ai_primary/capture.json"
    cap = json.loads((out / name).read_bytes())
    event = json.loads((out / cap["host_events"]["path"]).read_bytes())
    event["task_id"] = history["task_ids"][0]
    epin = pin(out, cap["host_events"]["path"], event)
    cap["host_events"] = epin.model_dump()
    pin(out, name, cap)
    with pytest.raises(ValueError, match="reused"):
        P.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


@pytest.mark.parametrize(
    "artifact",
    [
        "stage-review/runtime-source.zip",
        "stage-review/inherited-issues/migration_075075.json",
        "revisions/inputs/migration_075075/case-input.json",
    ],
)
def test_frozen_archive_issue_inventory_and_case_cannot_change(graph, artifact):
    root, out, _ = graph
    (out / artifact).write_bytes(b"changed")
    with pytest.raises(ValueError):
        P.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()
