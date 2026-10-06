"""Author four immutable source-grounded replacement inputs; never launch reviews.

Original captures, candidate records and inputs remain historical evidence.
This prepares proposals, not approved cases or a replacement review protocol.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from cobol_archaeologist.migration.ai_review import ROLES, AICaseSpec
from cobol_archaeologist.migration.backend import FixtureProtocol

ROOT = Path(__file__).resolve().parents[1]
CASES = ("migration_075075", "migration_255807", "migration_191889", "migration_345332")
BASELINE = "data/migration/diagnostics/original-case-baseline-qualification.json"
DEPENDENCE = (
    "The common frozen candidate manifest records dependent source-bundle groups. "
    "This case retains its original group and position; counts must distinguish cases "
    "from distinct bundles, and uncertainty must account for bundle dependence. "
    "Separate AI contexts do not establish independence of model errors."
)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(out, name):
    return {"path": name, "sha256": sha((out / name).read_bytes())}


def read_pin(out, evidence):
    name = Path(evidence["path"])
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("evidence path escapes review root")
    raw = (out / name).read_bytes()
    if sha(raw) != evidence["sha256"]:
        raise ValueError(f"evidence checksum differs: {name}")
    return raw


def save(out, name, value):
    raw = value if isinstance(value, bytes) else encoded(value)
    target = out / name
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError(f"immutable revision artifact differs: {name}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    return {"path": name, "sha256": sha(raw)}


def fixture(name, host, initialize, paragraph, observe, expected):
    return {
        "fixture_id": name,
        "host": host,
        "initialize": initialize,
        "perform": [paragraph],
        "observe": observe,
        "run_original_main": False,
        "expected_stdout": expected,
        "stdin": "",
    }


def cutoff_fixture(name, limit, refund, outcome):
    return fixture(
        name,
        "REFADJ2.cbl",
        [f"MOVE {limit} TO WS-CREDIT-LIMIT", f"MOVE {refund} TO WS-REFUND-AMT"],
        "2000-CUTOFF",
        ["WS-ACTION"],
        outcome.ljust(8) + "\n",
    )


def revise(spec, fixtures, proposal):
    """Reframe only source-supported regulatory leaves and concrete finite checks."""
    case_id = spec["case_id"]
    spec["duplicate_source_justification"] = DEPENDENCE
    checks = fixtures["checks"]
    if case_id in CASES[:2]:
        spec["allowed_source_scope"] = [
            {"path": "WSCUTOFF.cpy", "line_spans": [[4, 4]]}
        ]
        spec["intended_behavior"]["description"] = (
            "Finite clause-31 cutoff decision only: WS-ACTION is CONSENT when the refund "
            "exceeds min(one percent of credit limit, Rs 5000), otherwise ADJUST; equality "
            "does not exceed the cutoff. Consent solicitation, seven-day timing, account "
            "reversal and three-working-day timing are unmodeled and unclaimed."
        )
        # Above-cap was mislabeled as unaffected despite intentionally changing.
        changed = next(
            f
            for f in checks["class-specific-regression"]
            if f["fixture_id"] == "above-cap-consent"
        )
        checks["class-specific-regression"].remove(changed)
        checks["intended-regulatory-behavior"].append(changed)
        for amount in ("4999.99", "5000.00", "5000.01"):
            outcome = "CONSENT" if amount == "5000.01" else "ADJUST"
            check = (
                "intended-regulatory-behavior"
                if outcome == "CONSENT"
                else "class-specific-regression"
            )
            checks[check].append(
                cutoff_fixture(
                    "cap-" + amount.replace(".", "-"), "1000000", amount, outcome
                )
            )
        for amount in ("999.99", "1000.00", "1000.01"):
            checks["unaffected-outside-locus"].append(
                cutoff_fixture(
                    "percent-" + amount.replace(".", "-"),
                    "100000",
                    amount,
                    "CONSENT" if amount == "1000.01" else "ADJUST",
                )
            )
        for limit in ("499999", "500000", "500001"):
            for amount in ("4999.99", "5000.00", "5000.01"):
                cutoff = min(Decimal(limit) / 100, Decimal(5000))
                outcome = "CONSENT" if Decimal(amount) > cutoff else "ADJUST"
                # These are intended finite tests; original and intended may agree.
                checks["intended-regulatory-behavior"].append(
                    cutoff_fixture(
                        f"crossover-{limit}-{amount.replace('.', '-')}",
                        limit,
                        amount,
                        outcome,
                    )
                )
        checks["class-specific-regression"].append(
            cutoff_fixture("above-old-cap", "1000000", "6000.01", "CONSENT")
        )
        spec["unaffected_regressions"][1]["description"] = (
            "Finite equality/below-cap and above-old-cap outcomes remain unchanged; "
            "5000-to-6000 outcomes that change belong to intended checks."
        )
        proposal["caveats"] = [
            "Only the shared cap constant at WSCUTOFF.cpy line 4 is authorized.",
            "One evidenced host only; no consent/reversal deadline or storage compliance claim.",
            "PIC V implied decimals are initialized numerically; action output retains PIC X(8) padding.",
        ]
    elif case_id == "migration_191889":
        spec["intended_behavior"]["description"] = (
            "Finite OVD document-category membership from KYC clause 5(xiv): NPR letter "
            "category is admitted and a space-filled code is rejected. The five existing "
            "named categories retain acceptance. Document issuer, signature and name/address "
            "qualifications are unmodeled and full KYC compliance is unclaimed."
        )
        checks["intended-regulatory-behavior"].append(
            fixture(
                "blank-document-rejected",
                "OVDCHK1.cbl",
                ["MOVE SPACES TO WS-OVD-CODE"],
                "2000-SCREEN-OVD",
                ["WS-KYC-DECISION"],
                "REJECT\n",
            )
        )
        proposal["caveats"] = [
            "Only finite document-category membership is modeled; document qualifications are absent.",
            "Blank rejection is intended behavior, not an unaffected baseline assertion.",
            "Copybook consumer evidence covers only OVDCHK1; no other fan-out is claimed.",
        ]
    else:
        spec["intended_behavior"]["description"] = (
            "Finite KYC clause-5(iv)(b) capital boundary: exactly 10 percent capital, "
            "zero profit and no control yields N; strictly greater capital yields Y. "
            "Existing strict-profit and control branches remain unchanged. No complete "
            "beneficial-owner identification or repeated-invocation equivalence is claimed."
        )
        for amount, outcome in (("9.99", "N"), ("10.01", "Y")):
            checks["unaffected-outside-locus"].append(
                fixture(
                    "capital-" + amount.replace(".", "-"),
                    "BOIDENT2.cbl",
                    [
                        f"MOVE {amount} TO WS-CAPITAL-PCT",
                        "MOVE 0 TO WS-PROFIT-PCT",
                        "MOVE 'N' TO WS-CONTROL-IND",
                    ],
                    "2000-IDENTIFY-BO",
                    ["WS-IS-BO"],
                    outcome + "\n",
                )
            )
        proposal["caveats"] = [
            "Capital-comparison boundary only; profit and control are unchanged source branches.",
            "Existing original-source executions are evidence only for original fixtures.",
            "New nearest-representable percentage fixtures require fresh real execution.",
        ]
    spec["unaffected_regressions"][0]["description"] = (
        "Only the explicitly listed finite unaffected observations are claimed; "
        "no universal preservation outside the allowed locus is established."
    )
    proposal["allowed_source_scope"] = copy.deepcopy(spec["allowed_source_scope"])
    proposal["full_compliance_claim"] = False


def verified_revised_baseline(raw, cases):
    rows = json.loads(raw)["cases"]
    by_id = {row["case_id"]: row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != set(CASES):
        raise ValueError("revised baseline must cover exactly four cases")
    for case, fixtures in cases.items():
        if by_id[case].get("frozen_sources") != fixtures["frozen_sources"]:
            raise ValueError("revised baseline does not bind original frozen sources")
        if (
            by_id[case].get("fixture_protocol_sha256")
            != FixtureProtocol.model_validate(fixtures).sha256
        ):
            # Fixture authoring hash is finalized during the proposal phase.
            raise ValueError("revised baseline does not bind exact revised fixtures")
        observed = {}
        seen_checks = set()
        for observation in by_id[case]["observations"]:
            if observation["check_id"] in seen_checks:
                raise ValueError("duplicate revised baseline check")
            seen_checks.add(observation["check_id"])
            if observation["check_id"] in fixtures["checks"]:
                for result in json.loads(observation["log"])["fixtures"]:
                    key = (observation["check_id"], result["fixture_id"])
                    if key in observed:
                        raise ValueError("duplicate revised baseline fixture")
                    observed[key] = result
        for check_id, group in fixtures["checks"].items():
            for f in group:
                result = observed.get((check_id, f["fixture_id"]))
                if result is None:
                    raise ValueError("revised baseline omits a concrete fixture")
                run = result["run_result"]
                if (
                    run["compiled_ok"] is not True
                    or run["exit_code"] != 0
                    or run["timed_out"] is not False
                    or result.get("actual_stdout")
                    != run.get("stdout", "").replace("\r\n", "\n")
                    or result.get("expected_stdout") != f["expected_stdout"]
                ):
                    raise ValueError("revised original execution unavailable")
        expected = {
            (check, f["fixture_id"])
            for check, group in fixtures["checks"].items()
            for f in group
        }
        if set(observed) != expected:
            raise ValueError("revised baseline contains unreviewed fixture IDs")
    return by_id


def verified_wsl_capabilities(root, raw, baseline_raw, baseline_rows, fixture_specs):
    receipt = json.loads(raw)
    if (
        receipt.get("schema_version") != "migration-r2-qualified-wsl-capabilities-v1"
        or receipt.get("execution_environment") != "linux-wsl"
    ):
        raise ValueError("qualified WSL capability schema differs")
    runtime_pin = receipt["backend_script"]
    read_pin(root, runtime_pin)
    if not runtime_pin["path"].startswith("scripts/") or not runtime_pin[
        "path"
    ].endswith(".py"):
        raise ValueError("WSL runtime must pin its separate repository script")
    if receipt.get("qualification_artifact"):
        read_pin(root, receipt["qualification_artifact"])
    entries = receipt["cases"]
    by_id = {c["case_id"]: c["backend"] for c in entries}
    if len(by_id) != len(entries) or set(by_id) != set(CASES):
        raise ValueError("WSL capabilities must cover exactly four cases")
    if json.loads(baseline_raw).get("execution_environment") != "linux-wsl":
        raise ValueError("WSL baseline execution identity differs")
    for case_id, capability in by_id.items():
        if (
            capability.get("schema_version") != "migration-wsl-backend-capability-v1"
            or capability.get("execution_environment") != "linux-wsl"
            or capability.get("windows_execution_claim") is not False
            or capability.get("compiler_error") is not None
            or capability.get("backend_source_sha256") != runtime_pin["sha256"]
            or capability.get("fixture_protocol_sha256")
            != FixtureProtocol.model_validate(fixture_specs[case_id]).sha256
            or baseline_rows[case_id].get("backend") != capability
        ):
            raise ValueError("WSL case capability/source/baseline binding differs")
        compiler = capability["compiler"]
        if (
            compiler.get("platform") != "linux-wsl"
            or not compiler.get("binary")
            or not compiler.get("banner")
            or not compiler.get("version")
        ):
            raise ValueError("measured WSL compiler identity missing")
        for container, key in (
            (capability, "backend_identity_sha256"),
            (capability, "wsl_binary_sha256"),
            (capability, "runner_sha256"),
            (capability, "bootstrap_sha256"),
            (compiler, "binary_sha256"),
            (compiler, "native_binary_sha256"),
        ):
            digest = container.get(key, "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("measured WSL runtime hash missing")
        for observation in baseline_rows[case_id]["observations"]:
            if observation["check_id"] in fixture_specs[case_id]["checks"]:
                log = json.loads(observation["log"])
                if (
                    log.get("backend_identity_sha256")
                    != capability["backend_identity_sha256"]
                    or log.get("fixture_protocol_sha256")
                    != capability["fixture_protocol_sha256"]
                ):
                    raise ValueError("WSL executed check compiler identity differs")
    return receipt, by_id


def prepare(
    root: Path = ROOT, *, fixtures_only=False, baseline_path=None, capability_path=None
):
    root = Path(root).resolve()
    out = root / "data/migration/ai-review"
    preparation = json.loads((out / "input-preparation.json").read_bytes())
    originals = {
        json.loads(read_pin(out, p))["case_id"]: p for p in preparation["case_inputs"]
    }
    manifest_raw = (out / "candidate-manifest.json").read_bytes()
    if manifest_raw != (root / "data/migration/candidate-manifest.json").read_bytes():
        raise ValueError("original candidate manifest differs")
    baseline_raw = (root / BASELINE).read_bytes()
    baseline_cases = {c["case_id"]: c for c in json.loads(baseline_raw)["cases"]}
    # Validate every dependency before creating any proposal.
    prepared = []
    for case_id in CASES:
        original_pin = originals[case_id]
        original = json.loads(read_pin(out, original_pin))
        AICaseSpec.model_validate(original)
        dependencies = [
            *original["source_evidence"],
            original["regulation_evidence"],
            *original["fixture_evidence"],
        ]
        for evidence in dependencies:
            read_pin(out, evidence)
        for source, evidence in zip(
            original["frozen_sources"], original["source_evidence"], strict=True
        ):
            if source["sha256"] != evidence["sha256"]:
                raise ValueError("source pins differ")
        baseline = baseline_cases[case_id]
        if baseline["case_input"] != original_pin:
            raise ValueError("baseline does not bind original input")
        finals = []
        for role in ROLES:
            evidence = pin(out, f"reviews/{case_id}/{role}/exact-final.json")
            final = json.loads(read_pin(out, evidence))
            if final["case_id"] != case_id or final["role"] != role:
                raise ValueError("original review identity differs")
            finals.append(evidence)
        prepared.append((original_pin, original, baseline, finals))
    if not fixtures_only and baseline_path is None:
        raise ValueError(
            "final revised inputs require an executed revised-fixture baseline"
        )
    revised_raw = None
    revised_rows = None
    capability_raw = None
    qualified_capabilities = None
    capability_receipt = None
    if not fixtures_only:
        path = Path(baseline_path)
        revised_raw = (path if path.is_absolute() else root / path).read_bytes()
        fixture_specs = {}
        for _, original, _, _ in prepared:
            fixtures = json.loads(
                (out / f"inputs/{original['case_id']}/fixtures.json").read_bytes()
            )
            revise(copy.deepcopy(original), fixtures, {})
            authoring_path = (
                out / f"revisions/inputs/{original['case_id']}/fixture-authoring.json"
            )
            fixtures["fixture_authoring_evidence_sha256"] = sha(
                authoring_path.read_bytes()
            )
            fixture_specs[original["case_id"]] = fixtures
        revised_rows = verified_revised_baseline(revised_raw, fixture_specs)
        baseline_body = json.loads(revised_raw)
        is_wsl = baseline_body.get("execution_environment") == "linux-wsl" or any(
            row.get("backend", {}).get("execution_environment") == "linux-wsl"
            or row.get("backend", {}).get("compiler", {}).get("platform") == "linux-wsl"
            for row in revised_rows.values()
        )
        if is_wsl and capability_path is None:
            raise ValueError("WSL execution requires qualified capability evidence")
        if capability_path is not None:
            path = Path(capability_path)
            capability_raw = (path if path.is_absolute() else root / path).read_bytes()
            capability_receipt, qualified_capabilities = verified_wsl_capabilities(
                root, capability_raw, revised_raw, revised_rows, fixture_specs
            )
    baseline_pin = save(
        out, "revisions/original-case-baseline-qualification.json", baseline_raw
    )
    revised_baseline_pin = (
        save(out, "revisions/revised-original-baseline-qualification.json", revised_raw)
        if revised_raw is not None
        else None
    )
    revised_pins = []
    qualified_capability_pin = (
        save(out, "revisions/qualified-wsl-capabilities.json", capability_raw)
        if capability_raw is not None
        else None
    )
    for original_pin, original, baseline, finals in prepared:
        case_id = original["case_id"]
        base = f"revisions/inputs/{case_id}"
        spec = copy.deepcopy(original)
        # Sources and regulation retain their exact original paths and checksums.
        # Only authored hypotheses/fixtures acquire new immutable identities.
        original_base = f"inputs/{case_id}"
        fixtures = json.loads((out / original_base / "fixtures.json").read_bytes())
        proposal = json.loads((out / original_base / "proposal.json").read_bytes())
        revise(spec, fixtures, proposal)
        observed_pin = save(
            out,
            f"{base}/original-observations.json",
            {
                "schema_version": "migration-original-baseline-observations-v1",
                "qualification": baseline_pin,
                "original_case_input": original_pin,
                "case": baseline,
                "limitations": "Exact original checks only; new fixtures have not been executed. No remediation patch exists.",
            },
        )
        authoring = {
            "case_id": case_id,
            "status": "PROPOSED_NOT_REVIEWED_NOT_EVALUATION_ELIGIBLE",
            "provider_calls": 0,
            "sources": spec["source_evidence"],
            "regulation": spec["regulation_evidence"],
            "original_execution_evidence": observed_pin,
            "policy": "Source-grounded finite revision; fresh independent review required. Original execution logs are retained exactly; new tests remain unexecuted.",
        }
        authoring_pin = save(out, f"{base}/fixture-authoring.json", authoring)
        fixtures["fixture_authoring_evidence_sha256"] = authoring_pin["sha256"]
        FixtureProtocol.model_validate(fixtures)
        fixture_pin = save(out, f"{base}/fixtures.json", fixtures)
        proposal_pin = save(out, f"{base}/proposal.json", proposal)
        capability_pin = save(
            out,
            f"{base}/backend-capability.json",
            (out / original_base / "backend-capability.json").read_bytes(),
        )
        if fixtures_only:
            revised_pins.append(fixture_pin)
            continue
        revised_observed_pin = save(
            out,
            f"{base}/revised-original-observations.json",
            {
                "schema_version": "migration-revised-original-baseline-observations-v1",
                "qualification": revised_baseline_pin,
                "original_case_input": original_pin,
                "fixtures": fixture_pin,
                "case": revised_rows[case_id],
                "limitations": "Actual unchanged-original executions only; intended post-remediation results remain proposals. No patch has been generated.",
            },
        )
        spec["fixture_evidence"] = [
            fixture_pin,
            proposal_pin,
            capability_pin,
            authoring_pin,
            observed_pin,
        ]
        spec["fixture_evidence"].append(revised_observed_pin)
        if qualified_capabilities is not None:
            measured_pin = save(
                out,
                f"{base}/qualified-capability.json",
                {
                    "schema_version": "migration-case-qualified-wsl-capability-v1",
                    "case_id": case_id,
                    "qualification": qualified_capability_pin,
                    "backend_script": capability_receipt["backend_script"],
                    "qualification_artifact": capability_receipt.get(
                        "qualification_artifact"
                    ),
                    "backend": qualified_capabilities[case_id],
                    "actual_original_execution": revised_observed_pin,
                    "limitations": "Measured WSL execution of the supplied original fixtures; historical Windows availability receipt remains separate. No patched result is established.",
                },
            )
            spec["fixture_evidence"].append(measured_pin)
        spec["oracle_evidence_ref"] = proposal_pin["path"]
        # Detector envelope remains original, bound and byte-preserved.
        spec["detector_input_ref"] = original["detector_input_ref"]
        AICaseSpec.model_validate(spec)
        revised_pin = save(out, f"{base}/case-input.json", spec)
        save(
            out,
            f"{base}/revision-history.json",
            {
                "schema_version": "migration-ai-input-revision-history-v1",
                "original_case_input": original_pin,
                "revised_case_input": revised_pin,
                "original_review_findings": finals,
                "baseline_qualification": baseline_pin,
                "candidate_manifest": pin(out, "candidate-manifest.json"),
                "fresh_review_required": True,
                "blind_packet_includes_prior_decisions": False,
                "generation_authorized": False,
            },
        )
        revised_pins.append(revised_pin)
    return save(
        out,
        "revisions/fixtures-preparation.json"
        if fixtures_only
        else "revisions/input-preparation.json",
        {
            "schema_version": "migration-ai-input-revision-preparation-v1",
            "status": "PROPOSED_REQUIRES_PROSPECTIVE_PROTOCOL_AMENDMENT_AND_FRESH_REVIEW",
            "fixture_proposals" if fixtures_only else "case_inputs": revised_pins,
            "case_ids": list(CASES),
            "provider_calls": 0,
            "candidate_count": len(CASES),
            "hidden_metadata_supplied": False,
            "generation_authorized": False,
            "candidate_manifest": pin(out, "candidate-manifest.json"),
            "baseline_qualification": baseline_pin,
            "revised_baseline_qualification": revised_baseline_pin,
            "unchanged_other_cases": "Original decisions remain retained; no replacement or invented interface/history.",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--capability", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                args.root,
                fixtures_only=args.fixtures_only,
                baseline_path=args.baseline,
                capability_path=args.capability,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
