"""Promotion reconciles all 36 reviews and never promotes a partial roster."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    spec = importlib.util.spec_from_file_location(
        "request_helpers", ROOT / "tests/test_r2_review_requests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prerequisites(root, case_ids):
    h = helpers()
    temporal_rows = [{"instance_id": f"drift_{i:06d}"} for i in range(40)]
    rows = h.save(
        root,
        "data/benchmark/t6-v2/final/evaluation-rows.jsonl",
        ("\n".join(json.dumps(row) for row in temporal_rows) + "\n").encode(),
    )
    temporal = h.save(
        root,
        "data/benchmark/t6-v2/final/manifest.json",
        {
            "finalized": True,
            "evaluation_ready": True,
            "target_pair_count": 20,
            "evaluation_side_count": 40,
            "pair_order": [f"pair-{i}" for i in range(20)],
            "instance_order": [r["instance_id"] for r in temporal_rows],
            "evaluation_rows": rows,
        },
    )
    runtime = h.save(
        root, "data/eval/m4/runtime-source.zip", b"historical frozen runtime"
    )
    snap = h.save(
        root,
        "data/eval/m4/runtime-source-manifest.json",
        {
            "archive_path": runtime["path"],
            "archive_sha256": runtime["sha256"],
            "files": {},
        },
    )
    decision = h.save(
        root,
        "data/eval/m4/detector-decision.json",
        {"configuration": 4, "status": "NOT_EVALUABLE", "inputs": []},
    )
    candidate = {
        "path": "data/migration/candidate-manifest.json",
        "sha256": h.hashlib.sha256(
            (root / "data/migration/candidate-manifest.json").read_bytes()
        ).hexdigest(),
    }
    candidate_files = []
    for name in (
        "candidate-roster.jsonl",
        "oracle-candidate-specs.jsonl",
        "detector-visible-candidates.jsonl",
    ):
        candidate_files.append(
            {
                "path": "data/migration/" + name,
                "sha256": h.hashlib.sha256(
                    (root / "data/migration" / name).read_bytes()
                ).hexdigest(),
            }
        )
    intake = h.save(
        root,
        "data/eval/m4/r2-input-roster.json",
        {
            "configuration": 4,
            "decision": decision,
            "candidate_manifest": candidate,
            "candidate_files": candidate_files,
            "detector_led": {"active": False, "count": 0, "eligible_findings": []},
            "oracle_assisted": {"candidate_count": 12, "candidate_ids": case_ids},
            "temporal_review_manifest": temporal,
        },
    )
    manifest = h.save(
        root,
        "data/eval/m4/evaluation-manifest.json",
        {"decision": decision, "r2_input_roster": intake, "artifacts": []},
    )
    h.save(
        root,
        "data/eval/m4/terminal-receipt.json",
        {
            "status": "COMPLETE",
            "pending_evaluation_keys": 0,
            "runtime_snapshot_reproduces_frozen_hash": True,
            "artifacts": {
                "evaluation-manifest.json": manifest["sha256"],
                "detector-decision.json": decision["sha256"],
                "r2-input-roster.json": intake["sha256"],
                "runtime-source-manifest.json": snap["sha256"],
            },
        },
    )


@pytest.fixture
def graph(tmp_path):
    h = helpers()
    root, out = h.repository.__wrapped__(tmp_path)
    builder = h.module()
    h.qualification(builder, out)
    protocol = builder.prepare(root, frozen_at="2026-10-06T00:00:00Z")
    inventory_pin = builder.pin_file(out, "runtime-source-inventory.json")
    inventory = json.loads(builder.read_pin(out, inventory_pin))
    archive_path = out / "runtime-source.zip"
    with zipfile.ZipFile(archive_path, "w") as bundle:
        for name in inventory:
            bundle.write(root / name, name)
    archive_pin = builder.pin_file(out, "runtime-source.zip")
    h.save(
        out,
        "runtime-source-manifest.json",
        {
            "schema_version": "migration-ai-review-runtime-snapshot-v1",
            "inventory": inventory_pin.model_dump(),
            "archive": archive_pin.model_dump(),
            "files": [
                {"path": name, "sha256": digest} for name, digest in inventory.items()
            ],
        },
    )
    ids = []
    for case_pin in protocol.case_inputs:
        case = builder.AICaseSpec.model_validate_json(builder.read_pin(out, case_pin))
        ids.append(case.case_id)
        caps = []
        for role in builder.ROLES[:2]:
            name = f"requests/{case.case_id}/{role}"
            request = builder.AIReviewRequest.model_validate_json(
                (out / name / "request.json").read_bytes()
            )
            caps.append(
                h.capture(
                    builder,
                    out,
                    request,
                    name,
                    "2026-10-06T01:00:00Z",
                    "2026-10-06T02:00:00Z",
                )[0]
            )
        request = builder.adjudicator(
            case.case_id,
            root=root,
            captures=caps,
            materialized_at="2026-10-06T03:00:00Z",
        )
        name = f"requests/{case.case_id}/{builder.ROLES[2]}"
        caps.append(
            h.capture(
                builder,
                out,
                request,
                name,
                "2026-10-06T03:00:00Z",
                "2026-10-06T04:00:00Z",
            )[0]
        )
        for role, cap in zip(builder.ROLES, caps, strict=True):
            h.save(
                out,
                f"reviews/{case.case_id}/{role}/capture.json",
                json.loads(builder.read_pin(out, cap)),
            )
    prerequisites(root, ids)
    return root, out, ids


def change_response(graph, index, decision, unresolved=()):
    h = helpers()
    _root, out, ids = graph
    role = "ai_adjudicator"
    cap_path = f"reviews/{ids[index]}/{role}/capture.json"
    cap = json.loads((out / cap_path).read_bytes())
    final = json.loads((out / cap["exact_final"]["path"]).read_bytes())
    final["decision"] = decision
    final["unresolved_issues"] = list(unresolved)
    cap["exact_final"] = h.save(out, cap["exact_final"]["path"], final)
    events = json.loads((out / cap["host_events"]["path"]).read_bytes())
    events["final_sha256"] = cap["exact_final"]["sha256"]
    cap["host_events"] = h.save(out, cap["host_events"]["path"], events)
    h.save(out, cap_path, cap)


def test_missing_role_never_emits_canonical_roster(graph):
    root, out, ids = graph
    (out / f"reviews/{ids[-1]}/ai_adjudicator/capture.json").unlink()
    with pytest.raises(ValueError, match="36|missing"):
        load_script("promote_r2_review_roster").promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_subset_order_dispositions_and_deterministic_waves(graph):
    root, out, ids = graph
    change_response(graph, 1, "exclude")
    change_response(graph, 6, "include", ["open fixture issue"])
    module = load_script("promote_r2_review_roster")
    manifest = module.promote(root)
    accepted = [case for i, case in enumerate(ids) if i not in (1, 6)]
    rows = [
        json.loads(line)
        for line in (root / "data/migration/cases.jsonl").read_text().splitlines()
    ]
    assert [row["case_id"] for row in rows] == accepted
    assert manifest["generation_denominators"] == {
        "detector_led": 0,
        "oracle_assisted": 10,
        "combined": 10,
    }
    assert (root / "data/migration/detector-led-roster.jsonl").read_bytes() == b""
    wave = json.loads((root / "data/migration/wave-map.json").read_bytes())
    assert [len(w["case_ids"]) for w in wave["generation_waves"]] == [6, 4]
    assert [len(w["case_ids"]) for w in wave["validation_waves"]] == [8, 2]
    assert [
        case for w in wave["generation_waves"] for case in w["case_ids"]
    ] == accepted
    assert module.promote(root) == manifest
    reasons = json.loads((out / "disposition-reasons.json").read_bytes())
    assert reasons["cases"][6]["responses"][2]["unresolved_issues"] == [
        "open fixture issue"
    ]


def test_reused_host_context_is_rejected_after_repins(graph):
    h = helpers()
    root, out, ids = graph
    path = f"reviews/{ids[1]}/ai_primary/capture.json"
    cap = json.loads((out / path).read_bytes())
    event = json.loads((out / cap["host_events"]["path"]).read_bytes())
    other_cap = json.loads(
        (out / f"reviews/{ids[0]}/ai_primary/capture.json").read_bytes()
    )
    other_event = json.loads((out / other_cap["host_events"]["path"]).read_bytes())
    event["session_id"] = other_event["session_id"]
    cap["host_events"] = h.save(out, cap["host_events"]["path"], event)
    h.save(out, path, cap)
    with pytest.raises(ValueError, match="reused"):
        load_script("promote_r2_review_roster").promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_exact_evidence_tamper_and_runtime_change_fail_closed(graph):
    root, out, ids = graph
    source = next((out / "inputs" / ids[0] / "sources").iterdir())
    source.write_bytes(b"tampered source")
    with pytest.raises(ValueError, match="checksum"):
        load_script("promote_r2_review_roster").promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_zero_accepted_is_explicit_not_evaluable(graph):
    root, _out, ids = graph
    for index in range(len(ids)):
        change_response(graph, index, "exclude")
    manifest = load_script("promote_r2_review_roster").promote(root)
    assert manifest["status"] == "NOT_EVALUABLE"
    assert manifest["generation_denominators"]["combined"] == 0
    assert (root / "data/migration/cases.jsonl").read_bytes() == b""


def capture_amendment(graph, *, changed_path="scripts/seal_r2_review_session.py"):
    h = helpers()
    root, out, _ids = graph
    promoter = load_script("promote_r2_review_roster")
    original_inventory = promoter.pin(out, "runtime-source-inventory.json")
    original_snapshot = promoter.pin(out, "runtime-source-manifest.json")
    old_inventory = promoter.json_pin(out, original_inventory)
    changed = root / changed_path
    changed.write_bytes(
        changed.read_bytes() + b"# exact prior citation gate correction\n"
    )
    inventory = {
        name: h.hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in old_inventory
    }
    inventory_pin = h.save(
        out, "capture-amendment/runtime-source-inventory.json", inventory
    )
    archive_path = out / "capture-amendment/runtime-source.zip"
    with zipfile.ZipFile(archive_path, "w") as bundle:
        for name in inventory:
            bundle.write(root / name, name)
    archive_pin = promoter.pin(out, "capture-amendment/runtime-source.zip")
    snapshot_pin = h.save(
        out,
        "capture-amendment/runtime-source-manifest.json",
        {
            "schema_version": "migration-ai-review-runtime-snapshot-v1",
            "inventory": inventory_pin,
            "archive": archive_pin.model_dump(),
            "files": [{"path": name, "sha256": sha} for name, sha in inventory.items()],
        },
    )
    protocol_pin = promoter.pin(out, "review-protocol.json")
    protocol = promoter.AIReviewProtocol.model_validate_json(
        promoter.read(out, protocol_pin)
    )
    request_entries = []
    for request_path in sorted((out / "requests").rglob("request.json")):
        request_pin = promoter.pin(out, request_path.relative_to(out).as_posix())
        request = promoter.AIReviewRequest.model_validate_json(
            promoter.read(out, request_pin)
        )
        request_entries.append(
            {
                "request": request_pin.model_dump(),
                "request_sha256": promoter.model_sha256(request),
            }
        )
    amendment = {
        "schema_version": "migration-ai-review-capture-amendment-v1",
        "reason": "exact_prior_final_citation_gate_correction",
        "semantic_decisions_unchanged": True,
        "request_input_schema_hashes_unchanged": True,
        "protocol": protocol_pin.model_dump(),
        "original_runtime_inventory": original_inventory.model_dump(),
        "original_runtime_snapshot_manifest": original_snapshot.model_dump(),
        "amended_runtime_inventory": inventory_pin,
        "amended_runtime_snapshot_manifest": snapshot_pin,
        "changed_sources": [
            {
                "path": changed_path,
                "old_sha256": old_inventory[changed_path],
                "new_sha256": inventory[changed_path],
            }
        ],
        "unchanged_bindings": {
            "protocol": protocol_pin.model_dump(),
            "response_schema_sha256": protocol.response_schema_sha256,
            "case_inputs": [p.model_dump() for p in protocol.case_inputs],
            "requests": request_entries,
        },
    }
    h.save(out, "review-capture-amendment.json", amendment)
    return promoter, protocol, amendment


def test_amendment_preserves_original_archive_and_records_both_runtimes(graph):
    root, out, _ids = graph
    originals = {
        name: (out / name).read_bytes()
        for name in (
            "review-protocol.json",
            "runtime-source-inventory.json",
            "runtime-source-manifest.json",
            "runtime-source.zip",
        )
    }
    promoter, protocol, _amendment = capture_amendment(graph)
    original, amended, amendment = promoter.review_runtime(root, out, protocol)
    assert original.path == "runtime-source-manifest.json"
    assert amended.path == "capture-amendment/runtime-source-manifest.json"
    assert amendment.path == "review-capture-amendment.json"
    assert {name: (out / name).read_bytes() for name in originals} == originals
    manifest = promoter.promote(root)
    assert (
        manifest["source_intake"]["review_capture_amendment"]["sha256"]
        == amendment.sha256
    )
    assert (
        "original_protocol_runtime_preserved"
        in manifest["source_intake"]["runtime_provenance"]
    )


@pytest.mark.parametrize(
    "defect",
    [
        "reason",
        "semantics",
        "schema",
        "request_hash",
        "missing_blind_request",
        "source_accounting",
        "original_inventory",
        "original_archive",
        "amended_archive",
        "current_source",
    ],
)
def test_capture_amendment_cannot_hide_tamper_or_broaden_scope(graph, defect):
    h = helpers()
    root, out, _ids = graph
    promoter, protocol, amendment = capture_amendment(graph)
    if defect == "reason":
        amendment["reason"] = "improve review decisions"
    elif defect == "semantics":
        amendment["semantic_decisions_unchanged"] = False
    elif defect == "schema":
        amendment["unchanged_bindings"]["response_schema_sha256"] = "f" * 64
    elif defect == "request_hash":
        amendment["unchanged_bindings"]["requests"][0]["request_sha256"] = "f" * 64
    elif defect == "missing_blind_request":
        amendment["unchanged_bindings"]["requests"] = [
            entry
            for entry in amendment["unchanged_bindings"]["requests"]
            if not entry["request"]["path"].endswith("/ai_primary/request.json")
        ]
    elif defect == "source_accounting":
        amendment["changed_sources"] = []
    elif defect == "original_inventory":
        (out / "runtime-source-inventory.json").write_bytes(b"{}\n")
    elif defect == "original_archive":
        (out / "runtime-source.zip").write_bytes(b"corrupt")
    elif defect == "amended_archive":
        (out / "capture-amendment/runtime-source.zip").write_bytes(b"corrupt")
    else:
        (root / "scripts/seal_r2_review_session.py").write_bytes(
            b"unfrozen later implementation"
        )
    h.save(out, "review-capture-amendment.json", amendment)
    with pytest.raises(ValueError):
        promoter.review_runtime(root, out, protocol)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_amendment_rejects_rehashed_unapproved_runtime_source(graph):
    root, out, _ids = graph
    promoter, protocol, _amendment = capture_amendment(
        graph, changed_path="src/demo.py"
    )
    with pytest.raises(ValueError, match="unauthorized runtime source"):
        promoter.review_runtime(root, out, protocol)


def test_amendment_can_precede_materializing_remaining_adjudicator_requests(graph):
    h = helpers()
    root, out, _ids = graph
    promoter, protocol, amendment = capture_amendment(graph)
    amendment["unchanged_bindings"]["requests"] = [
        entry
        for entry in amendment["unchanged_bindings"]["requests"]
        if not entry["request"]["path"].endswith("/ai_adjudicator/request.json")
    ]
    h.save(out, "review-capture-amendment.json", amendment)
    promoter.review_runtime(root, out, protocol)


def test_adjudicator_can_cite_both_exact_prior_finals(graph):
    h = helpers()
    root, out, ids = graph
    cap_path = f"reviews/{ids[0]}/ai_adjudicator/capture.json"
    cap = json.loads((out / cap_path).read_bytes())
    request = json.loads((out / cap["request"]["path"]).read_bytes())
    final = json.loads((out / cap["exact_final"]["path"]).read_bytes())
    final["evidence"].extend(request["prior_responses"])
    cap["exact_final"] = h.save(out, cap["exact_final"]["path"], final)
    events = json.loads((out / cap["host_events"]["path"]).read_bytes())
    events["final_sha256"] = cap["exact_final"]["sha256"]
    cap["host_events"] = h.save(out, cap["host_events"]["path"], events)
    h.save(out, cap_path, cap)
    assert (
        load_script("promote_r2_review_roster").promote(root)[
            "generation_denominators"
        ]["combined"]
        == 12
    )


def test_partial_prior_citation_still_rejected(graph):
    h = helpers()
    root, out, ids = graph
    cap_path = f"reviews/{ids[0]}/ai_adjudicator/capture.json"
    cap = json.loads((out / cap_path).read_bytes())
    request = json.loads((out / cap["request"]["path"]).read_bytes())
    final = json.loads((out / cap["exact_final"]["path"]).read_bytes())
    final["evidence"].append(request["prior_responses"][0])
    cap["exact_final"] = h.save(out, cap["exact_final"]["path"], final)
    events = json.loads((out / cap["host_events"]["path"]).read_bytes())
    events["final_sha256"] = cap["exact_final"]["sha256"]
    cap["host_events"] = h.save(out, cap["host_events"]["path"], events)
    h.save(out, cap_path, cap)
    with pytest.raises(ValueError, match="response evidence"):
        load_script("promote_r2_review_roster").promote(root)
