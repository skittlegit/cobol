"""T2.2 gates for mutation operators, diversification, and ladder honesty."""

from __future__ import annotations

import dataclasses
import json
import random
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.mutate import (
    _STALE_GRIDS,
    ClauseDataError,
    ClauseRecord,
    MutationRejected,
    MutationResult,
    ProgramSource,
    _apply_mo3,
    _exact_wrong_value,
    _flatten_value,
    _is_floor,
    _leaf_kind,
    _stale_value,
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
from cobol_archaeologist.model.run_cobol import run_cobol
from cobol_archaeologist.schemas import DriftInstance
from cobol_archaeologist.tool_types import RunInputs

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


def _substitution_record(record: ClauseRecord) -> ClauseRecord:
    """Same clause with check.d4_mode stripped, so MO-4 takes the literal-
    substitution path (the country-code style realization) rather than the
    clause-driven member_removal path."""
    return dataclasses.replace(
        record,
        check={key: value for key, value in record.check.items() if key != "d4_mode"},
    )


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
            # Exercises the untouched literal-substitution path: a country-code
            # style list, i.e. a clause WITHOUT check.d4_mode. The clause-driven
            # member_removal path is covered by the D4 reference-list hosts in
            # test_benchmark_build.
            _substitution_record(records["KYC-ovd-list"]),
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


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
@pytest.mark.parametrize(
    ("relative_path", "touched_variables", "record_id", "operator"),
    [
        (
            "train-bases/ACTIVAT1.cbl",
            ("WS-DAYS-SINCE-ISSUE", "WS-CONSENT-DAYS", "WS-ACTION"),
            "CC-06a-vi",
            "MO-2",
        ),
        (
            "train-bases/CICREP1.cbl",
            ("WS-DAYS-SINCE-SETTLE", "WS-ACTION"),
            "CC-12b",
            "MO-2",
        ),
        (
            "train-bases/CICREP1.cbl",
            ("WS-DAYS-SINCE-SETTLE", "WS-ACTION"),
            "CC-12b",
            "MO-6",
        ),
    ],
)
def test_nested_if_operator_hosts_compile(
    relative_path: str,
    touched_variables: tuple[str, ...],
    record_id: str,
    operator: str,
):
    base = _seed(relative_path, touched_variables=touched_variables)

    result = mutate(base, _clause(record_id), operator, random.Random(2404))

    assert result.validation.level == "compiled"


def test_mo2_retains_success_guard_instead_of_orphaning_due_date_flow():
    base = _seed(
        "train-bases/KYCSYNC3.cbl",
        touched_variables=("WS-TODAY-DAY", "WS-DUE-DAY", "WS-STATUS"),
    )

    result = mutate(
        base,
        _clause("KYC-ckycr-update"),
        "MO-2",
        random.Random(2404),
    )

    expected_level = "compiled" if shutil.which("cobc") else "ast"
    assert result.validation.level == expected_level
    assert "COMPUTE WS-DUE-DAY = WS-RECEIPT-DAY + 7" in result.source.text
    assert "IF WS-TODAY-DAY <= WS-DUE-DAY" in result.source.text
    assert "MOVE 'OK' TO WS-STATUS" in result.source.text
    assert "MOVE 'OVERDUE' TO WS-STATUS" not in result.source.text


def test_mo2_ignores_control_keywords_and_variables_inside_literals():
    base = ProgramSource(
        program="LITCTRL1",
        filename="LITCTRL1.cbl",
        text="""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LITCTRL1.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-DAYS PIC 9(4) VALUE ZERO.
       01  WS-STATUS PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           DISPLAY 'IF WS-DAYS ELSE END-IF'
           IF WS-DAYS > 7
              MOVE 'OVERDUE' TO WS-STATUS
           ELSE
              MOVE 'INSLA' TO WS-STATUS
           END-IF
           DISPLAY WS-STATUS
           STOP RUN.
""",
        kind="native",
        touched_variables=("WS-DAYS", "WS-STATUS"),
    )

    result = mutate(
        base,
        _clause("KYC-ckycr-update"),
        "MO-2",
        random.Random(2404),
    )

    expected_level = "compiled" if shutil.which("cobc") else "ast"
    assert result.validation.level == expected_level
    assert "DISPLAY 'IF WS-DAYS ELSE END-IF'" in result.source.text
    assert "IF WS-DAYS <= 7" in result.source.text
    assert "MOVE 'OVERDUE' TO WS-STATUS" not in result.source.text


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
@pytest.mark.parametrize(
    ("relative_path", "touched_variables", "record_id", "operator"),
    [
        (
            "train-bases/ACTRECON2.cbl",
            ("WS-DAYS-SINCE-ISSUE", "WS-ACTIVATED", "WS-ACTION"),
            "CC-06a-vi",
            "MO-2",
        ),
        (
            "train-bases/CKYQUEUE2.cbl",
            ("WS-QUEUE-AGE", "WS-ROUTE"),
            "KYC-ckycr-update",
            "MO-2",
        ),
        (
            "train-bases/OVDROUT2.cbl",
            ("WS-OVD-CODE", "WS-ROUTE"),
            "KYC-ovd-list",
            "MO-4",
        ),
        (
            "train-bases/SANCBAT2.cbl",
            ("WS-LIST-SOURCE", "WS-BATCH-ROUTE"),
            "KYC-unsc-screening",
            "MO-4",
        ),
        (
            "train-bases/CLSRUN7.cbl",
            ("WS-CLOSE-DAYS", "WS-PENALTY-AMT"),
            "CC-08a",
            "MO-6",
        ),
        (
            "train-bases/INTROLL2.cbl",
            ("WS-INT-BASE", "WS-INTEREST-AMT"),
            "CC-09b-ii",
            "MO-6",
        ),
        (
            "train-bases/CICROLL2.cbl",
            ("WS-DAYS-SINCE-SETTLE", "WS-CIC-ACTION"),
            "CC-12b",
            "MO-6",
        ),
    ],
)
def test_purpose_authored_operator_hosts_compile(
    relative_path: str,
    touched_variables: tuple[str, ...],
    record_id: str,
    operator: str,
):
    """The anti-concentration bases must survive the real compiler after mutation."""

    base = _seed(relative_path, touched_variables=touched_variables)
    result = mutate(base, _clause(record_id), operator, random.Random(2404))

    assert result.validation.level == "compiled"
    if operator == "MO-2":
        assert "<=" in result.source.text
        assert "REVIEW" in result.source.text or "PENDING" in result.source.text
    elif operator == "MO-4":
        assert result.source.files != base.files
        assert "new='(deleted)'" in (result.instance.provenance.mutation or "")
    else:
        assert "VALUE 'N'" in result.source.text
        assert "WS-COMPLIANCE-FLAG" not in result.source.text


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
@pytest.mark.parametrize(
    ("relative_path", "touched_variables", "record_id", "stdin", "before", "after"),
    [
        (
            "train-bases/CLSRUN7.cbl",
            ("WS-CLOSE-DAYS", "WS-PENALTY-AMT"),
            "CC-08a",
            "10\n",
            "PENALTY: 000001500",
            "PENALTY: 000000000",
        ),
        (
            "train-bases/INTROLL2.cbl",
            ("WS-INT-BASE", "WS-INTEREST-AMT"),
            "CC-09b-ii",
            "1000\n100\n0\n",
            "INTEREST: 000002700",
            "INTEREST: 000000000",
        ),
        (
            "train-bases/CICROLL2.cbl",
            ("WS-DAYS-SINCE-SETTLE", "WS-CIC-ACTION"),
            "CC-12b",
            "10\nN\n",
            "CIC: UPDATE",
            "CIC: DEFER",
        ),
    ],
)
def test_purpose_authored_mo6_flags_disable_live_regulated_paths(
    relative_path: str,
    touched_variables: tuple[str, ...],
    record_id: str,
    stdin: str,
    before: str,
    after: str,
):
    base = _seed(relative_path, touched_variables=touched_variables)
    result = mutate(base, _clause(record_id), "MO-6", random.Random(2404))

    base_run = run_cobol(base.text, RunInputs(stdin=stdin))
    mutant_run = run_cobol(result.source.text, RunInputs(stdin=stdin))

    assert base_run.compiled_ok and base_run.exit_code == 0
    assert mutant_run.compiled_ok and mutant_run.exit_code == 0
    assert before in base_run.stdout
    assert after in mutant_run.stdout


def test_mo5_targets_the_partnership_branch_not_same_valued_corporate_branch():
    base = _seed(
        "train-bases/BOIDENT3.cbl",
        touched_variables=("WS-OWN-PCT", "WS-CTRL-IND", "WS-IS-BO"),
    )

    result = mutate(
        base,
        _clause("KYC-bo-threshold"),
        "MO-5",
        random.Random(2404),
    )

    lines = result.source.text.splitlines()
    corporate = next(index for index, line in enumerate(lines) if "WHEN 'C'" in line)
    partnership = next(index for index, line in enumerate(lines) if "WHEN 'P'" in line)
    assert "> 10.00" in lines[corporate + 1]
    assert ">= 10.00" in lines[partnership + 1]


def test_mo6_can_omit_a_real_rule_loader_instead_of_inventing_a_false_flag():
    base = _seed(
        "train-bases/INTROLL2.cbl",
        touched_variables=("WS-INT-BASE", "WS-INTEREST-AMT"),
    )

    result = mutate(base, _clause("CC-09b-ii"), "MO-6", random.Random(2404))

    assert "PERFORM 1500-LOAD-INTEREST-RULE" in base.text
    assert "PERFORM 1500-LOAD-INTEREST-RULE" not in result.source.text
    assert "1500-LOAD-INTEREST-RULE." in result.source.text
    assert "MOVE 'Y' TO WS-INTEREST-RULE-FLAG" in result.source.text
    assert "WS-COMPLIANCE-FLAG" not in result.source.text


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
    assert "MOVE 102 TO WS-FAIL-REASON" in result.source.text
    assert "IF WS-FAIL-REASON = ZERO" in result.source.text
    assert "OR WS-LIMIT = ZERO" in result.source.text
    assert result.instance.code_locus.is_interprocedural
    assert {locus.paragraph for locus in result.instance.code_locus.loci} >= {
        "1000-MAIN",
        "2000-VALIDATE",
    }


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
@pytest.mark.parametrize(
    ("relative_path", "touched_variables", "zero_limit", "configured", "in_limit"),
    [
        (
            "test-bases-x/TRNVAL1.cbl",
            ("WS-LIMIT", "WS-PROJ-BAL", "WS-FAIL-REASON", "WS-POSTED"),
            "0\n100\n",
            "50\n100\n",
            "100\n50\n",
        ),
        (
            "OVRLIM1.cbl",
            ("WS-CONSENT-ON-FILE", "WS-PROJECTED-BAL", "WS-CREDIT-LIMIT"),
            "100\n0\nN\nN\n",
            "100\n50\nN\nN\n",
            "50\n100\nN\nN\n",
        ),
    ],
)
def test_mo3x_zero_limit_exception_is_narrow_not_vacuous(
    relative_path: str,
    touched_variables: tuple[str, ...],
    zero_limit: str,
    configured: str,
    in_limit: str,
):
    result = mutate(
        _seed(relative_path, touched_variables=touched_variables),
        _clause("CC-06b-v"),
        "MO-3×",
        random.Random(2312),
    )

    outputs = [
        run_cobol(result.source.text, RunInputs(stdin=stdin))
        for stdin in (zero_limit, configured, in_limit)
    ]

    assert all(output.compiled_ok and output.exit_code == 0 for output in outputs)
    assert [output.stdout for output in outputs] == [
        "POSTED: Y\n",
        "POSTED: N\n",
        "POSTED: Y\n",
    ]


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
    # MO-0 is now a matched numeric control (BL-14): it perturbs a decorative
    # numeric so "was this edited" carries no label information, rather than
    # nudging a DISPLAY string the drift operators never touch.
    mo0 = emitted["MO-0"]
    assert {edit.kind for edit in mo0.surface_edits} & {"inert_numeric"}
    assert "DISPLAY 'XO" not in mo0.source.text

    mo2 = emitted["MO-2"].source.text
    assert "IF WS-DAYS-SINCE-UPD <= 7" in mo2
    assert "MOVE 'INSLA' TO WS-SLA-STATUS" in mo2
    assert "CONTINUE (required check removed)" not in mo2
    assert "MOVE 'OVERDUE' TO WS-SLA-STATUS" not in mo2

    mo3 = emitted["MO-3"].source.text
    assert "IF WS-DAYS-PAST-DUE > ZERO" in mo3
    assert "OR WS-OUTSTANDING-AMT > ZERO" not in mo3
    assert "IF WS-DAYS-PAST-DUE <= 3" not in mo3

    mo3x = emitted["MO-3×"].source.text
    assert "MOVE 'N' TO WS-CONSENT-ON-FILE" in mo3x
    assert "IF WS-CONSENT-REC-FOUND = 'Y'" in mo3x
    assert "IF WS-CONSENT-ON-FILE NOT = 'Y'" in mo3x
    assert "OR WS-CREDIT-LIMIT = ZERO" in mo3x

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
    # 5, not the retired current*1.1 fallback's 3: duration_years drifts on the
    # lineage's own grid (T2.4b). The targeting this test guards is unchanged.
    assert "IF WS-YEARS-SINCE-KYC >= 5" in result.source.text
    # 27, not 25: the T0.2 cruft pass added two WORKING-STORAGE lines above
    # the procedure. The targeting this test guards is unchanged.
    assert result.instance.code_locus.loci[0].line_span == (27, 27)


def test_mo1_stale_values_are_verified_priors_or_on_the_clause_grid():
    """A D1 threshold must be real history or a believable former value.

    The retired ``current * 1.1`` fallback emitted off-grid thresholds -- a
    33-day SLA no maintainer ever wrote -- which the judge read as generated.
    Every MO-1 stale value now resolves either to a recorded prior version or
    onto the grid its ``kind`` actually takes across the RBI lineage.
    """

    seen: dict[str, int] = {"prior_verified": 0, "grid_fallback": 0}
    refused = 0
    undeclared: list[str] = []
    for record in load_clause_records(CLAUSES_PATH):
        if "MO-1" not in record.check.get("mutation_ops", ()):
            continue
        current = record.clause.current_value
        assert current is not None, record.record_id
        for path, value in _flatten_value(current):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            kind = _leaf_kind(current, path)
            if record.check.get("mo1_mode") == "exact_wrong":
                # A fixed statutory constant is exempt from the direction rule,
                # but only because the clause *declares* it is -- the exemption
                # must be earned by data, not by a missing comparator.
                stale, source = _exact_wrong_value(
                    record, float(value), random.Random(7)
                )
                assert source == "exact_wrong"
                assert stale != float(value)
                seen.setdefault(source, 0)
                seen[source] += 1
                continue
            try:
                is_floor = _is_floor(current, path, record.record_id)
            except ClauseDataError:
                # BL-15: absence must fail loudly, never default to ceiling.
                undeclared.append(f"{record.record_id}.{path or '<root>'}")
                continue
            try:
                stale, source = _stale_value(
                    record, float(value), random.Random(7), kind, is_floor=is_floor
                )
            except MutationRejected as exc:
                # A leaf already at the lax end of its grid has no believable
                # laxer former value (a 10-year ceiling is the loosest the KYC
                # lineage ever ran). MO-1 refuses rather than invert direction.
                assert "no laxer" in str(exc), f"{record.record_id}.{path}: {exc}"
                refused += 1
                continue
            assert stale != float(value), f"{record.record_id}.{path} did not move"
            seen[source] += 1
            grid = _STALE_GRIDS.get(kind or "")
            if source == "grid_fallback" and grid:
                assert stale in grid, (
                    f"{record.record_id}.{path}: {stale} is off-grid for {kind}"
                )
                # The conceptual invariant, asserted so the next at_least clause
                # to enter the set fails loudly rather than drifting the wrong
                # way: stale is laxer for the obligated party. Floors never snap
                # up, ceilings never snap down.
                if is_floor:
                    assert stale < float(value), (
                        f"{record.record_id}.{path}: floor clause snapped up "
                        f"({value} -> {stale}) -- that encodes the regulator "
                        "loosening the rule, the opposite of drift"
                    )
                else:
                    assert stale > float(value), (
                        f"{record.record_id}.{path}: ceiling clause snapped down "
                        f"({value} -> {stale})"
                    )
    # BL-15 gate: every leaf an operator can target declares its comparator, so
    # the stale side is read from the clause and never inferred.
    assert not undeclared, (
        f"{len(undeclared)} MO-targetable leaves declare no comparator, so their "
        "stale side would be guessed (BL-15): " + ", ".join(undeclared)
    )
    # Both arms must stay exercised: all-synthesis would mean the curated prior
    # versions are unwired, all-prior would leave the fallback untested.
    assert seen["prior_verified"] >= 1
    assert seen["grid_fallback"] >= 1


def test_mo3_emits_semantic_contradictions_not_boolean_inversions():
    """MO-3 must not weaken a rule by making its branch unreachable.

    ``IF WS-BASE > ZERO`` -> ``<= ZERO`` charges interest only when nothing is
    owed: an always-false guard is not drift a maintainer ships, and the judge
    rejected it as artificial. An AND/OR flip is equally mechanical. Every D3
    host resolves to a recognized contradiction shape -- a retained pre-grace
    policy or a re-capitalized base.
    """

    late_fee = _seed(
        "LATEFEE1.cbl", touched_variables=("WS-DAYS-PAST-DUE", "WS-LATE-CHARGE")
    )
    late_fee_new = _seed(
        "train-bases/LATEFEE2.cbl",
        touched_variables=("WS-DAYS-PAST-DUE", "WS-OUTSTANDING", "WS-CHARGE"),
    )
    interest = _seed(
        "train-bases/INTCOMP1.cbl",
        touched_variables=("WS-BASE", "WS-UNPAID-FEES", "WS-CREDITS", "WS-INT"),
    )

    # Both grace hosts retain the coherent pre-grace policy: any day past due
    # may be charged. This is a business-rule mismatch, not a Boolean token flip.
    for base in (late_fee, late_fee_new):
        text = _apply_mo3(base).source.text
        assert "IF WS-DAYS-PAST-DUE > ZERO" in text
        assert " OR " not in text
        assert "IF WS-DAYS-PAST-DUE <= 3" not in text

    # The interest base drops its unpaid-charges term, so unpaid fees start
    # accruing interest -- the contradiction CC-09b-ii names. The field is still
    # ACCEPTed, which is what makes the edit read as a maintainer's slip.
    plan = _apply_mo3(interest)
    assert "- WS-UNPAID-FEES" not in plan.source.text
    assert "ACCEPT WS-UNPAID-FEES" in plan.source.text
    assert "IF WS-BASE <= ZERO" not in plan.source.text
    assert len(plan.source.text.splitlines()) == len(interest.text.splitlines())


@pytest.mark.skipif(shutil.which("cobc") is None, reason="cobc unavailable")
def test_mo3_pre_grace_policy_is_behaviorally_coherent_and_contradictory():
    base = _seed(
        "train-bases/LATEFEE2.cbl",
        touched_variables=("WS-DAYS-PAST-DUE", "WS-OUTSTANDING", "WS-CHARGE"),
    )
    result = mutate(
        base,
        _clause("CC-09b-v"),
        "MO-3",
        random.Random(2404),
    )

    outputs = [
        run_cobol(result.source.text, RunInputs(stdin=f"100\n{days}\n"))
        for days in (0, 1, 4)
    ]

    assert all(output.compiled_ok and output.exit_code == 0 for output in outputs)
    assert [output.stdout for output in outputs] == [
        "CHARGE: 000000000\n",
        "CHARGE: 000000250\n",
        "CHARGE: 000000250\n",
    ]


def test_mo1_moves_every_coupled_occurrence_of_the_regulated_literal():
    """A partial threshold edit is incoherence, not drift.

    CLOSPEN6 compares against the SLA window and subtracts it in the penalty
    arithmetic. Moving only the comparison leaves a program that charges nothing
    at 8 days and a full day's penalty at 9 -- a self-contradiction no
    maintainer would ship. Occurrences proven coupled by def-use move together.
    """

    base = _seed(
        "train-bases/CLOSPEN6.cbl",
        touched_variables=("WS-REQ-DAYS", "WS-TOT-PENALTY"),
        target_path="closure_window",
    )
    result = mutate(base, _clause("CC-08a"), "MO-1", random.Random(2601))

    text = result.source.text
    assert "IF WS-REQ-DAYS (WS-IDX) > 10" in text
    assert "(WS-REQ-DAYS (WS-IDX) - 10)" in text
    assert "- 7)" not in text
    assert len(result.instance.labels.line_level) == 2


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
