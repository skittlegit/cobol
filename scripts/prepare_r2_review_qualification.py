"""Freeze a synthetic, non-roster review transport qualification."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cobol_archaeologist.migration.ai_review import (
    ROLES,
    AICaseSpec,
    AIReviewerIdentity,
    AIReviewProtocol,
    AIReviewRequest,
    AIReviewResponse,
    response_schema_sha256,
)
from cobol_archaeologist.migration.backend import (
    ExecutionFixture,
    FixtureProtocol,
    RealValidationBackend,
    SourceAssertion,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/migration/ai-review"
BASE = "qualification/transport-v1"


def save(name: str, value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    raw = (
        value
        if isinstance(value, bytes)
        else (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    )
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f"immutable qualification artifact differs: {name}")
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def prepare():
    existing = OUT / BASE / "request.json"
    if existing.exists():
        request = AIReviewRequest.model_validate_json(existing.read_bytes())
        frozen = AIReviewProtocol.model_validate_json(
            (OUT / request.protocol.path).read_bytes()
        )
        case = AICaseSpec.model_validate_json(
            (OUT / request.case_input.path).read_bytes()
        )
        pins = [
            request.protocol,
            request.case_input,
            request.prompt,
            frozen.authorization_evidence,
            frozen.candidate_manifest,
            *frozen.case_inputs,
            *case.source_evidence,
            case.regulation_evidence,
            *case.fixture_evidence,
        ]
        for pin in pins:
            if hashlib.sha256((OUT / pin.path).read_bytes()).hexdigest() != pin.sha256:
                raise ValueError(f"qualification input changed: {pin.path}")
        if frozen.response_schema_sha256 != response_schema_sha256():
            raise ValueError("qualification response schema changed")
        return request
    source = save(
        f"{BASE}/sources/QTHRESH.cbl",
        b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTHRESH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-VALUE PIC 9(3) VALUE ZERO.
       01 WS-FLAG PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           STOP RUN.
       2000-CHECK.
           IF WS-VALUE > 90
               MOVE 'Y' TO WS-FLAG
           ELSE
               MOVE 'N' TO WS-FLAG
           END-IF.
""",
    )
    regulation = save(
        f"{BASE}/regulation.json",
        {
            "type": "synthetic_transport_qualification_policy_not_real_regulation",
            "clause": "The flag shall be Y exactly when the numeric value is greater than 100, and N otherwise.",
        },
    )
    authoring = save(
        f"{BASE}/fixture-authoring.json",
        {
            "status": "PROPOSED_NOT_REVIEWED",
            "synthetic": True,
            "sources": [source],
            "regulation": regulation,
            "limitation": "Finite boundary tests; no banking or full regulatory compliance claim.",
        },
    )

    def fixture(name, value, expected):
        return ExecutionFixture(
            fixture_id=name,
            host="QTHRESH.cbl",
            initialize=(f"MOVE {value} TO WS-VALUE", "MOVE 'N' TO WS-FLAG"),
            perform=("2000-CHECK",),
            observe=("WS-FLAG",),
            expected_stdout=expected + "\n",
        )

    protocol = FixtureProtocol(
        case_id="migration_qualification_transport",
        frozen_sources=[{"path": "QTHRESH.cbl", "sha256": source["sha256"]}],
        checks={
            "intended": (fixture("between-old-and-policy", 95, "N"),),
            "unchanged": (fixture("above-policy", 101, "Y"), fixture("low", 0, "N")),
            "boundary": (fixture("equality", 100, "N"),),
        },
        source_assertions=(
            SourceAssertion(
                assertion_id="division",
                host="QTHRESH.cbl",
                literal="PROCEDURE DIVISION.",
            ),
        ),
        fixture_authoring_evidence_sha256=authoring["sha256"],
    )
    fixtures = save(f"{BASE}/fixtures.json", protocol)
    capability = save(
        f"{BASE}/backend-capability.json",
        RealValidationBackend(protocol).capability_receipt(),
    )
    case = AICaseSpec(
        case_id="migration_qualification_transport",
        instance_id="drift_999999",
        drift_type="D1_stale_threshold",
        stratum="local",
        validation_capability="batch_executable",
        primary_program="QTHRESH.cbl",
        frozen_sources=protocol.frozen_sources,
        source_evidence=[source],
        regulation_evidence=regulation,
        fixture_evidence=[fixtures, capability, authoring],
        allowed_source_scope=[{"path": "QTHRESH.cbl", "line_spans": [[11, 11]]}],
        intended_behavior={
            "check_id": "intended",
            "description": "95 shall produce N.",
        },
        unaffected_regressions=[
            {"check_id": "unchanged", "description": "0 remains N and 101 remains Y."},
            {"check_id": "boundary", "description": "100 shall produce N."},
        ],
        detector_input_ref=f"{BASE}/regulation.json",
        oracle_evidence_ref=f"{BASE}/fixture-authoring.json",
        validation_protocol_sha256=capability["sha256"],
        source_bundle_group="synthetic-qthresh",
        duplicate_source_justification="Unique synthetic qualification only, excluded from all official denominators.",
    )
    case_pin = save(f"{BASE}/case-input.json", case)
    authorization = save(
        f"{BASE}/authorization.json",
        {
            "user_authorization": "Authorize AI-primary migration review with independent AI verification and adjudication",
            "nonhuman": True,
            "qualification_only": True,
        },
    )
    manifest = save(
        f"{BASE}/candidate-manifest.json",
        {
            "case_ids": [case.case_id],
            "official_candidate": False,
            "generation_authorized": False,
        },
    )
    inventory = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "src").rglob("*.py"))
    }
    runtime = save(f"{BASE}/runtime-source-inventory.json", inventory)
    reviewers = [
        AIReviewerIdentity(role=r, model="gpt-6.1-sol", reasoning="medium")
        for r in ROLES
    ]
    frozen = AIReviewProtocol(
        frozen_at=datetime.now(UTC),
        authorization_evidence=authorization,
        candidate_manifest=manifest,
        runtime_source_sha256=runtime["sha256"],
        response_schema_sha256=response_schema_sha256(),
        case_inputs=[case_pin],
        reviewers=reviewers,
    )
    frozen_pin = save(f"{BASE}/review-protocol.json", frozen)
    evidence = [source, regulation, fixtures, capability, authoring]
    packet = {
        "purpose": "Synthetic review transport qualification only. No official case or patch generation.",
        "case": case.model_dump(mode="json"),
        "evidence": [
            {
                "pin": p,
                "exact_utf8_content": (OUT / p["path"]).read_text(encoding="utf-8"),
            }
            for p in evidence
        ],
        "response_schema": AIReviewResponse.model_json_schema(),
        "instructions": "Independently assess source/scope, intended and regression fixtures, capability limitations and duplicate dependence. You may include, exclude or request revision. Metadata-only compiler capability is not measured execution. Return one JSON object matching the schema, with case_id migration_qualification_transport, role ai_primary, and all exact supplied evidence pins. Do not write files, propose a patch, or assert human review or provider usage.",
    }
    prompt = save(f"{BASE}/prompt.json", packet)
    request = AIReviewRequest(
        case_id=case.case_id,
        reviewer=reviewers[0],
        protocol=frozen_pin,
        case_input=case_pin,
        prompt=prompt,
        response_schema_sha256=response_schema_sha256(),
    )
    save(f"{BASE}/request.json", request)
    launch = (
        "Review only the frozen synthetic qualification packet at "
        "C:/Users/deepa/Github/cobol/data/migration/ai-review/qualification/transport-v1/prompt.json. "
        "Read that file only using a read-only command. Do not inspect other repository files, history, "
        "other cases or reviews, and do not write files or spawn agents. Follow its instructions and "
        "return only the exact JSON response as your final answer. This is explicitly nonhuman "
        "AI-primary review; no patch generation is authorized."
    )
    save(f"{BASE}/launch.txt", launch.encode())
    return request


if __name__ == "__main__":
    request = prepare()
    print(
        json.dumps(
            {
                "status": "FROZEN_QUALIFICATION_ONLY",
                "case_id": request.case_id,
                "official_review_tasks": 0,
                "generation_tasks": 0,
            }
        )
    )
