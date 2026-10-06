"""Revision promotion accounts for 48 chains and accepts only fresh repairs."""

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def revision_graph(tmp_path):
    old_tests = load("tests/test_r2_review_promotion.py")
    root, out, ids = old_tests.graph.__wrapped__(tmp_path)
    h = old_tests.helpers()
    promoter = load("scripts/promote_r2_review_revisions.py")
    for index in range(12):
        old_tests.change_response((root, out, ids), index, "exclude")
    original = promoter.collect(out, "review-protocol.json", "", ids, (set(), set()))
    h.save(
        out,
        "original-review-receipt.json",
        {
            "schema_version": "migration-ai-original-review-receipt-v1",
            "status": "COMPLETE_36_REVIEWED_NOT_GENERATION_ELIGIBLE",
            "terminal_status": "ALL_ORIGINAL_REVIEWS_TERMINAL",
            "capture_count": 36,
            "protocol": original[0].model_dump(),
            "reviews": original[5],
            "accepted_original_case_ids": [],
        },
    )
    for name in promoter.NEW_SCRIPTS:
        (root / name).write_text("pass\n")
    inventory = promoter.BUILDER.inventory(root)
    inventory.update(
        {
            name: h.hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in promoter.NEW_SCRIPTS
        }
    )
    invpin = h.save(out, "revisions/runtime-source-inventory.json", inventory)
    archive = out / "revisions/runtime-source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in inventory:
            bundle.write(root / name, name)
    h.save(
        out,
        "revisions/runtime-source-manifest.json",
        {
            "schema_version": "migration-ai-review-runtime-snapshot-v1",
            "inventory": invpin,
            "archive": promoter.pin(out, "revisions/runtime-source.zip").model_dump(),
            "files": [{"path": name, "sha256": sha} for name, sha in inventory.items()],
        },
    )
    cases = []
    by_id = {case.case_id: case for case in original[2]}
    rows = []
    for case_id in promoter.REVISION_IDS:
        fixture_pin = next(
            p
            for p in by_id[case_id].fixture_evidence
            if p.path.endswith("/fixtures.json")
        )
        fixtures = promoter.json_pin(out, fixture_pin)
        rows.append(
            {
                "case_id": case_id,
                "frozen_sources": fixtures["frozen_sources"],
                "fixture_protocol_sha256": promoter.helper(
                    "prepare_r2_review_revisions"
                )
                .FixtureProtocol.model_validate(fixtures)
                .sha256,
                "observations": [
                    {
                        "check_id": check,
                        "log": json.dumps(
                            {
                                "fixtures": [
                                    {
                                        "fixture_id": f["fixture_id"],
                                        "actual_stdout": "observed",
                                        "expected_stdout": f["expected_stdout"],
                                        "run_result": {
                                            "compiled_ok": True,
                                            "exit_code": 0,
                                            "timed_out": False,
                                            "stdout": "observed",
                                        },
                                    }
                                    for f in group
                                ]
                            }
                        ),
                    }
                    for check, group in fixtures["checks"].items()
                ],
            }
        )
    qualification = h.save(
        out, "revisions/revised-original-baseline-qualification.json", {"cases": rows}
    )
    for case_id in promoter.REVISION_IDS:
        case = by_id[case_id].model_dump(mode="json")
        case["intended_behavior"]["description"] += " Revised bounded claim."
        fixture_pin = next(
            p
            for p in by_id[case_id].fixture_evidence
            if p.path.endswith("/fixtures.json")
        )
        original_pin = original[1].case_inputs[ids.index(case_id)]
        observation = h.save(
            out,
            f"revisions/inputs/{case_id}/revised-original-observations.json",
            {
                "schema_version": "migration-revised-original-baseline-observations-v1",
                "qualification": qualification,
                "fixtures": fixture_pin.model_dump(),
                "original_case_input": original_pin.model_dump(),
                "case": next(row for row in rows if row["case_id"] == case_id),
            },
        )
        case["fixture_evidence"].append(observation)
        cases.append(h.save(out, f"revisions/inputs/{case_id}/case-input.json", case))
    protocol = original[1].model_copy(
        update={
            "frozen_at": promoter.BUILDER.timestamp("2026-10-06T05:00:00Z"),
            "case_inputs": tuple(
                promoter.OLD.MigrationEvidencePin.model_validate(p) for p in cases
            ),
            "runtime_source_sha256": invpin["sha256"],
        }
    )
    pp = h.save(out, "revisions/review-protocol.json", protocol.model_dump(mode="json"))
    for case_id, case_pin in zip(
        promoter.REVISION_IDS, protocol.case_inputs, strict=True
    ):
        finals = []
        for role in promoter.ROLES:
            name = f"revisions/requests/{case_id}/{role}"
            prompt = h.save(
                out, name + "/prompt.md", b"Review visible source and clause"
            )
            request = promoter.BUILDER.AIReviewRequest(
                case_id=case_id,
                reviewer=next(r for r in protocol.reviewers if r.role == role),
                protocol=pp,
                case_input=case_pin,
                prompt=prompt,
                response_schema_sha256=protocol.response_schema_sha256,
                prior_responses=finals if role == promoter.ROLES[2] else (),
            )
            h.save(out, name + "/request.json", request.model_dump(mode="json"))
            cap = h.capture(
                promoter.BUILDER,
                out,
                request,
                name,
                "2026-10-06T08:00:00Z"
                if role == promoter.ROLES[2]
                else "2026-10-06T06:00:00Z",
                "2026-10-06T09:00:00Z"
                if role == promoter.ROLES[2]
                else "2026-10-06T07:00:00Z",
            )
            finals.append(promoter.OLD.MigrationEvidencePin.model_validate(cap[2]))
            h.save(
                out,
                f"revisions/reviews/{case_id}/{role}/capture.json",
                json.loads(promoter.read(out, cap[0])),
            )
    return promoter, root, out, h


