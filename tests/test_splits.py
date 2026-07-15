"""T2.6 gates for deterministic, group-preserving benchmark splits."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.splits import build_splits


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data" / "benchmark" / "drift_instances.plausible.jsonl"
REAL = ROOT / "data" / "benchmark" / "seed" / "real_curated.jsonl"
FILENAMES = ("train.jsonl", "dev.jsonl", "test.jsonl", "distribution.md")


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _base_group(row: dict) -> str:
    base = row["provenance"].get("base_program")
    if base:
        return Path(base).stem.upper()
    return row["code_locus"]["loci"][0]["program"].upper()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    output = tmp_path_factory.mktemp("t26")
    report = build_splits(SYNTHETIC, REAL, output, seed=2600)
    rows = {
        split: _load(output / f"{split}.jsonl")
        for split in ("train", "dev", "test")
    }
    return output, report, rows


def test_gate_zero_base_program_overlap_and_no_missing_instances(built):
    _output, report, rows = built
    group_splits: dict[str, set[str]] = defaultdict(set)
    all_rows: list[dict] = []
    for split, items in rows.items():
        all_rows.extend(items)
        for item in items:
            group_splits[_base_group(item)].add(split)
    assert all(len(splits) == 1 for splits in group_splits.values())

    expected = _load(SYNTHETIC) + _load(REAL)
    assert len(all_rows) == len(expected)
    assert {item["instance_id"] for item in all_rows} == {
        item["instance_id"] for item in expected
    }
    assert report.counts == (("train", 30), ("dev", 0), ("test", 293))
    assert report.group_counts == (("train", 1), ("dev", 0), ("test", 14))


def test_gate_all_real_curated_instances_are_test_only(built):
    _output, _report, rows = built
    real_ids = {item["instance_id"] for item in _load(REAL)}
    assert real_ids <= {item["instance_id"] for item in rows["test"]}
    assert not real_ids & {
        item["instance_id"]
        for split in ("train", "dev")
        for item in rows[split]
    }
    assert all(
        item["provenance"]["source"] == "synthetic"
        for split in ("train", "dev")
        for item in rows[split]
    )


def test_gate_structural_t6_pairs_and_cross_variants_are_atomic(built):
    _output, _report, rows = built
    split_by_id = {
        item["instance_id"]: split
        for split, items in rows.items()
        for item in items
    }
    by_locus: dict[str, list[str]] = defaultdict(list)
    for item in _load(SYNTHETIC) + _load(REAL):
        key = json.dumps(item["code_locus"], sort_keys=True, separators=(",", ":"))
        by_locus[key].append(item["instance_id"])
    assert all(
        len({split_by_id[instance_id] for instance_id in instance_ids}) == 1
        for instance_ids in by_locus.values()
        if len(instance_ids) > 1
    )

    cross_groups: dict[str, set[str]] = defaultdict(set)
    for split, items in rows.items():
        for item in items:
            mutation = item["provenance"].get("mutation") or ""
            if "×" in mutation:
                cross_groups[_base_group(item)].add(split)
    assert cross_groups
    assert all(len(splits) == 1 for splits in cross_groups.values())


def test_gate_distribution_lists_and_flags_every_class_stratum_cell(built):
    output, report, _rows = built
    lines = (output / "distribution.md").read_text(encoding="utf-8").splitlines()
    cells = [
        line
        for line in lines
        if line.startswith(("| train | D", "| dev | D", "| test | D"))
    ]
    assert len(cells) == 3 * 7 * 2
    fragile = 0
    for line in cells:
        fields = [field.strip() for field in line.strip("|").split("|")]
        count = int(fields[3])
        status = fields[4]
        assert status == ("CI-fragile" if count < 10 else "ok")
        fragile += count < 10
    assert report.fragile_cells == fragile


def test_gate_regeneration_is_byte_deterministic(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    assert build_splits(SYNTHETIC, REAL, left, seed=2600) == build_splits(
        SYNTHETIC, REAL, right, seed=2600
    )
    for filename in FILENAMES:
        assert (left / filename).read_bytes() == (right / filename).read_bytes()
