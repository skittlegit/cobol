"""T2.6 gates for deterministic, group-preserving benchmark splits."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

import cobol_archaeologist.benchmark.splits as splits_module
from cobol_archaeologist.benchmark.splits import CLASS_ORDER, build_splits

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data" / "benchmark" / "drift_instances.plausible.jsonl"
REAL = ROOT / "data" / "benchmark" / "seed" / "real_curated.jsonl"
ROSTER = ROOT / "data" / "benchmark" / "seed" / "base_roster.json"
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
    report = build_splits(SYNTHETIC, REAL, output, seed=2600, roster_path=ROSTER)
    rows = {
        split: _load(output / f"{split}.jsonl") for split in ("train", "dev", "test")
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
    assert dict(report.counts) == {split: len(items) for split, items in rows.items()}
    assert all(count > 0 for _split, count in report.group_counts)


def test_gate_all_real_curated_instances_are_test_only(built):
    _output, _report, rows = built
    real_ids = {item["instance_id"] for item in _load(REAL)}
    assert real_ids <= {item["instance_id"] for item in rows["test"]}
    assert not real_ids & {
        item["instance_id"] for split in ("train", "dev") for item in rows[split]
    }
    assert all(
        item["provenance"]["source"] == "synthetic"
        for split in ("train", "dev")
        for item in rows[split]
    )


def test_gate_structural_t6_pairs_and_cross_variants_are_atomic(built):
    _output, _report, rows = built
    split_by_id = {
        item["instance_id"]: split for split, items in rows.items() for item in items
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


def test_gate_base_roster_reservations_are_honored(built):
    _output, _report, rows = built
    split_by_group = {
        _base_group(item): split for split, items in rows.items() for item in items
    }
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    for base_path, allowed_splits in roster["reservations"].items():
        group = Path(base_path).stem.upper()
        if group in split_by_group:
            assert split_by_group[group] in allowed_splits


def test_gate_purpose_level_split_minima(built):
    output, _report, rows = built
    synthetic_total = len(_load(SYNTHETIC))
    synthetic_counts = {
        split: sum(item["provenance"]["source"] == "synthetic" for item in items)
        for split, items in rows.items()
    }
    assert synthetic_counts["dev"] >= 0.12 * synthetic_total
    assert synthetic_counts["train"] >= 0.40 * synthetic_total

    for split in ("train", "dev"):
        classes = {item["drift_type"] for item in rows[split]}
        assert len(classes) >= 5

    test_local = [
        item for item in rows["test"] if not item["code_locus"]["is_interprocedural"]
    ]
    local_counts = Counter(item["drift_type"] for item in test_local)
    assert all(local_counts[drift_type] >= 10 for drift_type in CLASS_ORDER)

    test_interprocedural = [
        item for item in rows["test"] if item["code_locus"]["is_interprocedural"]
    ]
    assert len(test_interprocedural) >= 30
    operator_counts = Counter(
        (item["provenance"].get("mutation") or "").split(";", 1)[0]
        for item in test_interprocedural
    )
    assert all(
        operator_counts[operator] >= 8 for operator in ("MO-1×", "MO-3×", "MO-6×")
    )

    distribution = (output / "distribution.md").read_text(encoding="utf-8")
    interprocedural_classes = Counter(
        item["drift_type"] for item in test_interprocedural
    )
    for drift_type in CLASS_ORDER[:6]:
        if interprocedural_classes[drift_type] == 0:
            assert f"| {drift_type} | 0 |" in distribution


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
    assert build_splits(
        SYNTHETIC, REAL, left, seed=2600, roster_path=ROSTER
    ) == build_splits(SYNTHETIC, REAL, right, seed=2600, roster_path=ROSTER)
    for filename in FILENAMES:
        assert (left / filename).read_bytes() == (right / filename).read_bytes()


def test_quantitative_repair_allows_a_deficit_reducing_first_move(monkeypatch):
    """BL-10: two small groups may be needed to clear one cell minimum."""

    groups = {"D4-A": [object()], "D4-B": [object()]}
    assignments = {"D4-A": "train", "D4-B": "train"}
    allowed = {
        "D4-A": ("train", "test"),
        "D4-B": ("train", "test"),
    }

    def errors(_groups, candidate):
        return (
            []
            if all(split == "test" for split in candidate.values())
            else ["test-local D4 has fewer than 10 instances"]
        )

    def deficit(_groups, candidate):
        return float(sum(split != "test" for split in candidate.values()))

    monkeypatch.setattr(splits_module, "_purpose_errors", errors)
    monkeypatch.setattr(splits_module, "_purpose_deficit", deficit)
    monkeypatch.setattr(
        splits_module,
        "_assignment_score_for_groups",
        lambda _groups, _candidate: 0.0,
    )

    repaired = splits_module._repair_assignments(groups, assignments, allowed)

    assert repaired == {"D4-A": "test", "D4-B": "test"}