def test_revision_subset_order_accounting_and_waves(revision_graph):
    promoter, root, out, _h = revision_graph
    manifest = promoter.promote(root)
    assert "scripts/wsl_migration_backend.py" in promoter.NEW_SCRIPTS
    assert manifest["accepted_case_ids"] == list(promoter.REVISION_IDS)
    assert manifest["generation_denominators"] == {
        "detector_led": 0,
        "oracle_assisted": 4,
        "combined": 4,
    }
    assert len(manifest["original_excluded_case_ids"]) == 12
    assert len(manifest["excluded_case_ids"]) == 8
    waves = json.loads((root / "data/migration/wave-map.json").read_bytes())
    assert [w["case_ids"] for w in waves["generation_waves"]] == [
        list(promoter.REVISION_IDS)
    ]
    assert [w["case_ids"] for w in waves["validation_waves"]] == [
        list(promoter.REVISION_IDS)
    ]
    assert (
        json.loads((out / "original-review-disposition.json").read_bytes())["status"]
        == "NOT_EVALUABLE"
    )
    assert promoter.promote(root) == manifest


def test_partial_revision_does_not_write_canonical(revision_graph):
    promoter, root, out, _h = revision_graph
    (
        out
        / f"revisions/reviews/{promoter.REVISION_IDS[0]}/ai_adjudicator/capture.json"
    ).unlink()
    with pytest.raises(ValueError, match="missing role"):
        promoter.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_reused_original_context_rejected(revision_graph):
    promoter, root, out, h = revision_graph
    path = f"revisions/reviews/{promoter.REVISION_IDS[0]}/ai_primary/capture.json"
    capture = json.loads((out / path).read_bytes())
    event = json.loads(promoter.read(out, capture["host_events"]))
    original = json.loads(
        (
            out / f"reviews/{promoter.REVISION_IDS[0]}/ai_primary/capture.json"
        ).read_bytes()
    )
    event["session_id"] = json.loads(promoter.read(out, original["host_events"]))[
        "session_id"
    ]
    capture["host_events"] = h.save(out, capture["host_events"]["path"], event)
    h.save(out, path, capture)
    with pytest.raises(ValueError, match="reused"):
        promoter.promote(root)


def test_negative_revision_disposition_is_retained(revision_graph):
    promoter, root, out, h = revision_graph
    path = f"revisions/reviews/{promoter.REVISION_IDS[1]}/ai_adjudicator/capture.json"
    capture = json.loads((out / path).read_bytes())
    response = json.loads(promoter.read(out, capture["exact_final"]))
    response["unresolved_issues"] = ["fixture remains ambiguous"]
    capture["exact_final"] = h.save(out, capture["exact_final"]["path"], response)
    event = json.loads(promoter.read(out, capture["host_events"]))
    event["final_sha256"] = capture["exact_final"]["sha256"]
    capture["host_events"] = h.save(out, capture["host_events"]["path"], event)
    h.save(out, path, capture)
    manifest = promoter.promote(root)
    assert manifest["revision_excluded_case_ids"] == [promoter.REVISION_IDS[1]]
    assert manifest["accepted_case_ids"] == [
        case for case in promoter.REVISION_IDS if case != promoter.REVISION_IDS[1]
    ]
    assert manifest["generation_denominators"]["combined"] == 3


@pytest.mark.parametrize("defect", ["runtime_source", "archive", "order", "receipt"])
def test_source_archive_order_and_receipt_fail_closed(revision_graph, defect):
    promoter, root, out, h = revision_graph
    if defect == "runtime_source":
        (root / promoter.NEW_SCRIPTS[0]).write_bytes(b"unfrozen")
    elif defect == "archive":
        (out / "revisions/runtime-source.zip").write_bytes(b"corrupt")
    elif defect == "order":
        protocol = json.loads((out / "revisions/review-protocol.json").read_bytes())
        protocol["case_inputs"].reverse()
        h.save(out, "revisions/review-protocol.json", protocol)
    else:
        receipt = json.loads((out / "original-review-receipt.json").read_bytes())
        receipt["reviews"].pop()
        h.save(out, "original-review-receipt.json", receipt)
    with pytest.raises(ValueError):
        promoter.promote(root)
    assert not (root / "data/migration/cases.jsonl").exists()


def test_scope_and_source_identity_cannot_expand(revision_graph):
    promoter, _root, out, _h = revision_graph
    protocol = promoter.AIReviewProtocol.model_validate_json(
        (out / "review-protocol.json").read_bytes()
    )
    case = promoter.AICaseSpec.model_validate_json(
        promoter.read(out, protocol.case_inputs[0])
    )
    changed = case.model_copy(update={"source_bundle_group": "replacement"})
    with pytest.raises(ValueError, match="identity/source"):
        promoter.check_revision(case, changed)
    scope = case.allowed_source_scope[0].model_copy(
        update={"line_spans": ((1, 999999),)}
    )
    with pytest.raises(ValueError, match="scope expands"):
        promoter.check_revision(
            case, case.model_copy(update={"allowed_source_scope": (scope,)})
        )
