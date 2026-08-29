"""Seal fresh pair-aware Luna completions and build their promotion bridge."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_pair_correction import (
    PairCorrectionAttemptAudit,
    PairCorrectionAuditManifest,
    PairCorrectionBridgeManifest,
    PairCorrectionCompletion,
    PairCorrectionItemAudit,
    PairCorrectionPlanItem,
    pair_correction_envelope,
    require_temporal_flip,
    validate_pair_correction_audit,
    validate_pair_correction_bridge,
)
from cobol_archaeologist.benchmark.t6_review import BlindedReviewRecord
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, artifact_sha256_matches


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("pair correction audit escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=_sha(resolved)
    )


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite correction evidence: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _compact(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def build(
    *, root: Path, coordinator_manifest_path: Path, transcript_path: Path, output_dir: Path
) -> Path:
    root = root.resolve()
    coordinator = json.loads(coordinator_manifest_path.read_text(encoding="utf-8"))
    plan_path = root / coordinator["correction_plan"]["path"]
    plans = [
        PairCorrectionPlanItem.model_validate_json(raw)
        for raw in plan_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    transcript = [
        json.loads(raw)
        for raw in transcript_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    if len(plans) != 6 or len(transcript) != 6:
        raise ValueError("correction transcript must contain exactly six calls")
    responses: list[PairCorrectionCompletion] = []
    items: list[PairCorrectionItemAudit] = []
    for plan, call, coordinator_call in zip(
        plans, transcript, coordinator["calls"], strict=True
    ):
        if (
            call.get("correction_call_id") != plan.correction_call_id
            or coordinator_call["correction_call_id"] != plan.correction_call_id
            or not isinstance(call.get("task_identity"), str)
            or not isinstance(call.get("final_message"), str)
        ):
            raise ValueError("correction transcript identity differs from plan")
        prompt_path = root / coordinator_call["prompt"]["path"]
        if not artifact_sha256_matches(
            prompt_path, coordinator_call["prompt"]["sha256"]
        ):
            raise ValueError("correction prompt pin changed")
        prompt = prompt_path.read_bytes()
        final = call["final_message"].encode("utf-8")
        completion = PairCorrectionCompletion.model_validate_json(final)
        if completion.correction_call_id != plan.correction_call_id:
            raise ValueError("correction completion uses the wrong opaque call ID")
        responses.append(completion)
        try:
            require_temporal_flip(completion)
        except ValueError:
            outcome = "rejected_nonflip"
        else:
            outcome = "validated_flip"
        attempt = PairCorrectionAttemptAudit(
            attempt=1,
            task_identity=call["task_identity"],
            fork_turns="none",
            model_id="gpt-5.6-luna",
            reasoning_effort="max",
            tools_authorized=0,
            prior_pair_context_included=False,
            visible_pairs=1,
            prompt_utf8_base64=base64.b64encode(prompt).decode("ascii"),
            prompt_utf8_length=len(prompt),
            prompt_sha256=_sha_bytes(prompt),
            final_message_utf8_base64=base64.b64encode(final).decode("ascii"),
            final_message_utf8_length=len(final),
            final_message_sha256=_sha_bytes(final),
            outcome=outcome,
        )
        items.append(
            PairCorrectionItemAudit(
                correction_pair_id=plan.correction_pair_id,
                correction_call_id=plan.correction_call_id,
                review_item_order=tuple(
                    side.review_item_id for side in plan.sides
                ),
                envelope_sha256=_sha_bytes(
                    _compact(pair_correction_envelope(plan))
                ),
                attempt=attempt,
            )
        )
    responses_path = output_dir / "responses.jsonl"
    _write_once(
        responses_path,
        "".join(row.model_dump_json() + "\n" for row in responses).encode("utf-8"),
    )
    audit_path = output_dir / "audit-manifest.json"
    audit = PairCorrectionAuditManifest(
        schema_version="1",
        audit_variant="pair_aware_ai_correction",
        finalized=True,
        review_role="pair_aware_ai_correction",
        reviewer_pseudonym="luna-max-pair-aware-ai-correction",
        failed_promotion_report=ArtifactPin.model_validate(
            coordinator["failed_promotion_report"]
        ),
        correction_plan=ArtifactPin.model_validate(coordinator["correction_plan"]),
        packet=ArtifactPin.model_validate(coordinator["packet"]),
        primary_responses=ArtifactPin.model_validate(
            coordinator["primary_responses"]
        ),
        adjudication_responses=ArtifactPin.model_validate(
            coordinator["adjudication_responses"]
        ),
        responses=_pin(root, responses_path),
        provider="chatgpt-codex-collaboration",
        model_id="gpt-5.6-luna",
        reasoning_effort="max",
        fork_turns_per_attempt="none",
        fresh_task_per_pair=True,
        visible_pairs_per_call=1,
        tools_authorized_per_call=0,
        prior_pair_context_included=False,
        proposal_labels_visible=False,
        item_count=6,
        validated_flip_count=sum(
            item.attempt.outcome == "validated_flip" for item in items
        ),
        rejected_nonflip_count=sum(
            item.attempt.outcome == "rejected_nonflip" for item in items
        ),
        pair_order=tuple(coordinator["pair_order"]),
        items=items,
    )
    _write_once(
        audit_path, (audit.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    validate_pair_correction_audit(root=root, manifest_path=audit_path)
    accepted = [
        (plan, completion)
        for plan, completion, item in zip(plans, responses, items, strict=True)
        if item.attempt.outcome == "validated_flip"
    ]
    projected = [
        BlindedReviewRecord(
            review_item_id=side.review_item_id,
            reviewer_pseudonym=audit.reviewer_pseudonym,
            completed_at="1970-01-01T00:00:00Z",
            review_response=side.review_response,
        )
        for _, completion in accepted
        for side in completion.sides
    ]
    projected_path = output_dir / "promotion-responses.jsonl"
    _write_once(
        projected_path,
        "".join(row.model_dump_json() + "\n" for row in projected).encode("utf-8"),
    )
    bridge_path = output_dir / "promotion-bridge-manifest.json"
    bridge = PairCorrectionBridgeManifest(
        schema_version="1",
        finalized=True,
        projection="pair_correction_to_t6_promotion_v1",
        correction_audit_manifest=_pin(root, audit_path),
        correction_responses=_pin(root, projected_path),
        pair_order=tuple(plan.correction_pair_id for plan, _ in accepted),
        pair_members={
            plan.correction_pair_id: tuple(
                side.review_item_id for side in plan.sides
            )
            for plan, _ in accepted
        },
    )
    _write_once(
        bridge_path, (bridge.model_dump_json(indent=2) + "\n").encode("utf-8")
    )
    validate_pair_correction_bridge(root=root, bridge_path=bridge_path)
    return bridge_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument(
        "--coordinator-manifest",
        type=Path,
        default=Path(
            "data/benchmark/t6-v2/review/pair-correction-v2/"
            "prompt-manifest.coordinator-private.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/benchmark/t6-v2/review/evidence/pair-aware-ai-correction"
        ),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    print(
        build(
            root=root,
            coordinator_manifest_path=resolve(args.coordinator_manifest),
            transcript_path=resolve(args.transcript),
            output_dir=resolve(args.output_dir),
        )
    )


if __name__ == "__main__":
    main()
