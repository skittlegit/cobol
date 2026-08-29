"""Deterministically rebuild the coordinator-only T6-v2 blind release queue."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cobol_archaeologist.benchmark.t6_v2 import (
    BlindedReviewItem,
    BlindedReviewResponse,
    load_candidate_pair_proposals,
)

ROOT = Path(__file__).resolve().parents[1]
T6_ROOT = ROOT / "data/benchmark/t6-v2"


def _alias(review_item_id: str) -> str:
    digest = hashlib.sha256(f"t6-v2-source-alias:{review_item_id}".encode()).hexdigest()
    return f"src-{digest[:12]}"


def main() -> None:
    proposals = load_candidate_pair_proposals(
        T6_ROOT / "candidates/pair_proposals.jsonl"
    )
    envelopes: list[tuple[str, object, str, str]] = []
    for pair in proposals:
        source_text = (ROOT / pair.code_input_path).read_text(encoding="utf-8")
        for side in pair.sides:
            envelopes.append(
                (
                    side.blind_review_id,
                    side.authority,
                    _alias(side.blind_review_id),
                    source_text,
                )
            )
    envelopes.sort(
        key=lambda row: hashlib.sha256(
            f"t6-v2-release-order-v2:{row[0]}".encode()
        ).digest()
    )
    rows = [
        BlindedReviewItem(
            review_item_id=review_item_id,
            authority=authority,
            source_alias=source_alias,
            source_text=source_text,
            release_ordinal=ordinal,
            review_response=BlindedReviewResponse(),
        )
        for ordinal, (
            review_item_id,
            authority,
            source_alias,
            source_text,
        ) in enumerate(envelopes, start=1)
    ]
    destination = T6_ROOT / "review/packet.jsonl"
    temporary = destination.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(destination)


if __name__ == "__main__":
    main()
