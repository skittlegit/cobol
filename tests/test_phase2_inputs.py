"""T2.7 gates for the corrected Phase-2/M4 benchmark inputs."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"
SEED = BENCHMARK / "seed"
PROGRAMS = SEED / "programs"
TEST_SPLIT = BENCHMARK / "v1-pre" / "test.jsonl"
SPLIT_FILES = tuple(
    BENCHMARK / "v1-pre" / f"{split}.jsonl"
    for split in ("train", "dev", "test")
)

SUPERSEDED_IDS = {
    "drift_361728",
    "drift_379665",
    "drift_492883",
    "drift_582110",
    "drift_630861",
    "drift_710779",
    "drift_722152",
    "drift_810413",
}
PLAUSIBILITY_EVIDENCE = BENCHMARK / "t2_7_plausibility.jsonl"
STALE_SOURCE_FRAGMENTS = ("WS-SYNC-STATUS", "2000-SET-SYNC-STATUS")
PINNED_CARDDEMO_SOURCES = {
    "CBTRN02C.cbl": "708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f",
    "CBACT04C.cbl": "5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4",
    "CVACT01Y.cpy": "81a08bad15af5664326a6f0af3650f570821c4857ffdec3a6a39f91f07dca728",
    "CVACT03Y.cpy": "ffc6079e09b28739e154bf6c1e1c36d408209faa91f6cf7008078dc596a1c370",
    "CVTRA01Y.cpy": "50637f13692c89b17a2fc60d249dc54e9eb3569d933afca3cdcf65b491a9d5ba",
    "CVTRA02Y.cpy": "7828fae489c59944b4310e223028a8d3a525ccf4ead113c062bcaff04b52bf9c",
    "CVTRA05Y.cpy": "d7bde0e78ff608497087b9909c889ed39e347269f964bda767b92b547fbb5fec",
    "CVTRA06Y.cpy": "c5c69f1b86c5a10156d3c5881d7cf387e6b925aae32825360f85bf4056a554a1",
}


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _locus_key(row: dict) -> str:
    return json.dumps(
        row["code_locus"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _t6_groups(rows: list[dict]) -> list[list[dict]]:
    by_locus: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_locus[_locus_key(row)].append(row)
    return [
        group
        for group in by_locus.values()
        if len(
            {
                (
                    row["regulation_clause"]["version"],
                    row["regulation_clause"]["effective_date"],
                )
                for row in group
            }
        )
        > 1
    ]


def _note_fields(row: dict) -> dict[str, str]:
    note = row["provenance"].get("annotator_notes") or ""
    fields: dict[str, str] = {}
    for segment in note.split(";"):
        key, separator, value = segment.strip().partition("=")
        if separator:
            fields[key] = value
    return fields


def _normalized_program(path: Path) -> str:
    retained: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if len(line) > 6 and line[6] in {"*", "/"}:
            continue
        if "PROGRAM-ID." in line.upper():
            continue
        retained.append(line)
    return re.sub(r"\s+", " ", "\n".join(retained)).strip().upper()


def test_pinned_carddemo_seed_closure_is_self_contained_and_byte_exact():
    for filename, expected_hash in PINNED_CARDDEMO_SOURCES.items():
        path = PROGRAMS / filename
        assert path.is_file()
        canonical = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical).hexdigest() == expected_hash


def test_every_refrozen_test_row_materializes_exactly():
    failures: dict[str, str] = {}
    for raw in _load(TEST_SPLIT):
        row = DriftInstance.model_validate(raw)
        try:
            source = materialize(row)
        except Exception as exc:  # noqa: BLE001 - report the full fail-closed audit
            failures[row.instance_id] = str(exc)
            continue
        assert len(source.source_sha256) == 64
        assert source.main_file == row.provenance.base_program

    assert not failures, failures


def test_superseded_source_drift_ids_are_absent_from_refrozen_splits():
    present = {
        row["instance_id"]
        for path in SPLIT_FILES
        for row in _load(path)
    }
    assert not SUPERSEDED_IDS & present


def test_corrected_catalogue_has_no_stale_source_fragments_or_dangling_ids():
    artifact_paths = (
        BENCHMARK / "drift_instances.jsonl",
        BENCHMARK / "drift_instances.plausible.jsonl",
        BENCHMARK / "judgements.jsonl",
        BENCHMARK / "judgements.sample50.jsonl",
        *SPLIT_FILES,
    )
    for path in artifact_paths:
        text = path.read_text(encoding="utf-8")
        assert not any(fragment in text for fragment in STALE_SOURCE_FRAGMENTS), path
        assert not any(instance_id in text for instance_id in SUPERSEDED_IDS), path


def test_regenerated_synthetic_rows_have_current_plausibility_evidence():
    evidence = {row["instance_id"]: row for row in _load(PLAUSIBILITY_EVIDENCE)}
    replacements = [
        row
        for row in _load(BENCHMARK / "drift_instances.plausible.jsonl")
        if "plausibility=t2_7_plausibility.jsonl"
        in (row["provenance"].get("annotator_notes") or "")
    ]
    assert len(replacements) == len(SUPERSEDED_IDS)
    assert {item["supersedes"] for item in evidence.values()} == SUPERSEDED_IDS

    for raw in replacements:
        row = DriftInstance.model_validate(raw)
        proof = evidence[row.instance_id]
        source = materialize(row)
        main = source.files[source.main_file]

        assert proof["mutated_main_sha256"] == hashlib.sha256(
            main.encode("utf-8")
        ).hexdigest()
        assert proof["verdict"] == "plausible"
        assert proof["reviewer_family"] != "anthropic"
        assert "compiled" in proof["validation"]


def test_t2_7_adds_fifteen_genuine_pairs_across_bounded_lineages():
    rows = _load(SEED / "real_curated.jsonl")
    groups = _t6_groups(rows)
    new_groups = [
        group
        for group in groups
        if all(_note_fields(row).get("task") == "T2.7" for row in group)
    ]

    assert len(groups) >= 20
    assert len(new_groups) >= 15

    lineages: Counter[str] = Counter()
    programs: set[str] = set()
    normalized_bodies: dict[str, str] = {}
    for group in new_groups:
        assert len(group) == 2
        assert {row["labels"]["program_level"] for row in group} == {
            "conformant",
            "drift",
        }
        fields = [_note_fields(row) for row in group]
        assert len({field.get("pair") for field in fields}) == 1
        assert len({field.get("lineage") for field in fields}) == 1
        lineage = fields[0]["lineage"]
        lineages[lineage] += 1

        program_names = {row["provenance"]["base_program"] for row in group}
        assert len(program_names) == 1
        program = program_names.pop()
        programs.add(program)
        path = PROGRAMS / program
        assert path.is_file()
        normalized_bodies[program] = _normalized_program(path)

    assert len(lineages) >= 3
    assert max(lineages.values()) <= 5
    assert len(programs) == len(new_groups)
    assert len(set(normalized_bodies.values())) == len(normalized_bodies)
