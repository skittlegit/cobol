from __future__ import annotations

import json
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.t6_comparison import prepare_review_comparison

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "data/benchmark/t6-v2/review/packet.jsonl"
PRIMARY = ROOT / "data/benchmark/t6-v2/review/ai-primary-collaboration/transcript.jsonl"
INDEPENDENT = (
    ROOT
    / "data/benchmark/t6-v2/review/evidence/"
    "luna-independent-collaboration-subagent/audit-manifest.json"
)


def _report():
    return prepare_review_comparison(
        root=ROOT,
        packet_path=PACKET,
        primary_transcript_path=PRIMARY,
        independent_manifest_path=INDEPENDENT,
    )


def _partial_primary(tmp_path: Path) -> Path:
    rows = [
        json.loads(raw)
        for raw in PRIMARY.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    for row in rows:
        if len(row["attempts"]) > 1 and row["attempts"][0]["outcome"] == "schema_invalid":
            row["attempts"] = row["attempts"][:1]
    partial = tmp_path / "partial-primary.jsonl"
    partial.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return partial


def test_partial_primary_comparison_is_fail_closed(tmp_path: Path) -> None:
    report = prepare_review_comparison(
        root=ROOT,
        packet_path=PACKET,
        primary_transcript_path=_partial_primary(tmp_path),
        independent_manifest_path=INDEPENDENT,
    )

    assert report.status == "incomplete_primary"
    assert report.primary_accepted_item_count == 16
    assert report.primary_schema_invalid_attempt_count == 6
    assert report.compared_item_count == 16
    assert len(report.pending_primary_item_ids) == 6
    assert report.automatic_adjudication_performed is False
    assert report.promotion_performed is False


def test_comparison_is_deterministic() -> None:
    first = _report().model_dump_json()
    second = _report().model_dump_json()

    assert first == second


def test_valid_primary_response_cannot_be_marked_schema_invalid(tmp_path: Path) -> None:
    rows = [
        json.loads(raw)
        for raw in PRIMARY.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    rows[0]["attempts"][0]["outcome"] = "schema_invalid"
    tampered = tmp_path / "primary.jsonl"
    tampered.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="marked invalid has a valid response"):
        prepare_review_comparison(
            root=ROOT,
            packet_path=PACKET,
            primary_transcript_path=tampered,
            independent_manifest_path=INDEPENDENT,
        )


def test_six_fresh_retries_make_comparison_complete() -> None:
    report = _report()

    assert report.status == "ready_for_adjudication_review"
    assert report.primary_accepted_item_count == 22
    assert report.primary_schema_invalid_attempt_count == 6
    assert report.pending_primary_item_ids == []
    assert report.automatic_adjudication_performed is False
    assert report.promotion_performed is False
