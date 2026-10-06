"""Actual WSL qualification; unavailable WSL skips real execution explicitly."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.migration.ai_review import AICaseSpec
from cobol_archaeologist.migration.backend import (
    ExecutionFixture,
    FixtureProtocol,
    RealValidationBackend,
    SourceAssertion,
)
from cobol_archaeologist.migration.contracts import FrozenSource, MigrationEvidencePin
from cobol_archaeologist.migration.validate import CheckStatus
from cobol_archaeologist.tool_types import RunInputs

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/wsl_migration_backend.py"
spec = importlib.util.spec_from_file_location("wsl_migration_backend", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
WSLValidationBackend = module.WSLValidationBackend

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

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def setup(files=None, *, original_main=False, hosts=()):
    files = files or {"DEMO.cbl": SOURCE}
    frozen = tuple(FrozenSource(path=n, sha256=sha(t)) for n,t in files.items())
    pin = MigrationEvidencePin(path="synthetic-evidence.json", sha256="1"*64)
    case = AICaseSpec(case_id="migration_wsl_qualification", instance_id="drift_000001",
        drift_type="D1_stale_threshold", stratum="local",
        validation_capability="copybook_fanout" if hosts else "batch_executable",
        primary_program="DEMO.cbl", frozen_sources=frozen,
        source_evidence=tuple(MigrationEvidencePin(path="sources/"+s.path, sha256=s.sha256) for s in frozen),
        regulation_evidence=pin, fixture_evidence=(pin,),
        allowed_source_scope=({"path":"DEMO.cbl", "line_spans":((14,14),)},),
        intended_behavior={"check_id":"intended", "description":"synthetic threshold fixture"},
        unaffected_regressions=({"check_id":"regression", "description":"synthetic low value fixture"},),
        affected_hosts=hosts, detector_input_ref="detector.json", oracle_evidence_ref="oracle.json",
        validation_protocol_sha256="2"*64, source_bundle_group="synthetic-qualification",
        duplicate_source_justification="new synthetic finite backend test; no reviewer claim")
    def fixture(host, number, expected):
        kwargs = {"run_original_main":True, "stdin":str(number)+"\n"} if original_main else {
            "initialize":(f"MOVE {number} TO WS-AMOUNT",), "perform":("CHECK-AMOUNT",), "observe":("WS-RESULT",)}
        return ExecutionFixture(fixture_id=host+str(number), host=host, expected_stdout=expected+"\n", **kwargs)
    targets = hosts or ("DEMO",)
    protocol = FixtureProtocol(case_id=case.case_id, frozen_sources=frozen,
        checks={"intended":tuple(fixture(h,8,"Y") for h in targets),
                "regression":tuple(fixture(h,2,"N") for h in targets)},
        source_assertions=tuple(SourceAssertion(assertion_id=h,host=h,paragraph="CHECK-AMOUNT",literal="WS-AMOUNT > 5") for h in targets),
        fixture_authoring_evidence_sha256=sha(SOURCE))
    return case,files,protocol

def require(backend):
    if backend.compiler is None:
        pytest.skip("Actual Ubuntu WSL compiler unavailable: "+str(backend._compiler_error))

def test_actual_wsl_source_pass_and_changed_threshold_fail():
    case,files,protocol = setup()
    backend = WSLValidationBackend(protocol)
    require(backend)
    assert backend.parse(case,files).status == CheckStatus.PASS
    assert backend.compile(case,files).status == CheckStatus.PASS
    assert all(o.status == CheckStatus.PASS for o in backend.static(case,files))
    observation = backend.behavior(case,files,case.intended_behavior)
    assert observation.status == CheckStatus.PASS, observation.log
    payload = json.loads(observation.log)["fixtures"][0]
    assert payload["expanded_original_source_sha256"] == sha(SOURCE)
    assert payload["instrumented_source_sha256"] != sha(SOURCE)
    assert payload["run_result"] == {"compiled_ok":True,"stdout":"Y\n","stderr":"","exit_code":0,"timed_out":False}
    assert backend.behavior(case,files,case.unaffected_regressions[0]).status == CheckStatus.PASS
    changed = {"DEMO.cbl":SOURCE.replace("WS-AMOUNT > 5","WS-AMOUNT > 9")}
    assert backend.behavior(case,changed,case.intended_behavior).status == CheckStatus.FAIL
    assert backend.static(case,changed)[1].status == CheckStatus.FAIL

def test_actual_original_main_source_preserved_and_real_compile_failure():
    case,files,protocol = setup(original_main=True)
    backend = WSLValidationBackend(protocol)
    require(backend)
    observation = backend.behavior(case,files,case.intended_behavior)
    assert observation.status == CheckStatus.PASS, observation.log
    assert json.loads(observation.log)["fixtures"][0]["instrumented_source_sha256"] == sha(SOURCE)
    result = backend.run_source(SOURCE.replace("STOP RUN.", "BOGUS SYNTAX."),RunInputs(stdin="8\n"))
    assert not result.compiled_ok and result.exit_code is None and result.stderr

def test_actual_copybook_fanout_requires_every_host():
    copy = "       01 WS-AMOUNT PIC 9 VALUE ZERO.\n       01 WS-RESULT PIC X VALUE 'N'.\n"
    host = SOURCE.replace(copy,"           COPY FIELDS.\n")
    case,files,protocol = setup({"DEMO.cbl":host,"OTHER.cbl":host.replace("PROGRAM-ID. DEMO.","PROGRAM-ID. OTHER."),"FIELDS.cpy":copy},hosts=("DEMO","OTHER"))
    backend = WSLValidationBackend(protocol)
    require(backend)
    assert backend.compile(case,files,host="OTHER").status == CheckStatus.PASS
    assert backend.behavior(case,files,case.intended_behavior).status == CheckStatus.PASS
    missing = protocol.model_copy(update={"checks":{"intended":protocol.checks["intended"][:1]}})
    assert WSLValidationBackend(missing).behavior(case,files,case.intended_behavior).status == CheckStatus.UNAVAILABLE

def test_actual_identity_pinning_and_missing_capability_refuse(monkeypatch):
    case,files,protocol = setup()
    backend = WSLValidationBackend(protocol)
    require(backend)
    receipt = backend.capability_receipt()
    assert receipt["execution_environment"] == "linux-wsl"
    assert receipt["compiler"]["dependencies"] and receipt["compiler"]["native_tools"]
    assert "src/cobol_archaeologist/migration/backend.py" in receipt["source_dependency_sha256"]
    assert receipt["fixture_protocol_sha256"] == protocol.sha256
    assert not receipt["case_checks_executed"] and not receipt["windows_execution_claim"]
    assert receipt["backend_identity_sha256"] != RealValidationBackend(protocol).identity_sha256
    backend.compiler = {**backend.compiler,"binary_sha256":"0"*64}
    assert backend.compile(case,files).status == CheckStatus.UNAVAILABLE
    backend = WSLValidationBackend(protocol)
    backend.compiler = None
    assert backend.behavior(case,files,case.intended_behavior).status == CheckStatus.UNAVAILABLE
    backend = WSLValidationBackend(protocol)
    monkeypatch.setattr(module,"RUNNER",module.RUNNER+"\n# tampered")
    assert backend.compile(case,files).status == CheckStatus.UNAVAILABLE

def test_hostile_fixture_identifiers_scope_and_input_paths_rejected():
    case,files,protocol = setup()
    fixture = protocol.checks["intended"][0].model_copy(update={"perform":("CHECK-AMOUNT\nSTOP RUN.",)})
    with pytest.raises(ValidationError):
        WSLValidationBackend(protocol.model_copy(update={"checks":{"intended":(fixture,)}}))
    backend = WSLValidationBackend(protocol,distro="unsupported")
    assert backend.compile(case,files).status == CheckStatus.UNAVAILABLE
    assert backend.parse(case,{**files,"../escape.cbl":SOURCE}).status == CheckStatus.UNAVAILABLE
    backend = WSLValidationBackend(protocol)
    require(backend)
    with pytest.raises(ValueError):
        backend.run_source(SOURCE,RunInputs(files={"../escape":"hostile"}))
    absent = case.model_copy(update={"validation_capability":None})
    assert backend.compile(absent,files).status == CheckStatus.UNAVAILABLE

def test_actual_execution_timeout_and_output_bounds():
    _,_,protocol = setup()
    backend = WSLValidationBackend(protocol)
    require(backend)
    infinite = SOURCE.replace("STOP RUN.","PERFORM UNTIL 1 = 2 CONTINUE END-PERFORM.")
    result = backend.run_source(infinite,RunInputs(stdin="8\n"))
    assert result.compiled_ok and result.timed_out and result.exit_code is None
    flooding = SOURCE.replace("STOP RUN.", "PERFORM 70000 TIMES DISPLAY 'A' END-PERFORM\n           STOP RUN.")
    result = backend.run_source(flooding,RunInputs(stdin="8\n"))
    assert result.compiled_ok and not result.timed_out and result.exit_code == 0
    assert result.stdout.endswith("...[truncated at 65536 bytes]")
    assert len(result.stdout.encode()) < 65600
