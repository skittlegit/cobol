"""Reconcile stage migration terminals without pooling tracks or inventing usage."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from cobol_archaeologist.migration.report import (
    _required_pass_checks,
    _validate_check_roster,
)
from cobol_archaeologist.migration.validate import MigrationValidation
from scripts import seal_r2_stage_generation_session as seal
from scripts import validate_r2_stage_generation as validator

ROOT = Path(__file__).resolve().parents[1]


def summarize(records, cases, required_inventory=None):
    """Rates retain failures, abstentions and unavailable checks in their denominators."""
    if len(records) != len(cases):
        raise ValueError("pending or extra validation records")
    counts = Counter(r["validation"]["outcome"] for r in records)
    checks = defaultdict(Counter)
    classes = defaultdict(Counter)
    strata = defaultdict(Counter)
    capabilities = defaultdict(Counter)
    required_inventory = required_inventory or [
        {c["check_id"] for c in r["validation"]["checks"]} for r in records
    ]
    required = Counter(k for inventory in required_inventory for k in inventory)
    missing = Counter(
        k
        for r, inventory in zip(records, required_inventory, strict=True)
        for k in inventory
        if k not in {c["check_id"] for c in r["validation"]["checks"]}
    )
    for key in required:
        checks[key]
    for receipt, case in zip(records, cases, strict=True):
        record = receipt["validation"]
        if record["case_id"] != case["case_id"]:
            raise ValueError("validation case order differs")
        for check in record["checks"]:
            checks[check["check_id"]][check["status"]] += 1
        for grouping, key in ((classes, "drift_type"), (strata, "stratum")):
            grouping[str(case.get(key, "not_recorded"))][record["outcome"]] += 1
        capabilities[record["capability"]][record["outcome"]] += 1
    n = len(cases)
    precision = [
        r["validation"]["affected_line_precision"]
        for r in records
        if r["validation"]["affected_line_precision"] is not None
    ]
    return {
        "eligible": n,
        "evaluated": n,
        "outcomes": {k: counts[k] for k in ("pass", "fail", "abstention")},
        "patch_rate": {
            "numerator": n - counts["abstention"],
            "denominator": n,
            "value": (n - counts["abstention"]) / n if n else None,
        },
        "abstention_rate": {
            "numerator": counts["abstention"],
            "denominator": n,
            "value": counts["abstention"] / n if n else None,
        },
        "pass_rate": {
            "numerator": counts["pass"],
            "denominator": n,
            "value": counts["pass"] / n if n else None,
        },
        "checks": {
            k: {
                "denominator": n,
                "applicable_cases": required[k],
                "not_applicable_cases": n - required[k],
                "observed": dict(v),
                "not_observed": missing[k],
                "not_observed_in_all_cases": n - sum(v.values()),
                "pass_rate": v["pass"] / required[k] if required[k] else None,
            }
            for k, v in sorted(checks.items())
        },
        "by_drift_type": {k: dict(v) for k, v in sorted(classes.items())},
        "by_stratum": {k: dict(v) for k, v in sorted(strata.items())},
        "by_capability": {k: dict(v) for k, v in sorted(capabilities.items())},
        "affected_line_precision": {
            "observed": len(precision),
            "mean": sum(precision) / len(precision) if precision else None,
        },
        "changed_line_count": sum(
            r["validation"]["changed_line_count"] for r in records
        ),
        "unrelated_change_count": sum(
            r["validation"]["unrelated_change_count"] for r in records
        ),
        "provider_usage": "not_recorded",
    }


def build(root=ROOT):
    root = Path(root).resolve()
    base = root / "data/migration/generation"
    freeze_path = base / "runtime-manifest.json"
    freeze = json.loads(freeze_path.read_bytes())
    official = [e for e in freeze["requests"] if e["execution_purpose"] == "official"]
    roster_manifest = json.loads(seal.read_pin(root, freeze["roster_manifest"]))
    canonical = seal.read_pin(root, roster_manifest["canonical_roster"])
    if [c["case_id"] for c in map(json.loads, canonical.splitlines())] != [
        e["case_id"] for e in official
    ] or roster_manifest["accepted_case_ids"] != [e["case_id"] for e in official]:
        raise ValueError("canonical accepted roster order differs")
    detector_path = root / "data/eval/m4/detector-decision.json"
    detector = json.loads(
        seal.read_pin(root, roster_manifest["source_intake"]["detector_decision"])
    )
    if detector["status"] != "NOT_EVALUABLE":
        raise ValueError("frozen detector decision differs")
    if [e["run_key"] for e in official] != freeze["official_run_keys"]:
        raise ValueError("official run-key reconciliation differs")
    ledger_path, roster_path = (
        base / "generation-ledger.json",
        base / "validation-roster.json",
    )
    ledger, roster = (
        json.loads(ledger_path.read_bytes()),
        json.loads(roster_path.read_bytes()),
    )
    if (
        ledger.get("status") != "COMPLETE"
        or ledger.get("pending_keys") != []
        or ledger["generation_denominators"] != freeze["generation_denominators"]
        or [r["run_key"] for r in ledger["records"]] != freeze["official_run_keys"]
        or roster["records"] != ledger["records"]
        or roster["generation_ledger_sha256"] != seal.digest(ledger_path.read_bytes())
    ):
        raise ValueError("terminal generation ledger/validation roster differs")
    records, cases, evidence, inventories, mandatory = (
        [],
        [],
        [],
        [],
        defaultdict(Counter),
    )
    for entry in official:
        request, _, _ = seal.check_freeze(
            root=root,
            freeze_path=freeze_path,
            request_path=root / entry["request"]["path"],
            launch_path=root / entry["launch"]["path"],
        )
        capture_dir = base / "captures/official" / request.case.case_id
        capture_receipt_path = capture_dir / "seal-receipt.json"
        captured = json.loads(capture_receipt_path.read_bytes())
        row = ledger["records"][len(records)]
        if (
            row["case_id"] != request.case.case_id
            or row["proposal_kind"] != captured["proposal_kind"]
            or row["capture_receipt"]
            != seal.pin(
                root, capture_receipt_path, capture_receipt_path.read_bytes()
            ).model_dump()
        ):
            raise ValueError("generation ledger capture binding differs")
        terminal = base / "validation/official" / f"{request.case.case_id}.json"
        if not terminal.is_file():
            raise ValueError(f"pending validation: {request.case.case_id}")
        receipt = validator.validate(
            root=root,
            freeze_path=freeze_path,
            capture_dir=capture_dir,
            output_path=terminal,
        )
        if receipt["execution_purpose"] != "official":
            raise ValueError("qualification cannot enter official results")
        model = MigrationValidation.model_validate(receipt["validation"])
        if model.track != request.track or model.case_id != request.case.case_id:
            raise ValueError("terminal validation track/case differs")
        _validate_check_roster(model, request.case)
        expected = set(_required_pass_checks(request.case))
        inventories.append(expected)
        statuses = {c.check_id: c.status.value for c in model.checks}
        categories = {
            "apply": {"patch_apply"},
            "scope": {"allowed_source_scope", "affected_locations"},
            "parser": {"parser"},
            "source_binding": {"frozen_source_hash"},
            "compile": {
                k for k in expected if k == "compile" or k.endswith(":compile")
            },
            "intended": {"intended_behavior"},
            "regressions": {k for k in expected if k.startswith("regression:")},
            "static_consistency": {
                k
                for k in expected
                if k.endswith(("verifier_conflicts", "unresolved_references"))
            },
            "fanout": {k for k in expected if k.startswith("host:")},
        }
        for category, keys in categories.items():
            values = [statuses.get(k, "not_observed") for k in keys]
            state = (
                "not_applicable"
                if not keys or model.outcome.value == "abstention"
                else "fail"
                if "fail" in values
                else "unavailable"
                if "unavailable" in values
                else "not_observed"
                if any(v != "pass" for v in values)
                else "pass"
            )
            mandatory[category][state] += 1
        records.append(receipt)
        cases.append(request.case.model_dump(mode="json"))
        evidence.append(
            {
                "case_id": request.case.case_id,
                "validation": seal.pin(
                    root, terminal, terminal.read_bytes()
                ).model_dump(),
                "run_key": entry["run_key"],
            }
        )
    denominators = freeze["generation_denominators"]
    if (
        denominators["detector_led"] != 0
        or len(records) != denominators["oracle_assisted"]
        or denominators["combined"]
        != denominators["detector_led"] + denominators["oracle_assisted"]
    ):
        raise ValueError("frozen per-track denominators differ")
    report = {
        "schema_version": "migration-stage-report-v1",
        "status": "COMPLETE",
        "runtime_manifest": seal.pin(
            root, freeze_path, freeze_path.read_bytes()
        ).model_dump(),
        "roster_manifest": freeze["roster_manifest"],
        "generation_ledger": seal.pin(
            root, ledger_path, ledger_path.read_bytes()
        ).model_dump(),
        "validation_roster": seal.pin(
            root, roster_path, roster_path.read_bytes()
        ).model_dump(),
        "detector_decision_pin": seal.pin(
            root,
            detector_path,
            detector_path.read_bytes(),
        ).model_dump(),
        "evidence": evidence,
        "detector_decision": "NOT_EVALUABLE",
        "end_to_end_migration_claim_supported": False,
        "tracks": {
            "detector_led": {
                **summarize([], []),
                "status": "inactive_detector_not_evaluable",
            },
            "oracle_assisted": {
                **summarize(records, cases, inventories),
                "status": "upper_bound_only",
                "mandatory_categories": {
                    k: {
                        "denominator": len(cases),
                        "applicable_cases": len(cases) - v["not_applicable"],
                        "observed": dict(v),
                        "pass_rate": v["pass"] / len(cases) if cases else None,
                        "applicable_pass_rate": v["pass"]
                        / (len(cases) - v["not_applicable"])
                        if len(cases) - v["not_applicable"]
                        else None,
                    }
                    for k, v in sorted(mandatory.items())
                },
            },
        },
        "distinct_oracle_source_bundles": len(
            {c["source_bundle_group"] for c in cases}
        ),
        "case_source_bundles": {c["case_id"]: c["source_bundle_group"] for c in cases},
        "case_results": records,
        "qualification_excluded": freeze["qualification_disclosure"],
        "provider_usage": "not_recorded",
        "limitations": sorted({x for c in cases for x in c["reporting_limitations"]}),
    }
    raw = seal.json_bytes(report)
    seal.immutable(root / "data/migration/report.json", raw)
    lines = [
        "# Migration results",
        "",
        "Detector-led migration is inactive: configuration 4 is NOT_EVALUABLE.",
        "Oracle-assisted results are an upper bound and do not establish end-to-end detector utility.",
        "",
        "| Track | Eligible | Evaluated | Pass | Fail | Abstain |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for track, result in report["tracks"].items():
        counts = result["outcomes"]
        lines.append(
            f"| {track} | {result['eligible']} | {result['evaluated']} | {counts['pass']} | {counts['fail']} | {counts['abstention']} |"
        )
    lines.extend(
        [
            "",
            "Provider tokens, turns and latency: `not_recorded`.",
            "",
            f"Machine report SHA-256: `{hashlib.sha256(raw).hexdigest()}`.",
            "",
            "Qualification results are excluded from every official denominator.",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    oracle = report["tracks"]["oracle_assisted"]
    lines.extend(
        [
            "",
            f"The {len(cases)} oracle-assisted cases cover {report['distinct_oracle_source_bundles']} distinct source bundles.",
            "The two D1 interprocedural cutoff cases share a source bundle; their successes are dependent.",
            "No independent-case confidence interval or universal compliance claim is supported.",
            "",
            "| Validation category | Pass | Applicable | Not applicable |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, result in oracle["mandatory_categories"].items():
        lines.append(
            f"| {name} | {result['observed'].get('pass', 0)} | {result['applicable_cases']} | {result['observed'].get('not_applicable', 0)} |"
        )
    lines.extend(
        [
            "",
            "Class, stratum and capability outcomes are generated from the exact case records:",
            "",
        ]
    )
    for name in ("by_drift_type", "by_stratum", "by_capability"):
        lines.append(f"- {name}: `{json.dumps(oracle[name], sort_keys=True)}`")
    lines.extend(
        ["", "Measured successes are restricted to the authorized finite fixtures:", ""]
    )
    for record in records:
        v = record["validation"]
        lines.append(
            f"- {v['case_id']}: {v['outcome']}; {v['changed_line_count']} changed line(s), precision {v['affected_line_precision']}, unrelated changes {v['unrelated_change_count']}."
        )
    lines.extend(
        [
            "",
            "No failed patch or abstention was observed in this roster. This does not estimate reliability outside these selected cases.",
            "Compiler, intended and regression results reflect actual patched-source WSL execution; finite static consistency is not semantic equivalence.",
        ]
    )
    seal.immutable(
        root / "data/migration/report.md", ("\n".join(lines) + "\n").encode()
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.root), sort_keys=True, indent=2))
