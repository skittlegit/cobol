"""Seal six fresh replacement reviews and their eligible-pool bridge."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_replacement import (
    ReplacementAttemptAudit,
    ReplacementAuditManifest,
    ReplacementBridgeManifest,
    ReplacementCompletion,
    ReplacementItemAudit,
    ReplacementPlanItem,
    replacement_envelope,
    require_replacement_flip,
    validate_replacement_audit,
    validate_replacement_bridge,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=_sha_bytes(resolved.read_bytes())
    )


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite replacement evidence: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _compact(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def build(*, root: Path, coordinator: Path, transcript: Path, output_dir: Path) -> Path:
    root = root.resolve()
    manifest = json.loads(coordinator.read_text(encoding="utf-8"))
    plan_path = root / manifest["replacement_plan"]["path"]
    plans = [
        ReplacementPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    calls = [json.loads(raw) for raw in transcript.read_text(encoding="utf-8").splitlines() if raw.strip()]
    if len(plans) != 6 or len(calls) != 6:
        raise ValueError("replacement transcript must contain six calls")
    responses: list[ReplacementCompletion] = []
    items: list[ReplacementItemAudit] = []
    for plan, call, frozen in zip(plans, calls, manifest["calls"], strict=True):
        if call.get("review_call_id") != plan.replacement_call_id:
            raise ValueError("replacement transcript uses wrong opaque call ID")
        prompt_path = root / frozen["prompt"]["path"]
        prompt = prompt_path.read_bytes()
        if _sha_bytes(prompt) != frozen["prompt"]["sha256"]:
            raise ValueError("replacement prompt pin changed")
        final = call["final_message"].encode("utf-8")
        response = ReplacementCompletion.model_validate_json(final)
        try:
            require_replacement_flip(response)
        except ValueError:
            outcome = "rejected_nonflip"
        else:
            outcome = "validated_flip"
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
            prompt_sha256=_sha_bytes(prompt),
            final_message_utf8_base64=base64.b64encode(final).decode("ascii"),
            final_message_utf8_length=len(final),
            final_message_sha256=_sha_bytes(final),
            outcome=outcome,
        )
        responses.append(response)
        items.append(
            ReplacementItemAudit(
                replacement_id=plan.replacement_id,
                replacement_call_id=plan.replacement_call_id,
                review_item_order=tuple(side.review_item_id for side in plan.sides),
                envelope_sha256=_sha_bytes(_compact(replacement_envelope(plan))),
                attempt=attempt,
            )
        )
    responses_path = output_dir / "responses.jsonl"
    _write_once(responses_path, "".join(row.model_dump_json() + "\n" for row in responses).encode())
    audit_path = output_dir / "audit-manifest.json"
    audit = ReplacementAuditManifest(
        schema_version="1",
        audit_variant="additive_replacement_review",
        finalized=True,
        reviewer_pseudonym="luna-max-independent-paired-authority-reviewer",
        correction_audit=ArtifactPin.model_validate(manifest["correction_audit"]),
        replacement_plan=ArtifactPin.model_validate(manifest["replacement_plan"]),
        responses=_pin(root, responses_path),
        provider="chatgpt-codex-collaboration",
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        fork_turns_per_attempt="none",
        fresh_task_per_pair=True,
        tools_authorized_per_call=0,
        prior_pair_context_included=False,
        item_count=6,
        validated_flip_count=sum(item.attempt.outcome == "validated_flip" for item in items),
        rejected_nonflip_count=sum(item.attempt.outcome == "rejected_nonflip" for item in items),
        replacement_order=tuple(manifest["replacement_order"]),
        items=items,
    )
    _write_once(audit_path, (audit.model_dump_json(indent=2) + "\n").encode())
    validate_replacement_audit(root=root, manifest_path=audit_path)
    accepted_ids = tuple(
        item.replacement_id for item in items if item.attempt.outcome == "validated_flip"
    )
    bridge_path = output_dir / "promotion-bridge-manifest.json"
    bridge = ReplacementBridgeManifest(
        schema_version="1",
        finalized=True,
        projection="replacement_review_to_t6_pool_v1",
        replacement_audit=_pin(root, audit_path),
        replacement_plan=audit.replacement_plan,
        replacement_responses=audit.responses,
        replacement_order=accepted_ids,
        review_item_members={
            plan.replacement_id: tuple(side.review_item_id for side in plan.sides)
            for plan, item in zip(plans, items, strict=True)
            if item.attempt.outcome == "validated_flip"
        },
    )
    _write_once(bridge_path, (bridge.model_dump_json(indent=2) + "\n").encode())
    validate_replacement_bridge(root=root, bridge_path=bridge_path)
    return bridge_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--coordinator", type=Path, default=Path("data/benchmark/t6-v2/replacements/review-v4/prompt-manifest.coordinator-private.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/benchmark/t6-v2/replacements/evidence/review-v4"))
    args = parser.parse_args()
    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else (root / path).resolve()
    print(build(root=root, coordinator=resolve(args.coordinator), transcript=resolve(args.transcript), output_dir=resolve(args.output_dir)))


if __name__ == "__main__":
    main()
