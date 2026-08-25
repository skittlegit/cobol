from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.t6_pair_correction import (
    PairCorrectionAuditManifest,
)
from cobol_archaeologist.benchmark.t6_replacement import (
    REPLACEMENT_ORDER,
    ReplacementBridgeManifest,
    ReplacementCompletion,
    ReplacementMultiBatchLedgerManifest,
    ReplacementPlanItem,
    classify_replacement_final,
    validate_replacement_batch_ledger,
    validate_replacement_bridge,
    validate_replacement_completion,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin

ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path(
    "data/benchmark/t6-v2/replacements/evidence/"
    "review-v4-ledger/batch-ledger-manifest.json"
)
COORDINATOR_REL = Path(
    "data/benchmark/t6-v2/replacements/"
    "review-v4/prompt-manifest.coordinator-private.json"
)
TRANSCRIPT_REL = Path(
    "data/benchmark/t6-v2/replacements/review-v4/transcript.jsonl"
)
LEDGER_SHA256 = "39ca0e73a3a7291330f637f0705464a686b7828bca2fcca1eb9bb7d5d74953e8"
COORDINATOR_SHA256 = (
    "072373e6dccf11982f54fc027e5491cb5e1bd3d8ed2b570b4293cb4fee3518e0"
)
PLAN_SHA256 = "efb8c2f59e8b225f30b383bdf17ec59286c38517908299ada5804b2271f285d8"
TRANSCRIPT_SHA256 = (
    "479934ed27c99060ca9319fb572e2f3b6f26624794684c4505e3c9f81650f51f"
)
CORRECTION_SHA256 = (
    "f65ed3046e0ce09ad673b173dcb5a205491dd4778ee0d4449e24bb7b983a43c5"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    return ArtifactPin(
        path=path.relative_to(root).as_posix(),
        sha256=_sha(path),
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load_plans(root: Path, coordinator: dict[str, object]) -> list[ReplacementPlanItem]:
    path = root / coordinator["replacement_plan"]["path"]
    return [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


def _copy_ledger_graph(tmp_path: Path) -> Path:
    ledger = json.loads((ROOT / LEDGER_REL).read_text(encoding="utf-8"))
    coordinator = json.loads((ROOT / COORDINATOR_REL).read_text(encoding="utf-8"))
    correction_path = ROOT / ledger["correction_audit"]["path"]
    correction = PairCorrectionAuditManifest.model_validate_json(
        correction_path.read_text(encoding="utf-8")
    )
    plans = _load_plans(ROOT, coordinator)
    relatives = {
        LEDGER_REL,
        COORDINATOR_REL,
        Path(ledger["replacement_plan"]["path"]),
        Path(ledger["transcript"]["path"]),
        Path(ledger["correction_audit"]["path"]),
        Path(correction.correction_plan.path),
        *(Path(call["prompt"]["path"]) for call in coordinator["calls"]),
        *(Path(plan.source.path) for plan in plans),
    }
    for relative in relatives:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path / LEDGER_REL


def _repin_ledger_artifact(
    root: Path, ledger_path: Path, field: str, artifact: Path
) -> None:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger[field] = _pin(root, artifact).model_dump(mode="json")
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_frozen_v4_ledger_has_exact_pins_counts_and_classification() -> None:
    ledger_path = ROOT / LEDGER_REL
    assert _sha(ledger_path) == LEDGER_SHA256
    ledger, plans, accepted = validate_replacement_batch_ledger(
        root=ROOT, ledger_path=ledger_path
    )
    assert ledger.coordinator_manifest.sha256 == COORDINATOR_SHA256
    assert ledger.replacement_plan.sha256 == PLAN_SHA256
    assert ledger.transcript.sha256 == TRANSCRIPT_SHA256
    assert ledger.correction_audit.sha256 == CORRECTION_SHA256
    assert ledger.outcome_counts == {
        "validated_flip": 4,
        "rejected_nonflip": 0,
        "rejected_invalid_identity": 1,
        "rejected_schema": 1,
    }
    assert [plan.replacement_id for plan, _ in accepted] == [
        "t6v2-replacement-01",
        "t6v2-replacement-03",
        "t6v2-replacement-04",
        "t6v2-replacement-06",
    ]
    calls = _read_jsonl(ROOT / TRANSCRIPT_REL)
    outcomes = [
        classify_replacement_final(
            plan=plan,
            final=call["final_message"].encode("utf-8"),
        )[0]
        for plan, call in zip(plans, calls, strict=True)
    ]
    assert outcomes == [
        "validated_flip",
        "rejected_invalid_identity",
        "validated_flip",
        "validated_flip",
        "rejected_schema",
        "validated_flip",
    ]
    for call, item in zip(calls, ledger.items, strict=True):
        prompt = base64.b64decode(item.attempt.prompt_utf8_base64, validate=True)
        final = base64.b64decode(
            item.attempt.final_message_utf8_base64, validate=True
        )
        assert hashlib.sha256(prompt).hexdigest() == item.attempt.prompt_sha256
        assert len(prompt) == item.attempt.prompt_utf8_length
        assert final == call["final_message"].encode("utf-8")
        assert hashlib.sha256(final).hexdigest() == item.attempt.final_message_sha256
        assert len(final) == item.attempt.final_message_utf8_length


def test_cross_program_citation_line_must_belong_to_named_program() -> None:
    coordinator = json.loads((ROOT / COORDINATOR_REL).read_text(encoding="utf-8"))
    plan = _load_plans(ROOT, coordinator)[4]
    completion = ReplacementCompletion.model_validate(
        {
            "review_call_id": plan.replacement_call_id,
            "sides": [
                {
                    "review_item_id": plan.sides[0].review_item_id,
                    "review_response": {
                        "decision": "include",
                        "drift_type": "D7_conformant",
                        "line_level": [],
                        "rationale": "Conformant old threshold.",
                        "uncertainty_notes": None,
                    },
                },
                {
                    "review_item_id": plan.sides[1].review_item_id,
                    "review_response": {
                        "decision": "include",
                        "drift_type": "D1_stale_threshold",
                        "line_level": [
                            {
                                "program": "BOH4C3",
                                "line": 12,
                                "source_alias": plan.sides[1].source_alias,
                            }
                        ],
                        "rationale": "The threshold is stale.",
                        "uncertainty_notes": None,
                    },
                },
            ],
        }
    )
    assert "CALL 'BOH4C3'" in plan.shared_source_text.splitlines()[11]
    with pytest.raises(ValueError, match="citation"):
        validate_replacement_completion(plan, completion)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("freeze_version", "v3"),
        ("model_id", "gpt-5.5"),
        ("reasoning_effort", "high"),
        ("fork_turns", "all"),
        ("tools_authorized", 1),
        ("prior_pair_context_included", True),
    ),
)
def test_coordinator_control_field_tampering_fails_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    ledger_path = _copy_ledger_graph(tmp_path)
    coordinator_path = tmp_path / COORDINATOR_REL
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    coordinator[field] = value
    coordinator_path.write_text(
        json.dumps(coordinator, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _repin_ledger_artifact(
        tmp_path, ledger_path, "coordinator_manifest", coordinator_path
    )
    with pytest.raises(ValueError, match="coordinator"):
        validate_replacement_batch_ledger(root=tmp_path, ledger_path=ledger_path)


@pytest.mark.parametrize("mutation", ("task", "final", "order"))
def test_re_pinned_transcript_tampering_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    ledger_path = _copy_ledger_graph(tmp_path)
    transcript_path = tmp_path / TRANSCRIPT_REL
    calls = _read_jsonl(transcript_path)
    if mutation == "task":
        calls[0]["task_identity"] += "-tampered"
    elif mutation == "final":
        calls[0]["final_message"] += " "
    else:
        calls[0], calls[1] = calls[1], calls[0]
    _write_jsonl(transcript_path, calls)
    _repin_ledger_artifact(tmp_path, ledger_path, "transcript", transcript_path)
    with pytest.raises(ValueError):
        validate_replacement_batch_ledger(root=tmp_path, ledger_path=ledger_path)


def test_prompt_byte_tampering_fails_closed(tmp_path: Path) -> None:
    ledger_path = _copy_ledger_graph(tmp_path)
    coordinator = json.loads(
        (tmp_path / COORDINATOR_REL).read_text(encoding="utf-8")
    )
    prompt_path = tmp_path / coordinator["calls"][0]["prompt"]["path"]
    prompt_path.write_bytes(prompt_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="prompt pin changed"):
        validate_replacement_batch_ledger(root=tmp_path, ledger_path=ledger_path)


def _write_multibatch_bridge(
    root: Path, ledger_path: Path, *, duplicate_batch: bool
) -> Path:
    ledger, plans, _ = validate_replacement_batch_ledger(
        root=root, ledger_path=ledger_path
    )
    correction_path = root / ledger.correction_audit.path
    correction = PairCorrectionAuditManifest.model_validate_json(
        correction_path.read_text(encoding="utf-8")
    )
    batch_pin = _pin(root, ledger_path)
    aggregate = ReplacementMultiBatchLedgerManifest(
        schema_version="1",
        ledger_variant="replacement_multi_batch_v1",
        finalized=True,
        batch_ledgers=(batch_pin, batch_pin) if duplicate_batch else (batch_pin,),
        required_rejected_pair_order=correction.pair_order,
        accepted_replacement_order=REPLACEMENT_ORDER,
        accepted_count=6,
    )
    aggregate_path = root / "aggregate.json"
    aggregate_path.write_text(aggregate.model_dump_json(), encoding="utf-8")
    projected_plan = root / "projected-plan.jsonl"
    projected_response = root / "projected-response.jsonl"
    projected_plan.write_text("", encoding="utf-8")
    projected_response.write_text("", encoding="utf-8")
    bridge = ReplacementBridgeManifest(
        schema_version="1",
        finalized=True,
        projection="replacement_multibatch_to_t6_pool_v1",
        replacement_audit=_pin(root, aggregate_path),
        replacement_plan=_pin(root, projected_plan),
        replacement_responses=_pin(root, projected_response),
        replacement_order=REPLACEMENT_ORDER,
        review_item_members={
            plan.replacement_id: tuple(side.review_item_id for side in plan.sides)
            for plan in plans
        },
    )
    bridge_path = root / "bridge.json"
    bridge_path.write_text(bridge.model_dump_json(), encoding="utf-8")
    return bridge_path


def test_multibatch_projection_rejects_incomplete_accepted_scope(
    tmp_path: Path,
) -> None:
    ledger_path = _copy_ledger_graph(tmp_path)
    bridge_path = _write_multibatch_bridge(
        tmp_path, ledger_path, duplicate_batch=False
    )
    with pytest.raises(ValueError, match="exact rejected scope"):
        validate_replacement_bridge(root=tmp_path, bridge_path=bridge_path)


def test_multibatch_projection_rejects_duplicate_batch_coverage(
    tmp_path: Path,
) -> None:
    ledger_path = _copy_ledger_graph(tmp_path)
    bridge_path = _write_multibatch_bridge(
        tmp_path, ledger_path, duplicate_batch=True
    )
    with pytest.raises(ValueError, match="reuse model-visible identity"):
        validate_replacement_bridge(root=tmp_path, bridge_path=bridge_path)
