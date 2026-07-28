from pathlib import Path

from cobol_archaeologist.benchmark.surface import FEATURE_NAMES
from cobol_archaeologist.eval.phase5 import (
    binary_detection,
    majority_baseline,
    prevalence_random_baseline,
    static_keyword_baseline,
    surface_attacker_baseline,
)
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "data" / "benchmark" / "v1-pre"
PROBE = ROOT / "data" / "benchmark" / "probes" / "t2.2_surface_probe.jsonl"


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
