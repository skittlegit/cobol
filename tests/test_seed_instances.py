"""T2.5 Phase 3 gate: validate the first real-curated seed batch."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from cobol_archaeologist.schemas import DriftInstance


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "benchmark" / "seed"
INSTANCES_PATH = SEED_DIR / "real_curated.jsonl"
PROGRAMS_DIR = SEED_DIR / "programs"
COBC = shutil.which("cobc")

# Phase 2 retired P2. Phase 3 therefore contains P1, a second P1 deepening,
# P3, P4, and P5 as five distinct locus-pairs; P6 is a citation-axis probe.
EXPECTED_T6_PAIR_COUNT = 5


def _load_raw_instances() -> list[dict]:
    assert INSTANCES_PATH.is_file(), f"missing authored seed: {INSTANCES_PATH}"
    records: list[dict] = []
    for line_number, line in enumerate(
        INSTANCES_PATH.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"{INSTANCES_PATH.name}:{line_number}: invalid JSON: {exc}"
            ) from exc
    return records


def _locus_key(record: dict) -> str:
    return json.dumps(
        record["code_locus"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _raw_loci_by_instance_id() -> dict[str, bytes]:
    """Return each code_locus exactly as encoded in the JSONL artifact."""
    decoder = json.JSONDecoder()
    marker = '"code_locus":'
    raw_loci: dict[str, bytes] = {}

    for line in INSTANCES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        start = line.index(marker) + len(marker)
        while start < len(line) and line[start].isspace():
            start += 1
        _, end = decoder.raw_decode(line, start)
        raw_loci[record["instance_id"]] = line[start:end].encode("utf-8")

    return raw_loci


def _temporal_key(record: dict) -> tuple[str, str]:
    clause = record["regulation_clause"]
    return clause["version"], clause["effective_date"]


def _t6_pair_groups(records: list[dict]) -> list[list[dict]]:
    by_locus: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_locus[_locus_key(record)].append(record)

    # DECISION: the frozen schema deliberately has no pair_id. CONTRACT.md Part
    # 2 binds T6 sides by equal code_locus, so a pair candidate is a locus group
    # containing more than one regulation version/effective date.
    return [
        group
        for group in by_locus.values()
        if len({_temporal_key(record) for record in group}) > 1
    ]


def test_every_instance_round_trips_frozen_schema():
    records = _load_raw_instances()
    for record in records:
        first = DriftInstance.model_validate(record)
        second = DriftInstance.model_validate_json(first.model_dump_json())
        assert second == first, record.get("instance_id")


def test_real_curated_provenance_contract():
    for record in _load_raw_instances():
        provenance = record["provenance"]
        assert provenance["source"] == "real_curated", record["instance_id"]
        assert provenance.get("mutation") is None, record["instance_id"]


def test_t6_pairs_have_identical_loci_and_opposite_labels():
    pairs = _t6_pair_groups(_load_raw_instances())
    raw_loci = _raw_loci_by_instance_id()
    assert len(pairs) == EXPECTED_T6_PAIR_COUNT

    for group in pairs:
        assert len(group) == 2, [record["instance_id"] for record in group]
        assert len({_locus_key(record) for record in group}) == 1
        assert len({raw_loci[record["instance_id"]] for record in group}) == 1
        assert len({_temporal_key(record) for record in group}) == 2
        assert {record["labels"]["program_level"] for record in group} == {
            "conformant",
            "drift",
        }


def test_d2_instances_label_the_insertion_point():
    d2_records = [
        record
        for record in _load_raw_instances()
        if record["drift_type"] == "D2_missing_rule"
    ]
    assert d2_records, "seed must exercise D2 insertion-point labels"
    for record in d2_records:
        assert record["labels"]["line_level"], record["instance_id"]


def test_seed_contains_at_least_twenty_instances():
    assert len(_load_raw_instances()) >= 20


@pytest.mark.skipif(
    COBC is None, reason="cobc unavailable (required for T2.5 gate run)"
)
@pytest.mark.parametrize(
    "program",
    sorted(PROGRAMS_DIR.glob("*.cbl")),
    ids=lambda path: path.stem,
)
def test_seed_program_compiles_with_gnucobol(program: Path):
    result = subprocess.run(
        [COBC, "-fsyntax-only", "-I", str(PROGRAMS_DIR), str(program)],
        cwd=PROGRAMS_DIR,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"{program.name} failed cobc -fsyntax-only\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
