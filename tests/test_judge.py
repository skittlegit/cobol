"""Plausibility judging: review packets, verdict records, and applying them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.judge import (
    SYSTEM_FAMILY,
    FamilyIntegrityError,
    Judgement,
    PlausibilityGateError,
    apply_verdicts,
    load_instances,
    load_judgements,
    plausibility_gate,
    render_packet,
    write_packets,
)
from cobol_archaeologist.cli import main
from cobol_archaeologist.eval.materialize import materialize

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
RUBRIC = ROOT / "docs" / "judge-rubric.md"


def _rows(count: int = 4) -> list:
    rows = [
        row
        for row in load_instances(BENCHMARK / "train.jsonl")
        if row.provenance.source == "synthetic"
    ]
    return rows[:count]


def _write_rows(path: Path, rows: list) -> Path:
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )
    return path


def _judgement(row, verdict="plausible", model="claude-opus", family="anthropic"):
    return Judgement(
        instance_id=row.instance_id,
        drift_type=row.drift_type,
        is_interprocedural=row.code_locus.is_interprocedural,
        verdict=verdict,
        reason="Reads like a real maintenance change.",
        model=model,
        model_family=family,
    )


def test_detector_family_is_openai():
    assert SYSTEM_FAMILY == "openai"


def test_packet_shows_clause_and_loci_but_no_answer():
    row = (
        next(r for r in _rows(50) if r.code_locus.is_interprocedural)
        if any(r.code_locus.is_interprocedural for r in _rows(50))
        else _rows(1)[0]
    )
    packet = render_packet(row, materialize(row))
    assert row.regulation_clause.text in packet
    assert packet.count("## Mutated locus") == len(row.code_locus.loci)
    for forbidden in (
        row.gold_rationale,
        "gold_rationale",
        "provenance",
        row.drift_type,
    ):
        assert forbidden not in packet
    assert (row.provenance.mutation or "MUTATION-NOTE") not in packet


def test_write_packets_writes_one_packet_per_row(tmp_path):
    rows = _rows(3)
    count = write_packets(_write_rows(tmp_path / "rows.jsonl", rows), tmp_path / "p.md")
    text = (tmp_path / "p.md").read_text(encoding="utf-8")
    assert count == 3
    assert all(f"# {row.instance_id}" in text for row in rows)


def test_apply_keeps_plausible_rows_and_writes_the_rest(tmp_path):
    rows = _rows(4)
    path = _write_rows(tmp_path / "rows.jsonl", rows)
    judgements = [
        _judgement(rows[0]),
        _judgement(rows[1]),
        _judgement(rows[2], "implausible"),
        _judgement(rows[3], "unsure"),
    ]
    report = apply_verdicts(
        path, judgements, tmp_path / "ok.jsonl", tmp_path / "no.jsonl"
    )
    assert report["accepted"] == 2 and report["rejected"] == 2
    kept = load_instances(tmp_path / "ok.jsonl")
    assert [row.instance_id for row in kept] == [
        rows[0].instance_id,
        rows[1].instance_id,
    ]
    rejected = [
        json.loads(line) for line in (tmp_path / "no.jsonl").read_text().splitlines()
    ]
    assert {row["judgement"]["verdict"] for row in rejected} == {
        "implausible",
        "unsure",
    }


def test_apply_refuses_judgements_from_the_detector_family(tmp_path):
    rows = _rows(1)
    path = _write_rows(tmp_path / "rows.jsonl", rows)
    with pytest.raises(FamilyIntegrityError):
        apply_verdicts(
            path,
            [_judgement(rows[0], model="gpt-6-luna", family="openai")],
            tmp_path / "ok.jsonl",
            tmp_path / "no.jsonl",
        )


def test_apply_requires_one_judgement_per_row(tmp_path):
    rows = _rows(2)
    path = _write_rows(tmp_path / "rows.jsonl", rows)
    with pytest.raises(ValueError, match="exactly one judgement"):
        apply_verdicts(
            path, [_judgement(rows[0])], tmp_path / "ok.jsonl", tmp_path / "no.jsonl"
        )


def test_disguised_model_family_is_rejected(tmp_path):
    rows = _rows(1)
    record = _judgement(rows[0], model="gpt-6-luna", family="anthropic")
    path = tmp_path / "j.jsonl"
    path.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(FamilyIntegrityError):
        load_judgements(path)


def test_plausibility_gate_requires_ninety_percent():
    rows = _rows(10)
    good = [_judgement(row) for row in rows]
    assert plausibility_gate(good) == 1.0
    bad = [_judgement(row, "implausible") for row in rows[:2]] + good[2:]
    with pytest.raises(PlausibilityGateError):
        plausibility_gate(bad)


def test_recorded_verdicts_reproduce_the_accepted_rows():
    # Train/dev rows come from the historical catalogue or from later builds
    # judged by Claude; every current synthetic row has a plausible verdict and
    # every plausible verdict belongs to a catalogued or current row.
    judgements = load_judgements(BENCHMARK / "judgements.jsonl")
    plausible = {item.instance_id for item in judgements if item.verdict == "plausible"}
    catalogue = {
        row.instance_id
        for row in load_instances(BENCHMARK / "drift_instances.plausible.jsonl")
    }
    current = {
        row.instance_id
        for split in ("train", "dev", "test")
        for row in load_instances(BENCHMARK / f"{split}.jsonl")
        if row.provenance.source == "synthetic"
    }
    assert current <= plausible | catalogue
    assert plausible <= catalogue | current
    rejected = [
        json.loads(line)["instance"]["instance_id"]
        for line in (BENCHMARK / "rejected.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert not set(rejected) & current


def test_cli_packets_and_apply(tmp_path, capsys):
    rows = _rows(2)
    path = _write_rows(tmp_path / "rows.jsonl", rows)
    assert (
        main(
            ["benchmark-packets", "--input", str(path), "--out", str(tmp_path / "p.md")]
        )
        == 0
    )
    judgements = tmp_path / "j.jsonl"
    judgements.write_text(
        "".join(_judgement(row).model_dump_json() + "\n" for row in rows)
    )
    assert (
        main(
            [
                "benchmark-apply",
                "--input",
                str(path),
                "--judgements",
                str(judgements),
                "--accepted-out",
                str(tmp_path / "ok.jsonl"),
                "--rejected-out",
                str(tmp_path / "no.jsonl"),
            ]
        )
        == 0
    )
    assert '"accepted": 2' in capsys.readouterr().out


def test_rubric_has_three_worked_seed_examples():
    text = RUBRIC.read_text(encoding="utf-8")
    assert text.count("### Example") == 3
    for program in ("BOIDENT1", "LATEFEE1", "CLOSPEN5"):
        assert program in text


def test_fresh_test_rows_were_judged_outside_the_detector_family():
    judgements = {
        item.instance_id: item for item in load_judgements(BENCHMARK / "judgements.jsonl")
    }
    for row in load_instances(BENCHMARK / "test.jsonl"):
        assert judgements[row.instance_id].model_family == "anthropic"
