"""Provider-free generation freeze gates; review-chain gates live separately."""

import json
from pathlib import Path

import pytest

from scripts import prepare_r2_stage_generation as B
from scripts.stage_review_contracts import StageCanonicalCase

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    review = tmp_path / "data/migration/ai-review"
    case_raw = json.loads(
        (
            ROOT
            / "data/migration/ai-review/revisions/inputs/migration_075075/case-input.json"
        ).read_bytes()
    )
    case_raw.pop("schema_version")
    case = StageCanonicalCase(
        **case_raw,
        review_protocol_sha256="d" * 64,
        review_evidence_sha256="e" * 64,
        review_evidence={"path": "unused-review.json", "sha256": "e" * 64},
    )
    for evidence in (
        *case.source_evidence,
        case.regulation_evidence,
        *case.fixture_evidence,
    ):
        destination = review / evidence.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            (ROOT / "data/migration/ai-review" / evidence.path).read_bytes()
        )
    for path in (*B.NEW_RUNTIME, "scripts/wsl_migration_backend.py"):
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / path).read_bytes())
    inventory = {
        "scripts/wsl_migration_backend.py": B.pin(
            tmp_path, "scripts/wsl_migration_backend.py"
        )["sha256"]
    }
    inv = review / "stage-review/runtime-source-inventory.json"
    inv.parent.mkdir(parents=True)
    inv.write_bytes(B.encoded(inventory))
    for name in (
        "evaluation-manifest.json",
        "detector-decision.json",
        "r2-input-roster.json",
    ):
        dest = tmp_path / "data/eval/m4" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / "data/eval/m4" / name).read_bytes())
    migration = tmp_path / "data/migration"
    (migration / "cases.jsonl").write_text(
        case.model_dump_json() + "\n", encoding="utf-8"
    )
    (migration / "oracle-assisted-roster.jsonl").write_bytes(
        (migration / "cases.jsonl").read_bytes()
    )
    (migration / "detector-led-roster.jsonl").write_bytes(b"")
    for name in ("review-protocol.json", "disposition.json", "wave-map.json"):
        (migration / name).write_bytes(b"{}")
    manifest = {
        "schema_version": "r2-stage-reviewed-roster-manifest-v1",
        "accepted_case_ids": [case.case_id],
        "review_evidence_root": "data/migration/ai-review",
        "generation_denominators": {
            "detector_led": 0,
            "oracle_assisted": 1,
            "combined": 1,
        },
    }
    for key, name in (
        ("canonical_roster", "cases.jsonl"),
        ("oracle_assisted_roster", "oracle-assisted-roster.jsonl"),
        ("detector_led_roster", "detector-led-roster.jsonl"),
        ("review_protocol", "review-protocol.json"),
        ("disposition", "disposition.json"),
        ("wave_map", "wave-map.json"),
    ):
        manifest[key] = B.pin(tmp_path, "data/migration/" + name)
    (migration / "roster-manifest.json").write_bytes(B.encoded(manifest))
    monkeypatch.setattr(B, "load_stage_canonical_roster", lambda *a, **k: (case,))
    # Poisoning candidate oracle inputs must not affect the fresh finding.
    (review / "oracle-prediction.json").write_text(
        "SECRET_MUTATION_RATIONALE", encoding="utf-8"
    )
    return tmp_path, case


def test_freeze_distinct_purposes_replay_and_idempotence(tree):
    root, case = tree
    manifest = B.prepare(root, frozen_at="2026-10-07T00:00:00Z", cli_version="test-cli")
    assert len(manifest["requests"]) == 2
    assert set(manifest["official_run_keys"]).isdisjoint(
        manifest["qualification_run_keys"]
    )
    assert manifest["qualification_disclosure"]["reused_case_id"] == case.case_id
    assert (
        manifest["qualification_disclosure"]["official_denominator_contribution"] == 0
    )
    assert B.prepare(root, cli_version="test-cli") == manifest
    stages = [e["staging_root"] for e in manifest["requests"]]
    assert len(set(stages)) == 2
    for entry in manifest["requests"]:
        prompt = (root / entry["prompt"]["path"]).read_text()
        assert "SECRET_MUTATION" not in prompt and '"labels"' not in prompt
        assert "fixture_evidence" not in prompt and "review_evidence" not in prompt
        assert {p.name for p in (root / entry["staging_root"]).iterdir()} == {
            s.path for s in case.frozen_sources
        }


@pytest.mark.parametrize("damage", ["runtime", "staging", "launch", "request"])
def test_freeze_preflight_rejects_mutation(tree, damage):
    root, _ = tree
    manifest = B.prepare(root, cli_version="test-cli")
    entry = manifest["requests"][0]
    paths = {
        "runtime": B.NEW_RUNTIME[0],
        "staging": entry["source_pins"][0]["path"],
        "launch": entry["launch"]["path"],
        "request": entry["request"]["path"],
    }
    path = root / paths[damage]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        B.sealer.check_freeze(
            root=root,
            freeze_path=root / "data/migration/generation/runtime-manifest.json",
            request_path=root / entry["request"]["path"],
            launch_path=root / entry["launch"]["path"],
        )


def test_baseline_failure_is_not_relabelled(tree):
    root, case = tree
    evidence = next(
        p
        for p in case.fixture_evidence
        if p.path.endswith("revised-original-observations.json")
    )
    path = root / "data/migration/ai-review" / evidence.path
    value = json.loads(path.read_bytes())
    value["case"]["observations"][0]["status"] = "fail"
    path.write_bytes(B.encoded(value))
    changed = case.model_copy(
        update={
            "fixture_evidence": tuple(
                p.model_copy(update={"sha256": B.sealer.digest(path.read_bytes())})
                if p == evidence
                else p
                for p in case.fixture_evidence
            )
        }
    )
    with pytest.raises(ValueError, match="baseline must"):
        B.fresh_finding(changed, root / "data/migration/ai-review")


def test_intake_pin_and_denominators_fail_closed(tree):
    root, _ = tree
    path = root / "data/migration/roster-manifest.json"
    value = json.loads(path.read_bytes())
    value["generation_denominators"]["combined"] = 2
    path.write_bytes(B.encoded(value))
    with pytest.raises(ValueError, match="denominators"):
        B.prepare(root, cli_version="test-cli")


@pytest.mark.parametrize("case_id", ["075075", "255807", "191889", "345332"])
def test_all_current_candidates_fresh_finding_from_evidence(case_id):
    review = ROOT / "data/migration/ai-review"
    payload = json.loads(
        (review / f"revisions/inputs/migration_{case_id}/case-input.json").read_bytes()
    )
    payload.pop("schema_version")
    case = StageCanonicalCase(
        **payload,
        review_protocol_sha256="d" * 64,
        review_evidence_sha256="e" * 64,
        review_evidence={"path": "unused.json", "sha256": "e" * 64},
    )
    finding = B.fresh_finding(case, review)
    assert finding.prediction.instance_id == case.instance_id
    assert finding.verifier_tier == "executed"
    assert [l.line_span for l in finding.prediction.code_locus.loci] == [
        span for scope in case.allowed_source_scope for span in scope.line_spans
    ]
    if case_id in {"075075", "255807"}:
        assert finding.prediction.target_path == "cutoff"


def test_write_refuses_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        B.write(tmp_path, tmp_path.parent / "outside-generation.json", b"never written")
