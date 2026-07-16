"""T2.2 gates for mutation operators, diversification, and ladder honesty."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.mutate import (
    ClauseRecord,
    MutationResult,
    ProgramSource,
    load_clause_records,
    mutate,
    seed_mutation_plan,
)
from cobol_archaeologist.benchmark.surface import (
    FEATURE_NAMES,
    diversify,
    load_probe_rows,
    surface_probe_report,
)
from cobol_archaeologist.schemas import DriftInstance


REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUSES_PATH = REPO_ROOT / "data" / "regulations" / "clauses.jsonl"
SEED_DIR = REPO_ROOT / "data" / "benchmark" / "seed"
PROGRAMS_DIR = SEED_DIR / "programs"
PROBE_PATH = REPO_ROOT / "data" / "benchmark" / "probes" / "t2.2_surface_probe.jsonl"

ALL_OPERATORS = {
    "MO-0",
    "MO-1",
    "MO-2",
    "MO-3",
    "MO-4",
    "MO-5",
    "MO-6",
    "MO-1×",
    "MO-3×",
    "MO-6×",
}

EXPECTED_DRIFT_TYPES = {
    "MO-0": "D7_conformant",
    "MO-1": "D1_stale_threshold",
    "MO-2": "D2_missing_rule",
    "MO-3": "D3_contradictory",
    "MO-4": "D4_stale_reference_data",
    "MO-5": "D5_boundary_error",
    "MO-6": "D6_dead_code",
    "MO-1×": "D1_stale_threshold",
    "MO-3×": "D3_contradictory",
    "MO-6×": "D6_dead_code",
}


REFERENCE_LIST = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REFLIST1.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY WSREFLST.
       01  WS-RESULT PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM 2000-CHECK-COUNTRY
           DISPLAY 'VALID: ' WS-RESULT
           STOP RUN.
       2000-CHECK-COUNTRY.
           IF VALID-COUNTRY
              MOVE 'Y' TO WS-RESULT
           END-IF.
"""

REFERENCE_COPYBOOK = """\
       01  WS-COUNTRY PIC X(2) VALUE 'IN'.
           88 VALID-COUNTRY VALUES 'IN', 'GB', 'US'.
"""

REFUND_PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REFUNDC1.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY WSREFUND.
       01  WS-CREDIT PIC 9(7) VALUE ZERO.
       01  WS-CONSENT PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CREDIT
           PERFORM 2000-CHECK-CUTOFF
           DISPLAY 'CONSENT: ' WS-CONSENT
           STOP RUN.
       2000-CHECK-CUTOFF.
           IF WS-CREDIT > WS-CUTOFF-AMOUNT
              MOVE 'Y' TO WS-CONSENT
           END-IF.
"""

REFUND_COPYBOOK = """\
       01  WS-REFUND-CUTOFFS.
           05  WS-CUTOFF-PCT PIC V99 VALUE .01.
           05  WS-CUTOFF-AMOUNT PIC 9(7) VALUE 5000.
"""

LIMIT_GATE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LIMITGAT.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LIMIT PIC 9(5) VALUE 1000.
       01  WS-BALANCE PIC 9(5) VALUE ZERO.
       01  WS-VALID PIC X VALUE 'N'.
       01  WS-POSTED PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-BALANCE
           PERFORM 2000-VALIDATE
           IF WS-VALID = 'Y'
              PERFORM 3000-POST
           END-IF
           DISPLAY 'POSTED: ' WS-POSTED
           STOP RUN.
       2000-VALIDATE.
           IF WS-BALANCE <= WS-LIMIT
              MOVE 'Y' TO WS-VALID
           END-IF.
       3000-POST.
           MOVE 'Y' TO WS-POSTED.
"""

