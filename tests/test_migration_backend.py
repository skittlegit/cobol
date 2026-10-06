"""Real native compiler and parser checks for the migration backend."""

import hashlib
import json

import pytest

from cobol_archaeologist.migration.backend import (
    ExecutionFixture,
    FixtureProtocol,
    RealValidationBackend,
    SourceAssertion,
)
from cobol_archaeologist.migration.contracts import (
    AllowedSourceScope,
    BehaviorCheck,
    CaseStratum,
    FrozenSource,
    MigrationCase,
    ValidationCapability,
)
from cobol_archaeologist.migration.validate import CheckStatus

SOURCE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEMO.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AMOUNT PIC 9 VALUE ZERO.
       01 WS-RESULT PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN.
           ACCEPT WS-AMOUNT
           PERFORM CHECK-AMOUNT
           DISPLAY WS-RESULT
           STOP RUN.
       CHECK-AMOUNT.
           IF WS-AMOUNT > 5
               MOVE 'Y' TO WS-RESULT
           END-IF.
"""


def make_case(files, *, hosts=()):
    return MigrationCase(
        case_id="migration_backend", instance_id="drift_000001",
        drift_type="D1_stale_threshold", stratum=CaseStratum.LOCAL,
        validation_capability=(ValidationCapability.COPYBOOK_FANOUT if hosts
                               else ValidationCapability.BATCH_EXECUTABLE),
        primary_program="DEMO.cbl",
        frozen_sources=tuple(FrozenSource(path=p, sha256=hashlib.sha256(t.encode()).hexdigest())
                             for p, t in files.items()),
        allowed_source_scope=(AllowedSourceScope(path="DEMO.cbl", line_spans=((14, 14),)),),
        intended_behavior=BehaviorCheck(check_id="intended", description="Above threshold is flagged"),
        unaffected_regressions=(BehaviorCheck(check_id="regression", description="Below threshold remains clear"),),
        affected_hosts=hosts, detector_input_ref="detector.json", oracle_evidence_ref="oracle.json",
        review_protocol_sha256="1" * 64, validation_protocol_sha256="2" * 64,
        review_state="human_primary_reviewed_and_verified", review_evidence_sha256="3" * 64,
        eligible_for_evaluation=True)


def fixture(case, *, host="DEMO", original_main=False):
    kw = ({"run_original_main": True, "stdin": "8\n"} if original_main else
          {"initialize": ("MOVE 8 TO WS-AMOUNT",), "perform": ("CHECK-AMOUNT",), "observe": ("WS-RESULT",)})
    return FixtureProtocol(
        case_id=case.case_id, frozen_sources=case.frozen_sources,
        checks={"intended": (ExecutionFixture(fixture_id="above", host=host,
                                             expected_stdout="Y\n", **kw),)},
        source_assertions=(SourceAssertion(assertion_id="threshold", host=host,
                                          paragraph="CHECK-AMOUNT", literal="WS-AMOUNT > 5"),),
        fixture_authoring_evidence_sha256=hashlib.sha256(SOURCE.encode()).hexdigest())


def require_compiler(backend):
    if backend.compiler is None:
        pytest.skip(backend.capability_receipt()["compiler_error"])


def require_execution(observation):
    if (observation.status == CheckStatus.UNAVAILABLE and
            "Application Control policy has blocked" in observation.log):
        pytest.skip("Observed Windows Application Control execution block: " + observation.log)


def test_real_parser_compiler_and_paragraph_behavior_detect_a_regression():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    backend = RealValidationBackend(fixture(case))
    require_compiler(backend)
    assert backend.parse(case, files).status == CheckStatus.PASS
    assert backend.compile(case, files).status == CheckStatus.PASS
    assert all(c.status == CheckStatus.PASS for c in backend.static(case, files))
    result = backend.behavior(case, files, case.intended_behavior)
    require_execution(result)
    assert result.status == CheckStatus.PASS, result.log
    assert json.loads(result.log)["fixtures"][0]["actual_stdout"] == "Y\n"
    changed = {"DEMO.cbl": SOURCE.replace("WS-AMOUNT > 5", "WS-AMOUNT > 9")}
    regression = backend.behavior(case, changed, case.intended_behavior)
    require_execution(regression)
    assert regression.status == CheckStatus.FAIL
    assert backend.static(case, changed)[1].status == CheckStatus.FAIL


def test_original_main_executes_real_accept_display_without_a_driver():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    backend = RealValidationBackend(fixture(case, original_main=True))
    require_compiler(backend)
    result = backend.behavior(case, files, case.intended_behavior)
    require_execution(result)
    assert result.status == CheckStatus.PASS, result.log
    observed = json.loads(result.log)["fixtures"][0]
    assert observed["instrumented_source_sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()


def test_missing_fixture_missing_static_assertions_and_outside_source_fail_closed():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    proto = fixture(case).model_copy(update={"source_assertions": ()})
    backend = RealValidationBackend(proto)
    assert backend.behavior(case, files, case.unaffected_regressions[0]).status == CheckStatus.UNAVAILABLE
    assert backend.static(case, files)[1].status == CheckStatus.UNAVAILABLE
    outside = {**files, "../outside.cbl": SOURCE}
    assert backend.parse(case, outside).status == CheckStatus.UNAVAILABLE


def test_copybook_expansion_and_host_coverage_are_checked_with_the_real_compiler():
    copy = "       01 WS-AMOUNT PIC 9 VALUE ZERO.\n       01 WS-RESULT PIC X VALUE 'N'.\n"
    source = SOURCE.replace(copy, "           COPY FIELDS.\n")
    files = {"DEMO.cbl": source, "OTHER.cbl": source.replace("PROGRAM-ID. DEMO.", "PROGRAM-ID. OTHER."),
             "FIELDS.cpy": copy}
    case = make_case(files, hosts=("DEMO", "OTHER"))
    proto = fixture(case)
    backend = RealValidationBackend(proto)
    require_compiler(backend)
    assert backend.compile(case, files, host="OTHER").status == CheckStatus.PASS
    assert backend.behavior(case, files, case.intended_behavior).status == CheckStatus.UNAVAILABLE
    demo = proto.checks["intended"][0]
    both = proto.model_copy(update={"checks": {"intended": (demo, demo.model_copy(update={"host": "OTHER", "fixture_id": "other-above"}))}})
    observed = RealValidationBackend(both).behavior(case, files, case.intended_behavior)
    require_execution(observed)
    assert observed.status == CheckStatus.PASS, observed.log


def test_capability_receipt_pins_the_protocol_and_does_not_claim_case_passes():
    case = make_case({"DEMO.cbl": SOURCE})
    backend = RealValidationBackend(fixture(case))
    receipt = backend.capability_receipt()
    assert receipt["fixture_protocol_sha256"] == backend.fixtures.sha256
    assert len(receipt["backend_identity_sha256"]) == 64
    assert receipt["case_checks_executed"] is False
    assert receipt["cics_static"].startswith("unavailable")


def test_execution_permission_denial_is_unavailable_and_cannot_pass(monkeypatch):
    from cobol_archaeologist.migration import backend as module

    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    backend = RealValidationBackend(fixture(case))
    backend.compiler = {"binary": "fixture", "binary_sha256": "0" * 64}
    monkeypatch.setattr(backend, "_compiler_pin", lambda: None)

    def blocked(*args, **kwargs):
        raise PermissionError("Execution denied by host policy")

    monkeypatch.setattr(module, "run_cobol", blocked)
    result = backend.behavior(case, files, case.intended_behavior)
    assert result.status == CheckStatus.UNAVAILABLE
    assert "Execution denied by host policy" in result.log


def test_parser_remains_independent_when_compiler_is_missing(monkeypatch):
    from cobol_archaeologist.migration import backend as module

    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    monkeypatch.setattr(module, "find_cobc", lambda: None)
    backend = RealValidationBackend(fixture(case))
    assert backend.parse(case, files).status == CheckStatus.PASS
    assert backend.compile(case, files).status == CheckStatus.UNAVAILABLE
    assert backend.behavior(case, files, case.intended_behavior).status == CheckStatus.UNAVAILABLE


def test_compiler_environment_changes_are_rejected_before_execution(monkeypatch):
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    backend = RealValidationBackend(fixture(case))
    require_compiler(backend)
    monkeypatch.setenv("COB_BACKEND_TEST_PIN", "changed-after-pin")
    result = backend.compile(case, files)
    assert result.status == CheckStatus.UNAVAILABLE
    assert "Compiler identity changed" in result.log


def test_finite_trace_and_slice_retain_source_lines_and_real_data_dependencies():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    observed = RealValidationBackend(fixture(case)).static(case, files)[1]
    assert observed.status == CheckStatus.PASS, observed.log
    analysis = json.loads(observed.log)["finite_dataflow_slices"]
    assert analysis["status"] == "pass"
    target = analysis["targets"][0]
    assert target["variable"] == "WS-RESULT"
    assert any(site["ref"]["line_start"] == 15 for site in target["trace"]["sites"])
    assert any(stmt["ref"]["line_start"] == 14 for stmt in target["slice"]["statements"])
    assert all(item["source_path"] == "DEMO.cbl" for item in target["slice"]["statements"])


@pytest.mark.parametrize("variable", ["WS-MISSING", "WS-RESULT"])
def test_finite_analysis_rejects_missing_and_ambiguous_targets(variable):
    text = SOURCE
    if variable == "WS-RESULT":
        text = text.replace("       PROCEDURE DIVISION.",
            "       01 ANOTHER-RECORD.\n       05 WS-RESULT PIC X VALUE 'N'.\n       PROCEDURE DIVISION.")
    files = {"DEMO.cbl": text}
    case = make_case(files)
    proto = fixture(case)
    changed = proto.checks["intended"][0].model_copy(update={"observe": (variable,)})
    proto = proto.model_copy(update={"checks": {"intended": (changed,)}})
    observed = RealValidationBackend(proto).static(case, files)[1]
    assert observed.status in (CheckStatus.FAIL, CheckStatus.UNAVAILABLE)
    assert "target" in observed.log


def test_static_original_main_cannot_claim_unprovided_observation_targets():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    result = RealValidationBackend(fixture(case, original_main=True)).static(case, files)[1]
    assert result.status == CheckStatus.UNAVAILABLE
    assert "observation targets" in result.log


def test_data_copybook_analysis_preserves_declaration_and_host_provenance():
    copy = "       01 WS-AMOUNT PIC 9 VALUE ZERO.\n       01 WS-RESULT PIC X VALUE 'N'.\n"
    files = {"DEMO.cbl": SOURCE.replace(copy, "           COPY FIELDS.\n"), "FIELDS.cpy": copy}
    case = make_case(files)
    result = RealValidationBackend(fixture(case)).static(case, files)[1]
    assert result.status == CheckStatus.PASS, result.log
    target = json.loads(result.log)["finite_dataflow_slices"]["targets"][0]
    declaration = next(s for s in target["trace"]["sites"] if s["statement_kind"] == "VALUE-clause")
    assert declaration["source_path"] == "FIELDS.cpy"
    assert declaration["ref"]["line_start"] == 2
    assert any(s["source_path"] == "DEMO.cbl" for s in target["slice"]["statements"])


def test_backend_identity_includes_the_actual_dataflow_and_slicer_sources(monkeypatch):
    from cobol_archaeologist.migration import backend as module

    captured = []
    original = module._digest

    def recording(value):
        captured.append(value)
        return original(value)

    monkeypatch.setattr(module, "_digest", recording)
    case = make_case({"DEMO.cbl": SOURCE})
    assert len(RealValidationBackend(fixture(case)).identity_sha256) == 64
    identity = next(v for v in captured if isinstance(v, dict) and "source_sha256" in v)
    assert {"dataflow.py", "slicer.py"} <= set(identity["source_sha256"])


def test_explicit_reviewed_targets_enable_original_main_static_analysis():
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    proto = fixture(case, original_main=True).model_copy(update={"static_targets": {"DEMO.cbl": ("WS-RESULT",)}})
    result = RealValidationBackend(proto).static(case, files)[1]
    assert result.status == CheckStatus.PASS, result.log


@pytest.mark.parametrize("targets", [{"MISSING": ("WS-RESULT",)},
                                   {"DEMO": ("WS-RESULT", "ws-result")},
                                   {"DEMO": ("WS-RESULT OF REC",)}])
def test_reviewed_static_targets_require_unique_names_and_a_frozen_host(targets):
    case = make_case({"DEMO.cbl": SOURCE})
    data = fixture(case).model_dump()
    data["static_targets"] = targets
    with pytest.raises(ValueError, match="static target"):
        FixtureProtocol.model_validate(data)


def test_procedure_copy_remains_unavailable_in_original_line_analysis():
    files = {"DEMO.cbl": SOURCE.replace("               MOVE 'Y' TO WS-RESULT", "           COPY ACTION."),
             "ACTION.cpy": "               MOVE 'Y' TO WS-RESULT\n"}
    case = make_case(files)
    result = RealValidationBackend(fixture(case)).static(case, files)[1]
    assert result.status == CheckStatus.UNAVAILABLE
    assert "procedure COPY" in result.log


def test_corrupted_analysis_line_provenance_cannot_pass(monkeypatch):
    from cobol_archaeologist.migration import backend as module

    original = module.trace_variable

    def corrupted(*args, **kwargs):
        trace = original(*args, **kwargs)
        trace.sites[0].excerpt = "fabricated source evidence"
        return trace

    monkeypatch.setattr(module, "trace_variable", corrupted)
    files = {"DEMO.cbl": SOURCE}
    case = make_case(files)
    result = RealValidationBackend(fixture(case)).static(case, files)[1]
    assert result.status == CheckStatus.FAIL
    assert "differs from original source lines" in result.log
