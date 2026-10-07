"""Reconcile stage migration terminals without pooling tracks or inventing usage."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts import seal_r2_stage_generation_session as seal
from scripts import validate_r2_stage_generation as validator

ROOT = Path(__file__).resolve().parents[1]


def summarize(records, cases):
    """Rates retain failures, abstentions and unavailable checks in their denominators."""
    if len(records) != len(cases):
        raise ValueError("pending or extra validation records")
    counts = Counter(r["validation"]["outcome"] for r in records)
    checks = defaultdict(Counter)
    classes = defaultdict(Counter)
    strata = defaultdict(Counter)
    capabilities = defaultdict(Counter)
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
                "observed": dict(v),
                "not_observed": n - sum(v.values()),
                "pass_rate": v["pass"] / n if n else None,
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
    if [e["run_key"] for e in official] != freeze["official_run_keys"]:
        raise ValueError("official run-key reconciliation differs")
    records, cases, evidence = [], [], []
    for entry in official:
        request, _, _ = seal.check_freeze(
            root=root,
            freeze_path=freeze_path,
            request_path=root / entry["request"]["path"],
            launch_path=root / entry["launch"]["path"],
        )
        capture_dir = base / "captures/official" / request.case.case_id
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
    ):
        raise ValueError("frozen per-track denominators differ")
    report = {
        "schema_version": "migration-stage-report-v1",
        "status": "COMPLETE",
        "runtime_manifest": seal.pin(
            root, freeze_path, freeze_path.read_bytes()
        ).model_dump(),
        "roster_manifest": freeze["roster_manifest"],
        "evidence": evidence,
        "detector_decision": "NOT_EVALUABLE",
        "end_to_end_migration_claim_supported": False,
        "tracks": {
            "detector_led": {
                **summarize([], []),
                "status": "inactive_detector_not_evaluable",
            },
            "oracle_assisted": {
                **summarize(records, cases),
                "status": "upper_bound_only",
            },
        },
        "distinct_oracle_source_bundles": len(
            {c["source_bundle_group"] for c in cases}
        ),
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
    seal.immutable(
        root / "data/migration/report.md", ("\n".join(lines) + "\n").encode()
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.root), sort_keys=True, indent=2))
