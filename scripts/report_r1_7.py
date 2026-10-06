"""Build provider-free T8.3/T8.4 reports from immutable evaluation evidence.

Run with ``python scripts/report_r1_7.py``. This never runs a model or changes
sealed records. Every rendered claim is copied from a JSON pointer, bound to
the report hash and the complete byte-hashed input manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cobol_archaeologist.eval.calibration import calibration
from cobol_archaeologist.eval.metrics import DRIFT_TYPES, evaluate
from cobol_archaeologist.eval.phase5_headline import (
    _balanced_accuracy_structured,
    _risk_coverage,
    paired_f1_comparison,
)
from cobol_archaeologist.eval.schemas import EvaluationRecord

ROOT = Path(__file__).resolve().parents[1]
LINEAGE = Path("data/eval/m4/gpt6-luna-repeat")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Inputs:
    def __init__(self, root: Path):
        self.root = root
        self.pins: dict[str, str] = {}

    def read(self, path: Path) -> str:
        data = (self.root / path).read_bytes()
        self.pins[path.as_posix()] = hashlib.sha256(data).hexdigest()
        return data.decode("utf-8-sig")

    def json(self, path: Path) -> Any:
        return json.loads(self.read(path))

    def records(self, path: Path) -> list[EvaluationRecord]:
        return [EvaluationRecord.model_validate_json(line)
                for line in self.read(path).splitlines() if line.strip()]


def verify_pins(root: Path, pins: dict[str, str]) -> None:
    for name, expected in pins.items():
        if sha(root / name) != expected:
            raise ValueError(f"Evidence changed: {name}")


def operation_profile(records: list[EvaluationRecord]) -> dict[str, Any]:
    """Count host trajectory observations; never infer provider telemetry."""
    cells: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"rows": 0, "answered": 0, "tool_calls": 0,
                 "successful_observations": 0, "error_observations": 0,
                 "tools": Counter(), "repeated_tool_arguments": 0,
                 "host_latency_ms_samples": [], "per_tool_latency_ms_samples": defaultdict(list)})
    for row in records:
        stratum = "interprocedural" if row.gold.code_locus.is_interprocedural else "local"
        trajectories = ([row.trajectory] if row.trajectory else [])
        if row.agent_hunts:
            trajectories = [hunt.trajectory for hunt in row.agent_hunts]
        steps = [step for trajectory in trajectories for step in trajectory.steps]
        repeated = len(steps) - len({(s.tool, json.dumps(s.arguments, sort_keys=True))
                                     for s in steps})
        for key in ("overall", stratum, row.gold.drift_type,
                    f"{row.gold.drift_type}/{stratum}"):
            cell = cells[key]
            cell["rows"] += 1
            cell["answered"] += int(not row.abstained and not row.infrastructure_error)
            cell["tool_calls"] += len(steps)
            cell["successful_observations"] += sum(s.error is None for s in steps)
            cell["error_observations"] += sum(s.error is not None for s in steps)
            cell["tools"].update(s.tool for s in steps)
            cell["repeated_tool_arguments"] += repeated
            cell["host_latency_ms_samples"].extend(s.latency_ms for s in steps)
            for step in steps:
                cell["per_tool_latency_ms_samples"][step.tool].append(step.latency_ms)
    for cell in cells.values():
        samples = sorted(cell.pop("host_latency_ms_samples"))
        cell["host_observation_latency_ms"] = {
            "samples": len(samples), "zero_values": sum(v == 0 for v in samples),
            "median": statistics.median(samples) if samples else None,
            "p95_nearest_rank": samples[math.ceil(len(samples) * .95) - 1] if samples else None,
            "maximum": max(samples) if samples else None,
            "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        }
        cell["host_per_tool_latency_ms"] = {
            tool: {"samples": len(values), "zero_values": sum(v == 0 for v in values),
                   "median": statistics.median(values), "maximum": max(values)}
            for tool, values in sorted(cell.pop("per_tool_latency_ms_samples").items())}
    return dict(sorted(cells.items()))


def pointer(document: Any, location: str) -> Any:
    for key in location.strip("/").split("/"):
        document = document[int(key)] if isinstance(document, list) else document[key]
    return document


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def build(root: Path = ROOT) -> tuple[dict, dict, Inputs]:
    inputs = Inputs(root)
    terminal = inputs.json(LINEAGE / "diagnostics/r1.6-terminal-receipt.json")
    for name, expected in terminal["file_sha256"].items():
        inputs.read(LINEAGE / name)
        if inputs.pins[(LINEAGE / name).as_posix()] != expected:
            raise ValueError(f"Terminal receipt pin mismatch: {name}")
    reconciliation = inputs.json(LINEAGE / "diagnostics/r1.6-full-terminal-reconciliation.json")
    freeze = inputs.json(LINEAGE / "run-freeze.json")
    inputs.read(Path("scripts/report_r1_7.py"))
    for name in ("phase5_headline.py", "metrics.py", "statistics.py", "calibration.py"):
        inputs.read(Path("src/cobol_archaeologist/eval") / name)
    inputs.read(Path("docs/tasks/T8.3-work-order.md"))
    inputs.read(Path("docs/tasks/T8.4-work-order.md"))
    inputs.read(Path("docs/tasks/T8.1-work-order.md"))
    by_system = {s: inputs.records(LINEAGE / "full" / s / f"{s}.jsonl")
                 for s in freeze["systems"]}
    expected = [r.instance_id for r in by_system["adaptive_agent"]]
    if len(expected) != 196 or len(set(expected)) != 196:
        raise ValueError("Full roster must contain 196 distinct rows")
    for system, rows in by_system.items():
        if [r.instance_id for r in rows] != expected:
            raise ValueError(f"Full roster does not align: {system}")
    statistics = {
        "bootstrap_resamples": freeze["decision_bootstrap_resamples"],
        "randomization_samples": freeze["decision_randomization_samples"],
        "seed": freeze["decision_statistics_seed"],
    }
    comparisons = {
        control: {locus: paired_f1_comparison(
            by_system["adaptive_agent"], by_system[control], locus=locus, **statistics)
            for locus in ("overall", "local", "interprocedural")}
        for control in ("rag_reranker", "agent")
    }
    systems = {}
    profiles = {}
    for system, rows in by_system.items():
        sealed = reconciliation["systems"][system]
        balanced = {locus: _balanced_accuracy_structured(
            rows if locus == "overall" else [r for r in rows if
                r.gold.code_locus.is_interprocedural == (locus == "interprocedural")])
            for locus in ("overall", "local", "interprocedural")}
        cal = calibration(rows)
        # No independent trajectory assessments were supplied to the terminal
        # reconciliation. Its zero faithfulness entries are missing-assessment
        # artifacts, not measured proof that every explanation is unfaithful.
        cal["per_tier_faithfulness"] = {
            k: {"n": v["n"], "faithfulness": None, "status": "not_recorded"}
            for k, v in cal["per_tier_faithfulness"].items()}
        cells = []
        for drift in DRIFT_TYPES:
            for stratum in ("local", "interprocedural"):
                cell_rows = [r for r in rows if r.gold.drift_type == drift and
                    r.gold.code_locus.is_interprocedural == (stratum == "interprocedural")]
                cells.append({"drift_type": drift, "stratum": stratum,
                              "rows": len(cell_rows),
                              "answered": sum(not r.abstained for r in cell_rows),
                              "metrics": evaluate(cell_rows),
                              "small_cell": len(cell_rows) < 20,
                              "small_cell_note": "Descriptive count flag; not a release threshold"})
        systems[system] = {**sealed, "balanced_accuracy": balanced,
                           "calibration": cal, "risk_coverage": _risk_coverage(rows),
                           "class_stratum_cells": cells,
                           "faithfulness_status": "not_recorded_no_independent_assessments",
                           "sealed_faithfulness_zeros_are_not_measured_quality": True}
        profiles[system] = operation_profile(rows)
    history = {
        "configuration_1": {"scope": "Historical evaluation; original roster, no pooling",
            "report": inputs.json(Path("data/eval/legacy/m4-initial/report.json"))},
        "configuration_2": {"scope": "Seven-row smoke only; no full evaluation",
            "manifest": inputs.json(Path("data/eval/legacy/m4-config2/smoke/agent.manifest.json")),
            "initial_five_row_smoke": inputs.json(Path("data/eval/legacy/m4-config2-smoke/agent.manifest.json")),
            "pre_amendment_smoke": inputs.json(Path("data/eval/legacy/m4-config2/smoke-pre-amendment-e6a7762/agent.manifest.json"))},
        "configuration_3": {"scope": "Fourteen-row smoke per system; no hidden evaluation",
            "systems": {s: inputs.json(Path("data/eval/legacy/m4-config3/lineage-v4/smoke") /
                         s / "progress.json") for s in freeze["systems"]}},
    }
    interrupted = inputs.json(LINEAGE / "full/interrupted-attempts.json")
    diagnostics = {}
    for directory in (LINEAGE / "diagnostics", LINEAGE / "full/rejected-finals",
                      LINEAGE / "full/rejected-tool-logs", LINEAGE / "temporal/rejected-finals",
                      LINEAGE / "temporal/interrupted-attempts"):
        if (root / directory).exists():
            paths = sorted(p for p in (root / directory).rglob("*") if p.is_file())
            diagnostics[directory.as_posix()] = [p.relative_to(root).as_posix() for p in paths]
            for p in paths:
                # Pin opaque raw bytes without trying to decode binary evidence.
                inputs.pins[p.relative_to(root).as_posix()] = sha(p)
    # Exact host logs and seals back operational claims, independently of
    # provider-authored final text. Do not include mutable live raw trees.
    for stage in ("full", "temporal"):
        for pattern in ("host-tool-log.jsonl", "staging-manifest.json", "*.execution.json"):
            for p in sorted((root / LINEAGE / stage).rglob(pattern)):
                inputs.pins[p.relative_to(root).as_posix()] = sha(p)
    missing = {k: "not_recorded" for k in (
        "provider_tokens", "provider_turns", "provider_end_to_end_latency",
        "provider_per_tool_latency", "provider_cache_reads", "provider_cache_writes",
        "metered_billing", "complete_provider_retry_count")}
    adaptive_detection = systems["adaptive_agent"]["metrics"]["overall"]["t1_detection"]
    primary = comparisons["rag_reranker"]["interprocedural"]
    quality_gates = {
        "t1_f1": adaptive_detection["f1"] >= 0.70,
        "balanced_accuracy": systems["adaptive_agent"]["balanced_accuracy"]["overall"] >= 0.65,
        "answer_rate": adaptive_detection["answer_rate"] >= 0.60,
        "answered_accuracy": adaptive_detection["answered_accuracy"] >= 0.80,
        "interprocedural_advantage": (primary["delta_f1"] >= 0.10 and
            primary["bootstrap_95_ci"][0] > 0 and primary["paired_randomization_p"] < 0.05),
        "temporal_paired_accuracy": (terminal["temporal_paired_metrics"]["pairs"] >= 20 and
            terminal["temporal_paired_metrics"]["paired_accuracy"] >= 0.70),
        "verified_evidence": all(v["unverified_emissions"] == 0 for v in systems.values()),
    }
    summaries = {
        system: {
            "host_status": v["progress_status"], "records": v["record_count"],
            "tasks": v["task_count"], "T1": v["metrics"]["overall"]["t1_detection"],
            "balanced_accuracy": v["balanced_accuracy"],
            "T2": v["metrics"]["overall"]["t2_localization"],
            "T3_macro_F1": v["metrics"]["overall"]["t3_classification"]["macro_f1"],
            "verification_tier_counts": v["calibration"]["tier_counts"],
            "brier_score": v["calibration"]["brier_score"],
            "expected_calibration_error": v["calibration"]["expected_calibration_error"],
            "faithfulness_status": v["faithfulness_status"],
            "class_stratum_counts": [{"class": c["drift_type"], "stratum": c["stratum"],
                "rows": c["rows"], "answered": c["answered"], "small_cell": c["small_cell"]}
                for c in v["class_stratum_cells"]],
        } for system, v in systems.items()
    }
    historical_summaries = {
        "configuration_1": {"scope": history["configuration_1"]["scope"],
            "historical_report_status": history["configuration_1"]["report"]["status"]},
        "configuration_2": {"scope": history["configuration_2"]["scope"],
            "validity": history["configuration_2"]["manifest"]["validity"],
            "initial_five_row_smoke_validity": history["configuration_2"]["initial_five_row_smoke"]["validity"],
            "pre_amendment_smoke_validity": history["configuration_2"]["pre_amendment_smoke"].get("validity", "not_recorded")},
        "configuration_3": {"scope": history["configuration_3"]["scope"],
            "system_statuses": {s: v["status"] for s, v in
                history["configuration_3"]["systems"].items()}},
    }
    report = {
        "schema_version": "r1.7-validity-quality-report-v1",
        "provider_calls": 0, "comparison_scope": terminal["comparison_scope"],
        "terminal_evidence": terminal, "freeze": freeze,
        "historical_configurations": history, "systems": systems,
        "historical_summaries": historical_summaries,
        "system_summaries": summaries,
        "statistics_parameters": statistics,
        "quality_gates": quality_gates,
        "quality_gate_scope": "Frozen descriptive host-quality gates; release provenance decision is separate",
        "paired_comparisons": comparisons,
        "primary_comparison": comparisons["rag_reranker"]["interprocedural"],
        "temporal": terminal["temporal_paired_metrics"],
        "signed_reference_discrepancies": terminal["signed_reference_discrepancies"],
        "host_validity_is_distinct_from_signed_reference_audit": True,
        "resource_telemetry": missing,
        "diagnostic_file_inventory": diagnostics,
        "interrupted_attempts": interrupted,
        "retry_accounting": "Preserved diagnostic files and interruption registry; not a complete provider attempt count. Counted repair substitutions remain separately zero.",
        "limitations": [
            "Repeated previously opened hidden roster; not a first-look estimate.",
            "Systems and historical rosters are not pooled.",
            "No independent faithfulness assessment file was supplied; sealed metric zeros are missing-assessment artifacts.",
            "Full-record trajectory model_id can retain the predecessor runtime default; provider identity is bound to freeze and sealed execution, not this nested field.",
            "No tool-disable capability receipt for baseline provider tasks.",
            "Signed-reference discrepancies are retained as measured; host replay VALID does not assert signed-reference equality.",
        ],
    }
    performance = {
        "schema_version": "r1.7-performance-profile-v1", "provider_calls": 0,
        "measurement_scope": "Canonical host trajectory observations; no provider-resource estimates",
        "systems": profiles, "resource_telemetry": missing,
        "retry_accounting": report["retry_accounting"],
        "interrupted_attempts": interrupted,
        "diagnostic_file_inventory": diagnostics,
        "historical_control": "agent: historical-policy GPT-6 Luna/max within the same frozen run",
        "coverage_gain": {locus: {
            "adaptive_coverage": profiles["adaptive_agent"][locus]["answered"] / profiles["adaptive_agent"][locus]["rows"],
            "historical_control_coverage": profiles["agent"][locus]["answered"] / profiles["agent"][locus]["rows"],
            "coverage_difference": (profiles["adaptive_agent"][locus]["answered"] - profiles["agent"][locus]["answered"]) / profiles["agent"][locus]["rows"],
            "additional_host_tool_calls": profiles["adaptive_agent"][locus]["tool_calls"] - profiles["agent"][locus]["tool_calls"],
            "causal_interpretation": "Descriptive system comparison, no marginal causal tool benefit",
        } for locus in ("overall", "local", "interprocedural")},
        "latency_limitation": "Trajectory latency_ms can include zero/error placeholders; no end-to-end or per-tool latency advantage is asserted.",
        "cache_limitation": "Repeated same-tool arguments are observed within rows; they do not prove provider cache hits or misses.",
        "billing_claim": "No dollar cost inferred without metered billing evidence",
    }
    temporal_records = inputs.json(LINEAGE / "temporal/adaptive_agent/replayed-records.json")
    performance["temporal_host_observations"] = operation_profile([
        EvaluationRecord.model_validate(r) for r in temporal_records["records"]])
    return report, performance, inputs


def publish(root: Path = ROOT) -> None:
    report, performance, inputs = build(root)
    out = root / "data/eval/m4"
    outputs = {"report.json": report, "performance-profile.json": performance}
    manifest = {"schema_version": "r1.7-report-evidence-manifest-v1",
                "inputs": dict(sorted(inputs.pins.items())), "outputs": {}, "claims": []}
    for name, document in outputs.items():
        write_json(out / name, document)
        manifest["outputs"][name] = sha(out / name)
    narrative = {
        "report.json": [("Comparison scope", "/comparison_scope"),
            ("Terminal host validity", "/terminal_evidence/host_status"),
            ("Full-run task count", "/terminal_evidence/sealed_full_run_tasks"),
            ("Temporal side count", "/terminal_evidence/sealed_temporal_sides"),
            ("Historical configurations", "/historical_summaries"),
            ("Primary paired comparison", "/primary_comparison"),
            ("Frozen quality gates", "/quality_gates"),
            ("Temporal paired result", "/temporal"),
            ("Signed-reference discrepancies", "/signed_reference_discrepancies"),
            ("Validity and quality limitations", "/limitations"),
            ("Retries and resumptions", "/retry_accounting"),
            ("Missing provider measurements", "/resource_telemetry")],
        "performance-profile.json": [("Measurement scope", "/measurement_scope"),
            ("Host observations by system and cell", "/systems"),
            ("Temporal host observations", "/temporal_host_observations"),
            ("Coverage gained", "/coverage_gain"),
            ("Missing provider measurements", "/resource_telemetry"),
            ("Retries and resumptions", "/retry_accounting"),
            ("Latency limitation", "/latency_limitation"),
            ("Cache limitation", "/cache_limitation"),
            ("Billing", "/billing_claim")],
    }
    for name, document in outputs.items():
        claims = list(narrative[name])
        if name == "report.json":
            claims.extend((f"{s}: validity, overall/local/interprocedural quality, calibration and fragile cells",
                           f"/system_summaries/{s}") for s in document["systems"])
        lines = ["# T8.3 validity and quality" if name == "report.json" else "# T8.4 performance profile", ""]
        for title, location in claims:
            value = pointer(document, location)
            claim_id = f"{name}:{location}"
            manifest["claims"].append({"id": claim_id, "report": name,
                "json_pointer": location, "value_sha256": hashlib.sha256(
                    json.dumps(value, sort_keys=True).encode()).hexdigest(),
                "report_sha256": manifest["outputs"][name],
                "input_manifest_required": True})
            lines.extend([f"## {title}", "", f"Evidence: `{claim_id}`", "", "```json",
                          json.dumps(value, indent=2, sort_keys=True), "```", ""])
        md = name.replace(".json", ".md")
        (out / md).write_text("\n".join(lines), encoding="utf-8", newline="\n")
        manifest["outputs"][md] = sha(out / md)
    verify_pins(root, inputs.pins)
    write_json(out / "report-evidence-manifest.json", manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    publish(parser.parse_args().root)