NO_CAPITALIZATION = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NOCAP1.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-BALANCE PIC 9(7) VALUE ZERO.
       01  WS-ALLOW-CHARGE-CAP PIC X VALUE 'N'.
       01  WS-INTEREST PIC 9(7)V99 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-BALANCE
           PERFORM 2000-COMPUTE-INTEREST
           DISPLAY 'INTEREST: ' WS-INTEREST
           STOP RUN.
       2000-COMPUTE-INTEREST.
           IF WS-ALLOW-CHARGE-CAP = 'N'
              COMPUTE WS-INTEREST = WS-BALANCE * .01
           END-IF.
"""

NO_CAP_SUBPROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NOCAPSUB.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-BALANCE PIC 9(7) VALUE ZERO.
       01  WS-ALLOW-CHARGE-CAP PIC X VALUE 'N'.
       01  WS-INTEREST PIC 9(7)V99 VALUE ZERO.
       LINKAGE SECTION.
       01  LK-COMPLIANCE-ENABLED PIC X.
       PROCEDURE DIVISION USING LK-COMPLIANCE-ENABLED.
       1000-MAIN.
           IF LK-COMPLIANCE-ENABLED = 'Y'
              PERFORM 2000-COMPUTE-INTEREST
           END-IF
           GOBACK.
       2000-COMPUTE-INTEREST.
           IF WS-ALLOW-CHARGE-CAP = 'N'
              COMPUTE WS-INTEREST = WS-BALANCE * .01
           END-IF.
"""

BATCH_CONTROLLER = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BATCHCTL.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COMPLIANCE-ENABLED PIC X VALUE 'Y'.
       PROCEDURE DIVISION.
       1000-MAIN.
           CALL 'NOCAPSUB' USING WS-COMPLIANCE-ENABLED
           STOP RUN.
