"""Author source-grounded migration proposals; this does not promote cases."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cobol_archaeologist.eval.materialize import materialize
from cobol_archaeologist.migration.ai_review import AICaseSpec
from cobol_archaeologist.migration.backend import (
    ExecutionFixture,
    FixtureProtocol,
    RealValidationBackend,
    SourceAssertion,
)
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/migration/ai-review"
CHECKS = (
    "intended-regulatory-behavior",
    "unaffected-outside-locus",
    "class-specific-regression",
)
BANNED = {
    "labels",
    "gold_rationale",
    "provenance",
    "mutation",
    "annotator_notes",
    "detector_scores",
    "benchmark_scores",
}


def check_visible(value):
    if isinstance(value, dict):
        if set(value) & BANNED:
            raise ValueError("hidden metadata in a proposed visible input")
        for nested in value.values():
            check_visible(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            check_visible(nested)


def immutable_bytes(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError(f"refusing to replace proposed input: {path.name}")
    path.write_bytes(payload)


def write(path: Path, value) -> dict:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    immutable_bytes(path, payload)
    return {
        "path": path.relative_to(OUT).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def fixture(name, host, paragraph, moves, observe, expected):
    return ExecutionFixture(
        fixture_id=name,
        host=host,
        initialize=tuple(moves),
        perform=(paragraph,),
        observe=tuple(observe),
        expected_stdout=expected,
    )


def main_fixture(name, host, stdin, expected):
    return ExecutionFixture(
        fixture_id=name,
        host=host,
        run_original_main=True,
        stdin=stdin,
        expected_stdout=expected,
    )


def authored_fixtures(candidate: dict, specification: dict, note_sha: str):
    name = candidate["primary_program"]
    intended, regressions, boundaries = [], [], []
    caveats = []
    if name == "REFADJ2.cbl":

        def refund(identifier, limit, amount, expected):
            return fixture(
                identifier,
                name,
                "2000-CUTOFF",
                [f"MOVE {limit} TO WS-CREDIT-LIMIT", f"MOVE {amount} TO WS-REFUND-AMT"],
                ["WS-ACTION"],
                expected,
            )

        intended = [refund("above-regulatory-cap", 1000000, 5500, "CONSENT \n")]
        regressions = [
            refund("low-limit-consent", 100000, 1500, "CONSENT \n"),
            refund("below-cutoff-adjust", 100000, 500, "ADJUST  \n"),
        ]
        boundaries = [
            refund("at-cap-adjust", 1000000, 5000, "ADJUST  \n"),
            refund("above-cap-consent", 1000000, 5001, "CONSENT \n"),
        ]
        caveats = [
            "Cutoff leaf only; consent/reversal deadlines and real transaction storage are outside this finite fixture scope."
        ]
    elif name == "KYCSY201.cbl":

        def kyc(identifier, days, expected):
            return fixture(
                identifier,
                name,
                "2000-CHECK-SLA",
                [f"MOVE {days} TO WS-DAYS-SINCE-UPD"],
                ["WS-SLA-STATUS"],
                expected,
            )

        intended = [kyc("late-eight-days", 8, "LATE    \n")]
        regressions = [kyc("new-record-preserved", 0, "NEW     \n")]
        boundaries = [
            kyc("timely-seven-days", 7, "OK      \n"),
            kyc("timely-one-day", 1, "OK      \n"),
        ]
        caveats = [
            "OK/LATE are proposed explicit status-interface conventions; reviewers must reject or revise if unsupported. A status flag does not prove a CKYCR update was transmitted."
        ]
    elif name == "TRNVAL1.cbl":
        intended = [main_fixture("block-overlimit", name, "100\n200\n", "POSTED: N\n")]
        regressions = [
            main_fixture("allow-underlimit", name, "100\n50\n", "POSTED: Y\n")
        ]
        boundaries = [
            main_fixture("allow-equal-limit", name, "100\n100\n", "POSTED: Y\n"),
            main_fixture("zero-limit-no-consent", name, "0\n50\n", "POSTED: N\n"),
        ]
        caveats = [
            "Frozen source has an orphan OR/END-IF; minimal syntax repair within the proposed scope is required. No consent input is modeled; these fixtures assume no explicit consent."
        ]
    elif name == "OVDCHK1.cbl":

        def ovd(identifier, value, expected):
            return fixture(
                identifier,
                name,
                "2000-SCREEN-OVD",
                [f"MOVE '{value}' TO WS-OVD-CODE"],
                ["WS-KYC-DECISION"],
                expected,
            )

        intended = [ovd("npr-document-admitted", "NPR", "ACCEPT\n")]
        regressions = [
            ovd("passport-preserved", "PSP", "ACCEPT\n"),
            ovd("driving-license-preserved", "DLC", "ACCEPT\n"),
        ]
        boundaries = [
            ovd("unknown-rejected", "ZZZ", "REJECT\n"),
            ovd("aadhaar-preserved", "ADH", "ACCEPT\n"),
            ovd("voter-preserved", "VTR", "ACCEPT\n"),
            ovd("nrega-preserved", "NRG", "ACCEPT\n"),
        ]
    elif name == "SCRNGATE1.cbl":

        def screening(identifier, value, expected):
            return fixture(
                identifier,
                name,
                "2000-SCREEN-SANCTIONS",
                [f"MOVE '{value}' TO WS-LIST-SOURCE"],
                ["WS-SCREEN-RESULT"],
                expected,
            )

        intended = [screening("mandated-1988-source-blocked", "S88", "BLOCK\n")]
        regressions = [screening("1267-source-preserved", "S67", "BLOCK\n")]
        boundaries = [screening("unrelated-source-clear", "ZZZ", "CLEAR\n")]
        caveats = [
            "S67/S88 are proposed registry code conventions; regulation text does not itself define these internal codes. Reviewer must assess the supplied source mapping and may reject underspecified registry provenance."
        ]
    elif name == "BOIDENT2.cbl":

        def owner(identifier, capital, profit, control, expected):
            return fixture(
                identifier,
                name,
                "2000-IDENTIFY-BO",
                [
                    f"MOVE {capital} TO WS-CAPITAL-PCT",
                    f"MOVE {profit} TO WS-PROFIT-PCT",
                    f"MOVE '{control}' TO WS-CONTROL-IND",
                ],
                ["WS-IS-BO"],
                expected,
            )

        intended = [owner("exact-capital-boundary", 10, 0, "N", "N\n")]
        regressions = [
            owner("below-threshold", 9, 9, "N", "N\n"),
            owner("above-threshold", 11, 0, "N", "Y\n"),
        ]
        boundaries = [
            owner("profit-above", 0, 11, "N", "Y\n"),
            owner("control-preserved", 0, 0, "Y", "Y\n"),
            owner("profit-exact", 0, 10, "N", "N\n"),
        ]
        caveats = [
            "Control through other means follows the existing independent source branch; ownership boundary is the targeted regulation leaf."
        ]
    elif name == "CLOSPEN3.cbl":

        def closure(identifier, calendar_days, work_days, expected):
            return fixture(
                identifier,
                name,
                "2000-PEN",
                [
                    f"MOVE {calendar_days} TO WS-CAL-DAYS-ELAPSED",
                    f"MOVE {work_days} TO WS-WORK-DAYS-ELAPSED",
                ],
                ["WS-SLA-BREACH-DAY", "WS-PENALTY-AMT"],
                expected,
            )

        intended = [
            closure("within-seven-no-breach-marker", 9, 7, "0000\n0000000.00\n")
        ]
        regressions = [closure("within-six", 8, 6, "0000\n0000000.00\n")]
        boundaries = [closure("one-day-after-window", 10, 8, "0009\n0000500.00\n")]
        caveats = [
            "At the equality boundary the original payable penalty is already zero; this proposal tests the internal breach-day sentinel. Reviewer must assess whether that is a meaningful regulatory defect. The source's calendar-day formula lacks a holiday calendar; these finite scenarios do not prove general calendar-day accrual."
        ]
    elif name in {"BATCHCT2.cbl", "CBTRN02C.cbl"}:
        caveats = [
            "No defensible concrete intended-regulatory execution fixture has been established from this source and clause. Empty checks remain unavailable, not passes; reviewers must exclude or request revised evidence."
        ]
        if name == "BATCHCT2.cbl":
            caveats.append(
                "Source implements a 500-per-day penalty control chain while the supplied clause governs minimum amount due and capitalization. Reachability alone does not establish this clause's regulated behavior."
            )
        else:
            caveats.append(
                "Source is a transaction-posting batch with indexed file dependencies. The proposed scope alone does not expose unused-card closure, notice/reply windows, CIC updates, or concrete external-state fixtures."
            )
    assertions = []
    for host in candidate.get("affected_hosts", []):
        assertions.append(
            SourceAssertion(
                assertion_id=f"division-{host.lower()}",
                host=host,
                literal="PROCEDURE DIVISION.",
            )
        )
    if not assertions:
        assertions = [
            SourceAssertion(
                assertion_id="procedure-division-preserved",
                host=name,
                literal="PROCEDURE DIVISION.",
            )
        ]
    static_targets = (
        {name: ("WS-POSTED", "WS-FAIL-REASON", "WS-LIMIT", "WS-PROJ-BAL")}
        if name == "TRNVAL1.cbl"
        else {}
    )
    protocol = FixtureProtocol(
        case_id=candidate["case_id"],
        frozen_sources=candidate["frozen_sources"],
        checks=dict(
            zip(CHECKS, [tuple(intended), tuple(regressions), tuple(boundaries)])
        ),
        source_assertions=tuple(assertions),
        fixture_authoring_evidence_sha256=note_sha,
        static_targets=static_targets,
    )
    return protocol, caveats


def prepare(root: Path = ROOT):
    if root != ROOT:
        raise ValueError("preparation uses the repository's frozen source inventory")
    terminal = json.loads(
        (root / "data/eval/m4/terminal-receipt.json").read_text(encoding="utf-8")
    )
    if terminal["status"] != "COMPLETE":
        raise ValueError("R1.7 is not terminal")
    manifest_path = root / "data/migration/candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, item in manifest["files"].items():
        if (
            hashlib.sha256((root / "data/migration" / name).read_bytes()).hexdigest()
            != item["sha256"]
        ):
            raise ValueError("candidate artifact changed")
    immutable_bytes(OUT / "candidate-manifest.json", manifest_path.read_bytes())
    rows = {
        r.instance_id: r
        for r in [
            DriftInstance.model_validate_json(line)
            for line in (root / "data/benchmark/v1/test.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
    }
    specs = {
        s["case_id"]: s
        for s in [
            json.loads(line)
            for line in (root / "data/migration/oracle-candidate-specs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
    }
    candidates = [
        json.loads(line)
        for line in (root / "data/migration/candidate-roster.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    pins = []
    for candidate in candidates:
        case_id = candidate["case_id"]
        specification = specs[case_id]
        base = OUT / "inputs" / case_id
        source = materialize(rows[candidate["instance_id"]])
        source_pins = []
        for frozen in candidate["frozen_sources"]:
            payload = source.files[frozen["path"]].encode()
            if hashlib.sha256(payload).hexdigest() != frozen["sha256"]:
                raise ValueError("materialized candidate source mismatch")
            target = base / "sources" / frozen["path"]
            immutable_bytes(target, payload)
            source_pins.append(
                {"path": target.relative_to(OUT).as_posix(), "sha256": frozen["sha256"]}
            )
        regulation = specification["oracle_prediction"]["regulation_clause"]
        regulation_pin = write(base / "regulation.json", regulation)
        note_pin = write(
            base / "fixture-authoring.json",
            {
                "case_id": case_id,
                "status": "PROPOSED_NOT_REVIEWED_NOT_EVALUATION_ELIGIBLE",
                "policy": "Source-grounded finite test proposal. No original repair or hidden metadata is supplied. Independent AI review may exclude or revise it; empty fixtures remain unavailable.",
                "regulation": regulation_pin,
                "sources": source_pins,
                "provider_calls": 0,
            },
        )
        fixtures, caveats = authored_fixtures(
            candidate, specification, note_pin["sha256"]
        )
        fixture_pin = write(base / "fixtures.json", fixtures)
        proposal_pin = write(
            base / "proposal.json",
            {
                "case_id": case_id,
                "proposed_class": candidate["drift_type"],
                "allowed_source_scope": specification["allowed_source_scope"],
                "caveats": caveats,
                "full_compliance_claim": False,
                "review_status": "PENDING",
            },
        )
        write(
            base / "detector-envelope.json",
            {
                "regulation": regulation_pin,
                "sources": source_pins,
                "finding": None,
                "detector_led_active": False,
            },
        )
        backend = RealValidationBackend(fixtures)
        validation_pin = write(
            base / "backend-capability.json", backend.capability_receipt()
        )
        body = {
            name: candidate[name]
            for name in [
                "case_id",
                "instance_id",
                "drift_type",
                "stratum",
                "validation_capability",
                "primary_program",
                "frozen_sources",
            ]
        }
        body.update(
            source_evidence=source_pins,
            regulation_evidence=regulation_pin,
            fixture_evidence=[fixture_pin, proposal_pin, validation_pin, note_pin],
            allowed_source_scope=specification["allowed_source_scope"],
            intended_behavior=specification["intended_behavior"],
            unaffected_regressions=specification["unaffected_regressions"],
            affected_hosts=specification["affected_hosts"],
            detector_input_ref=(base / "detector-envelope.json")
            .relative_to(OUT)
            .as_posix(),
            oracle_evidence_ref=(base / "proposal.json").relative_to(OUT).as_posix(),
            validation_protocol_sha256=validation_pin["sha256"],
            source_bundle_group=candidate["source_bundle_sha256"],
            duplicate_source_justification="Preselected before detector results; repeated source bundles remain dependent groups. Retain original candidate order only if all reviewers approve; future reporting discloses cases and distinct bundles and makes no independent-case interval claim.",
        )
        case = AICaseSpec.model_validate(body)
        check_visible(case.model_dump(mode="json"))
        pins.append(write(base / "case-input.json", case))
    receipt = {
        "schema_version": "r2-source-fixture-preparation-v1",
        "status": "PROPOSED_REVIEW_PENDING",
        "candidate_count": len(pins),
        "case_inputs": pins,
        "provider_calls": 0,
        "generation_authorized": False,
        "hidden_metadata_supplied": False,
    }
    write(OUT / "input-preparation.json", receipt)
    print(
        json.dumps(
            {
                "case_inputs": len(pins),
                "provider_calls": 0,
                "generation_authorized": False,
            }
        )
    )
    return receipt


if __name__ == "__main__":
    prepare()
