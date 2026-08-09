import json
import random
from pathlib import Path

from cobol_archaeologist.benchmark.surface import FEATURE_NAMES
from cobol_archaeologist.eval.phase5 import (
    binary_detection,
    build_offline_suite,
    majority_baseline,
    prevalence_random_baseline,
    static_keyword_baseline,
    surface_attacker_baseline,
)
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "data" / "benchmark" / "v1-pre"
V1 = ROOT / "data" / "benchmark" / "v1"
BASELINES = ROOT / "data" / "eval" / "m5" / "baselines"
PROBE = ROOT / "data" / "benchmark" / "probes" / "t2.2_surface_probe.jsonl"
OFFLINE_SYSTEMS = (
    "train_majority",
    "prevalence_random",
    "static_keyword",
    "attacker_with_bases",
)


def _by_id(path: Path) -> dict[str, dict]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {record["instance_id"]: record for record in records}


def _load(name: str) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in (PRE / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_offline_baselines_are_full_coverage_and_deterministic():
    train = _load("train")
    test = _load("test")[:12]
    systems = (
        majority_baseline(train, test),
        prevalence_random_baseline(train, test),
        static_keyword_baseline(test),
    )
    for records in systems:
        assert len(records) == len(test)
        assert binary_detection(records)["answer_rate"] == 1.0
        assert all("mutation" not in record.model_dump_json() for record in records)
    reversed_random = prevalence_random_baseline(train, list(reversed(test)))
    assert {row.instance_id: row.predicted_is_drift for row in systems[1]} == {
        row.instance_id: row.predicted_is_drift for row in reversed_random
    }


def test_attacker_uses_exact_registered_features_without_operator_leakage():
    test = _load("test")[:12]
    records, manifest = surface_attacker_baseline(test, probe_path=PROBE)
    assert len(records) == len(test)
    assert manifest.parameters["feature_names"] == list(FEATURE_NAMES)
    assert manifest.source_probe_sha256
    for record in records:
        assert set(record.details["features"]) == set(FEATURE_NAMES)
        payload = record.model_dump_json()
        assert "operator" not in payload
        assert "mutation" not in payload


def test_frozen_offline_suite_is_reorder_invariant_and_excludes_dropped_ids(tmp_path):
    """T5.3 gate: the four no-provider baselines over the frozen v1 split are
    per-instance identical when the test file is shuffled, and no artifact ever
    mentions one of T5.2's 8 excluded candidate IDs."""

    excluded = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))[
        "excluded_candidate_ids"
    ]
    assert len(excluded) == 8

    rows = [
        line
        for line in (V1 / "test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    shuffled = rows[:]
    random.Random(20260809).shuffle(shuffled)
    assert shuffled != rows
    reordered_split = tmp_path / "test_shuffled.jsonl"
    reordered_split.write_text("\n".join(shuffled) + "\n", encoding="utf-8")

    build_offline_suite(
        train_path=V1 / "train.jsonl",
        test_path=reordered_split,
        probe_path=PROBE,
        output_dir=tmp_path / "baselines",
    )

    for system in OFFLINE_SYSTEMS:
        frozen = _by_id(BASELINES / f"{system}.jsonl")
        reordered = _by_id(tmp_path / "baselines" / f"{system}.jsonl")
        assert frozen == reordered, f"{system} is not reorder-invariant"
        assert not set(frozen) & set(excluded)

    for artifact in sorted(BASELINES.glob("*")):
        text = artifact.read_text(encoding="utf-8")
        assert not [bad for bad in excluded if bad in text], artifact.name