"""


def _seed(name: str, **kwargs) -> ProgramSource:
    return ProgramSource.from_path(PROGRAMS_DIR / name, **kwargs)


def _records_by_id() -> dict[str, ClauseRecord]:
    return {record.record_id: record for record in load_clause_records(CLAUSES_PATH)}


def _conformant_late_fee() -> ProgramSource:
    source = (PROGRAMS_DIR / "LATEFEE1.cbl").read_text(encoding="utf-8")
    source = source.replace(
        "= WS-LATE-RATE * WS-TOTAL-AMT-DUE",
        "= WS-LATE-RATE * WS-OUTSTANDING-AMT",
    )
    return ProgramSource(
        program="LATEFEE1",
        filename="LATEFEE1.cbl",
        text=source,
        kind="native",
        touched_variables=("WS-DAYS-PAST-DUE", "WS-LATE-CHARGE"),
        target_path="past_due_grace",
    )


def _conformant_penalty_pilot() -> ProgramSource:
    source = (PROGRAMS_DIR / "CLOSPEN5.cbl").read_text(encoding="utf-8")
    source = source.replace(
        "WS-PEN-ENABLED        PIC X(1) VALUE 'N'.",
        "WS-PEN-ENABLED        PIC X(1) VALUE 'Y'.",
        1,
    )
    return ProgramSource(
        program="CLOSPEN5",
        filename="CLOSPEN5.cbl",
        text=source,
        kind="native",
        touched_variables=("WS-PEN-ENABLED", "WS-PENALTY-AMT"),
        target_path="penalty_per_day",
    )


def _cases() -> dict[str, tuple[ProgramSource, ClauseRecord]]:
    records = _records_by_id()
    return {
        "MO-0": (
            _seed(
                "BOIDENT2.cbl",
                touched_variables=("WS-BO-THRESHOLD", "WS-IS-BO"),
            ),
            records["KYC-bo-threshold"],
        ),
        "MO-1": (
            _seed(
                "BOIDENT2.cbl",
                touched_variables=("WS-BO-THRESHOLD", "WS-IS-BO"),
            ),
            records["KYC-bo-threshold"],
        ),
        "MO-2": (
            _seed(
                "KYCSYNC2.cbl",
                touched_variables=("WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"),
            ),
            records["KYC-ckycr-update"],
        ),
        "MO-3": (_conformant_late_fee(), records["CC-09b-v"]),
        "MO-4": (
            ProgramSource(
                program="REFLIST1",
                filename="REFLIST1.cbl",
                text=REFERENCE_LIST,
                kind="native",
                files={"WSREFLST.cpy": REFERENCE_COPYBOOK},
                touched_variables=("WS-COUNTRY",),
            ),
            records["KYC-ovd-list"],
        ),
        "MO-5": (
            _seed(
                "KYCSYNC2.cbl",
                touched_variables=("WS-DAYS-SINCE-UPD", "WS-SLA-STATUS"),
            ),
            records["KYC-ckycr-update"],
        ),
        "MO-6": (_conformant_penalty_pilot(), records["CC-08a"]),
        "MO-1×": (
            ProgramSource(
                program="REFUNDC1",
                filename="REFUNDC1.cbl",
                text=REFUND_PROGRAM,
                kind="native",
                files={"WSREFUND.cpy": REFUND_COPYBOOK},
                touched_variables=("WS-CUTOFF-AMOUNT", "WS-CONSENT"),
                target_path="cutoff",
            ),
            records["CC-10h"],
        ),
        "MO-3×": (
            _seed(
                "OVRLIM1.cbl",
                touched_variables=(
                    "WS-CONSENT-ON-FILE",
                    "WS-PROJECTED-BAL",
                    "WS-CREDIT-LIMIT",
                ),
            ),
            records["CC-06b-v"],
        ),
        "MO-6×": (
            ProgramSource(
                program="NOCAPSUB",
                filename="NOCAPSUB.cbl",
                text=NO_CAP_SUBPROGRAM,
                kind="native",
                files={"BATCHCTL.cbl": BATCH_CONTROLLER},
                touched_variables=("LK-COMPLIANCE-ENABLED", "WS-INTEREST"),
            ),
            records["CC-09b-ii"],
        ),
    }


@pytest.fixture(scope="module")
def emitted() -> dict[str, MutationResult]:
    return {
        op: mutate(base, record, op, random.Random(2200 + index))
        for index, (op, (base, record)) in enumerate(_cases().items())
    }


def test_gate_a_targeting_map_covers_every_operator():
    records = load_clause_records(CLAUSES_PATH)
    tokens = {
        token for record in records for token in record.check.get("mutation_ops", [])
    }
    assert ALL_OPERATORS - {"MO-0"} <= tokens
    assert not {token for token in tokens if token.endswith("x")}


def test_gate_a_every_operator_emits_validated_instance(emitted):
    assert set(emitted) == ALL_OPERATORS
    for op, result in emitted.items():
        assert result.validation.ok, (op, result.validation.messages)
        assert result.instance.drift_type == EXPECTED_DRIFT_TYPES[op]
        assert result.surface_edits, f"{op} omitted style diversification"


def test_gate_a_cross_variants_are_genuinely_interprocedural(emitted):
    for op in ("MO-1×", "MO-3×", "MO-6×"):
        locus = emitted[op].instance.code_locus
        assert locus.is_interprocedural is True
        coordinates = {(item.program, item.file, item.paragraph) for item in locus.loci}
        assert len(coordinates) >= 2


def _clause(record_id: str) -> ClauseRecord:
    return next(
        record
        for record in load_clause_records(CLAUSES_PATH)
        if record.record_id == record_id
    )


def test_corrective_mo1x_emits_from_authored_copybook_host():
    base = ProgramSource.from_path(
        PROGRAMS_DIR / "test-bases-x" / "REFADJ2.cbl",
        touched_variables=("WS-CUTOFF-CAP", "WS-CUTOFF", "WS-REFUND-AMT"),
        target_path="cutoff",
    )
    result = mutate(base, _clause("CC-10h"), "MO-1×", random.Random(2311))

    assert result.validation.ok
    assert "VALUE 6000" in result.source.files["WSCUTOFF.cpy"]
    assert result.instance.code_locus.is_interprocedural
    assert {locus.file for locus in result.instance.code_locus.loci} == {
        None,
        "WSCUTOFF.cpy",
    }


def test_corrective_mo3x_emits_from_authored_validate_gate_post_host():
    base = ProgramSource.from_path(
        PROGRAMS_DIR / "test-bases-x" / "TRNVAL1.cbl",
        touched_variables=(
            "WS-LIMIT",
            "WS-PROJ-BAL",
            "WS-FAIL-REASON",
            "WS-POSTED",
        ),
    )
    result = mutate(base, _clause("CC-06b-v"), "MO-3×", random.Random(2312))

    assert result.validation.ok
    assert "MOVE 102 TO WS-FAIL-REASON" not in result.source.text
    assert "IF WS-FAIL-REASON = ZERO" in result.source.text
    assert result.instance.code_locus.is_interprocedural
    assert {locus.paragraph for locus in result.instance.code_locus.loci} >= {
        "1000-MAIN",
        "2000-VALIDATE",
    }


def test_corrective_mo6x_emits_from_rostered_batch_chain():
    directory = PROGRAMS_DIR / "test-bases-x"
    base = ProgramSource.from_path(
        directory / "BATCHCT2.cbl",
        files={
            "BATCHCT1.cbl": (directory / "BATCHCT1.cbl").read_text(encoding="utf-8"),
            "WSCTLFLG.cpy": (directory / "WSCTLFLG.cpy").read_text(encoding="utf-8"),
        },
        touched_variables=("WS-PEN-RUN-FLAG", "WS-PENALTY"),
    )
    result = mutate(base, _clause("CC-09b-ii"), "MO-6×", random.Random(2313))

    assert result.validation.ok
    assert "MOVE 'N' TO WS-PEN-RUN-FLAG" in result.source.files["BATCHCT1.cbl"]
    assert "IF PEN-RUN-ON" in result.source.text
    assert result.instance.code_locus.is_interprocedural
    assert {locus.program for locus in result.instance.code_locus.loci} >= {
        "BATCHCT1",
        "BATCHCT2",
    }


def test_gate_a_loci_are_sorted_for_pair_stability(emitted):
    for result in emitted.values():
        loci = result.instance.code_locus.loci
        keys = [(item.program, item.file or "", item.line_span) for item in loci]
        assert keys == sorted(keys)


def test_gate_a_seed_plan_reports_unhosted_synthetic_records():
    plan = seed_mutation_plan(
        load_clause_records(CLAUSES_PATH),
        PROGRAMS_DIR,
        SEED_DIR / "real_curated.jsonl",
    )
    assert {
        "CC-08a",
        "KYC-periodic-updation",
        "KYC-bo-threshold",
        "KYC-ckycr-update",
    } <= {item.record_id for item in plan.hosted}
    assert plan.skipped_synthetic_record_ids
    assert set(plan.skipped_synthetic_record_ids).isdisjoint(
        {item.record_id for item in plan.hosted}
    )


def test_gate_b_every_instance_round_trips_frozen_schema(emitted):
    for result in emitted.values():
        first = DriftInstance.model_validate(result.instance.model_dump())
        second = DriftInstance.model_validate_json(first.model_dump_json())
        assert second == first


def test_gate_b_labels_and_provenance_follow_contract(emitted):
    for op, result in emitted.items():
        instance = result.instance
        assert instance.provenance.source == "synthetic"
        assert instance.provenance.base_program == result.source.filename
        mutation = instance.provenance.mutation or ""
        for required in (op, "locus=", "old=", "new=", "validation="):
            assert required in mutation
        assert instance.code_locus.slice_vars
        if op == "MO-2":
            assert instance.labels.line_level


def test_plausibility_shapes_avoid_generator_sentinels(emitted):
    mo0 = emitted["MO-0"].source.text
    assert "DISPLAY 'BO= '" in mo0
    assert "DISPLAY 'XO" not in mo0

    mo2 = emitted["MO-2"].source.text
    assert "MOVE 'INSLA' TO WS-SLA-STATUS." in mo2
    assert "CONTINUE (required check removed)" not in mo2
    assert "IF WS-DAYS-SINCE-UPD" not in mo2

    mo3 = emitted["MO-3"].source.text
    assert "IF WS-DAYS-PAST-DUE > 3" in mo3
    assert "OR WS-OUTSTANDING-AMT > ZERO" in mo3
    assert "IF WS-DAYS-PAST-DUE <= 3" not in mo3

    mo3x = emitted["MO-3×"].source.text
    assert "MOVE 'N' TO WS-CONSENT-ON-FILE" not in mo3x
    assert "IF WS-CONSENT-REC-FOUND = 'Y'" in mo3x
    assert "IF WS-CONSENT-ON-FILE NOT = 'Y'" in mo3x

    mo6 = emitted["MO-6"].source.text
    assert "WS-PEN-ENABLED        PIC X(1) VALUE 'N'." in mo6
    assert "IF PENALTY-ON" in mo6
    assert "WS-COMPLIANCE-FLAG" not in mo6

    mo4 = emitted["MO-4"].source.files["WSREFLST.cpy"]
    assert "VALUES 'IN', 'GB', 'CA'" in mo4
    assert "'ZZ'" not in mo4


def test_gate_b_deterministic_with_fixed_seed():
    for index, (op, (base, record)) in enumerate(_cases().items()):
        left = mutate(base, record, op, random.Random(9000 + index))
        right = mutate(base, record, op, random.Random(9000 + index))
        assert left.to_json() == right.to_json(), op


def test_gate_b_composite_target_paths_resolve(emitted):
    assert emitted["MO-3"].instance.target_path == "past_due_grace"
    assert emitted["MO-1×"].instance.target_path == "cutoff"


def test_mo1_targets_business_condition_before_matching_pic_width():
    records = _records_by_id()
    base = _seed(
        "KYCSCHED1.cbl",
        touched_variables=("WS-YEARS-SINCE-KYC", "WS-RISK-RATING"),
        target_path="high_risk",
    )
    result = mutate(
        base,
        records["KYC-periodic-updation"],
        "MO-1",
        random.Random(2251),
    )
    assert "PIC 9(2) VALUE ZERO" in result.source.text
    assert "IF WS-YEARS-SINCE-KYC >= 3" in result.source.text
    assert result.instance.code_locus.loci[0].line_span == (25, 25)


def test_surface_diversification_is_deterministic_and_line_preserving():
    source = (PROGRAMS_DIR / "BOIDENT2.cbl").read_text(encoding="utf-8")
    left = diversify(source, (18, 30), random.Random(44))
    right = diversify(source, (18, 30), random.Random(44))
    assert left == right
    assert left != source
    assert len(left.splitlines()) == len(source.splitlines())


def test_gate_c_balanced_probe_is_at_chance():
    rows = load_probe_rows(PROBE_PATH)
    assert len(rows) >= 100
    labels = [row.label for row in rows]
    assert labels.count(0) >= 50
    assert labels.count(1) >= 50
    assert len({row.source_hash for row in rows}) >= 25
    assert {row.base_program for row in rows} >= {
        "BOIDENT2",
        "KYCSCHED1",
        "KYCSYNC2",
    }
    assert tuple(rows[0].features) == FEATURE_NAMES

    report = surface_probe_report(rows, seed=2250, bootstrap_samples=400)
    assert report.ci_low <= 0.5 <= report.ci_high, report


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
def test_gate_d_compiler_present_and_no_ast_downgrades(emitted):
    assert {result.validation.level for result in emitted.values()} == {"compiled"}
    assert all(
        "validation=compiled" in (result.instance.provenance.mutation or "")
        for result in emitted.values()
    )


def test_probe_artifact_is_jsonl():
    for line_number, line in enumerate(
        PROBE_PATH.read_text(encoding="utf-8").splitlines(), 1
    ):
        record = json.loads(line)
        assert record["label"] in (0, 1), line_number
        assert set(record["features"]) == set(FEATURE_NAMES), line_number
