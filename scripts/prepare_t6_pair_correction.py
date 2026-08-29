"""Prepare six opaque, proposal-blind T6 pair-correction calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.benchmark.t6_pair_correction import (
    CORRECTION_PAIR_ORDER,
    PairCorrectionPlanItem,
    PairCorrectionSideInput,
    build_pair_correction_prompt,
)
from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    T6ReviewPromotionReport,
)
from cobol_archaeologist.benchmark.t6_v2 import (
    ArtifactPin,
    load_blinded_review_packet,
    load_candidate_pair_proposals,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("pair correction artifact escapes repository")
    return ArtifactPin(
        path=resolved.relative_to(root).as_posix(), sha256=_sha(resolved)
    )


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite pair correction artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _rows(path: Path) -> dict[str, BlindedReviewRecord]:
    return {
        row.review_item_id: row
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for row in [BlindedReviewRecord.model_validate_json(raw)]
    }


def prepare(*, root: Path, output_dir: Path) -> Path:
    root = root.resolve()
    output_dir = output_dir.resolve()
    failure_path = (
        root
        / "data/benchmark/t6-v2/review/evidence/promotion-gate/"
        "pre-pair-correction-report.json"
    )
    failure = T6ReviewPromotionReport.model_validate_json(
        failure_path.read_text(encoding="utf-8")
    )
    scope = tuple(
        gap.pair_id
        for gap in failure.gaps
        if gap.code == "pair_ineligible" and gap.pair_id is not None
    )
    if failure.evaluation_ready or scope != CORRECTION_PAIR_ORDER:
        raise ValueError("failed promotion does not derive the frozen six-pair scope")
    packet_path = root / "data/benchmark/t6-v2/review/packet.jsonl"
    packet = load_blinded_review_packet(packet_path)
    packet_by_id = {item.review_item_id: item for item in packet}
    proposals = {
        pair.pair_id: pair
        for pair in load_candidate_pair_proposals(
            root / "data/benchmark/t6-v2/candidates/pair_proposals.jsonl"
        )
    }
    primary_path = root / "data/benchmark/t6-v2/final/ai-primary-responses.jsonl"
    adjudication_path = (
        root
        / "data/benchmark/t6-v2/review/evidence/ai-adjudicator-promotion-bridge/"
        "promotion-responses.jsonl"
    )
    resolved = {**_rows(primary_path), **_rows(adjudication_path)}
    failure_sha = _sha(failure_path)
    plans: list[PairCorrectionPlanItem] = []
    for pair_id in CORRECTION_PAIR_ORDER:
        pair = proposals[pair_id]
        sides = sorted(pair.sides, key=lambda side: side.candidate_side_id)
        items = [packet_by_id[side.blind_review_id] for side in sides]
        if items[0].source_text != items[1].source_text:
            raise ValueError(f"{pair_id} correction sides do not share source text")
        call_id = "pcall-" + hashlib.sha256(
            f"{failure_sha}:{pair_id}".encode()
        ).hexdigest()[:12]
        plans.append(
            PairCorrectionPlanItem(
                schema_version="1",
                correction_pair_id=pair_id,
                correction_call_id=call_id,
                shared_source_text=items[0].source_text,
                sides=tuple(
                    PairCorrectionSideInput(
                        position=position,
                        review_item_id=item.review_item_id,
                        authority=item.authority,
                        source_alias=item.source_alias,
                        sealed_side_judgment=resolved[
                            item.review_item_id
                        ].review_response,
                    )
                    for position, item in zip(("left", "right"), items, strict=True)
                ),
            )
        )
    plan_path = output_dir / "correction-plan.jsonl"
    _write_once(
        plan_path,
        "".join(plan.model_dump_json() + "\n" for plan in plans).encode("utf-8"),
    )
    prompt_records = []
    forbidden = (
        "proposal",
        "gold",
        "pair_proposals",
        "data/benchmark",
        "exactly one included d7",
        "one d7 and one",
        "temporal flip",
    )
    for ordinal, plan in enumerate(plans, start=1):
        prompt = build_pair_correction_prompt(plan)
        lowered = prompt.lower()
        if plan.correction_pair_id in prompt or any(item in lowered for item in forbidden):
            raise ValueError("model-visible correction prompt leaks coordinator state")
        prompt_path = output_dir / "prompts" / f"pair-{ordinal:02d}.txt"
        _write_once(prompt_path, prompt.encode("utf-8"))
        prompt_records.append(
            {
                "correction_pair_id": plan.correction_pair_id,
                "correction_call_id": plan.correction_call_id,
                "review_item_order": [side.review_item_id for side in plan.sides],
                "prompt": _pin(root, prompt_path).model_dump(mode="json"),
                "prompt_utf8_length": len(prompt.encode("utf-8")),
            }
        )
    manifest_path = output_dir / "prompt-manifest.coordinator-private.json"
    manifest = {
        "schema_version": "1",
        "model_id": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "fork_turns": "none",
        "tools_authorized": 0,
        "prior_pair_context_included": False,
        "failed_promotion_report": _pin(root, failure_path).model_dump(mode="json"),
        "packet": _pin(root, packet_path).model_dump(mode="json"),
        "primary_responses": _pin(root, primary_path).model_dump(mode="json"),
        "adjudication_responses": _pin(root, adjudication_path).model_dump(mode="json"),
        "correction_plan": _pin(root, plan_path).model_dump(mode="json"),
        "pair_order": list(CORRECTION_PAIR_ORDER),
        "calls": prompt_records,
    }
    _write_once(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/benchmark/t6-v2/review/pair-correction-v2"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir.is_absolute()
        else (root / args.output_dir).resolve()
    )
    print(prepare(root=root, output_dir=output_dir))


if __name__ == "__main__":
    main()
