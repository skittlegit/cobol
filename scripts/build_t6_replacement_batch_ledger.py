"""Seal one immutable batch of one-shot replacement review attempts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_replacement import (
    ReplacementAttemptAudit,
    ReplacementBatchLedgerManifest,
    ReplacementItemAudit,
    ReplacementPlanItem,
    classify_replacement_final,
    replacement_envelope,
    validate_replacement_batch_ledger,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, artifact_sha256_matches


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("replacement ledger artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=_sha(resolved.read_bytes())
    )


def _write_once(path: Path, value: bytes) -> None:
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"refusing to overwrite replacement ledger: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _compact(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def build(
    *,
    root: Path,
    coordinator: Path,
    transcript: Path,
    output_dir: Path,
    batch_id: str,
) -> Path:
    root = root.resolve()
    coordinator_data = json.loads(coordinator.read_text(encoding="utf-8"))
    plan_pin = ArtifactPin.model_validate(coordinator_data["replacement_plan"])
    plan_path = root / plan_pin.path
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    calls = [
        json.loads(raw)
        for raw in transcript.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    frozen_calls = coordinator_data["calls"]
    if len(plans) != len(calls) or len(plans) != len(frozen_calls):
        raise ValueError("replacement ledger transcript differs from batch size")
    items: list[ReplacementItemAudit] = []
    for plan, call, frozen in zip(plans, calls, frozen_calls, strict=True):
        if (
            set(call) != {"review_call_id", "task_identity", "final_message"}
            or call["review_call_id"] != plan.replacement_call_id
            or frozen["replacement_call_id"] != plan.replacement_call_id
        ):
            raise ValueError("replacement ledger transcript uses wrong call identity")
        prompt_path = root / frozen["prompt"]["path"]
        prompt = prompt_path.read_bytes()
        if not artifact_sha256_matches(prompt_path, frozen["prompt"]["sha256"]):
            raise ValueError("replacement ledger prompt pin changed")
        final = call["final_message"].encode("utf-8")
        outcome, _ = classify_replacement_final(plan=plan, final=final)
        attempt = ReplacementAttemptAudit(
            attempt=1,
            task_identity=call["task_identity"],
            fork_turns="none",
            model_id="gpt-5.6-luna",
            reasoning_effort="max",
            tools_authorized=0,
            visible_pairs=1,
            prior_pair_context_included=False,
            prompt_utf8_base64=base64.b64encode(prompt).decode("ascii"),
            prompt_utf8_length=len(prompt),
            prompt_sha256=_sha(prompt),
            final_message_utf8_base64=base64.b64encode(final).decode("ascii"),
            final_message_utf8_length=len(final),
            final_message_sha256=_sha(final),
            outcome=outcome,
        )
        items.append(
            ReplacementItemAudit(
                replacement_id=plan.replacement_id,
                replacement_call_id=plan.replacement_call_id,
                review_item_order=tuple(side.review_item_id for side in plan.sides),
                envelope_sha256=_sha(_compact(replacement_envelope(plan))),
                attempt=attempt,
            )
        )
    outcomes = (
        "validated_flip",
        "rejected_nonflip",
        "rejected_invalid_identity",
        "rejected_schema",
    )
    ledger = ReplacementBatchLedgerManifest(
        schema_version="1",
        ledger_variant="replacement_one_shot_batch_v1",
        finalized=True,
        batch_id=batch_id,
        coordinator_manifest=_pin(root, coordinator),
        correction_audit=ArtifactPin.model_validate(
            coordinator_data["correction_audit"]
        ),
        replacement_plan=plan_pin,
        transcript=_pin(root, transcript),
        provider="chatgpt-codex-collaboration",
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        fork_turns_per_attempt="none",
        fresh_task_per_pair=True,
        tools_authorized_per_call=0,
        prior_pair_context_included=False,
        item_count=len(items),
        outcome_counts={
            outcome: sum(item.attempt.outcome == outcome for item in items)
            for outcome in outcomes
        },
        replacement_order=tuple(item.replacement_id for item in items),
        items=items,
    )
    ledger_path = output_dir / "batch-ledger-manifest.json"
    _write_once(
        ledger_path, (ledger.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    validate_replacement_batch_ledger(root=root, ledger_path=ledger_path)
    return ledger_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--coordinator", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    print(
        build(
            root=root,
            coordinator=resolve(args.coordinator),
            transcript=resolve(args.transcript),
            output_dir=resolve(args.output_dir),
            batch_id=args.batch_id,
        )
    )


if __name__ == "__main__":
    main()
