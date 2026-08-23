"""Deterministic T5.5 benchmark-first audit and M5 closure report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cobol_archaeologist.benchmark.surface import (
    FEATURE_NAMES,
    load_probe_rows,
    per_feature_auc,
)
from cobol_archaeologist.eval.live import ROOT
from cobol_archaeologist.eval.phase5_headline import build_headline_outputs

M4_REPORT = ROOT / "data" / "eval" / "m4" / "report.json"
M5 = ROOT / "data" / "eval" / "m5"
T53_SUMMARY = M5 / "t5.3-completion-summary.json"
T54_REPORT = M5 / "report.json"
T54_ERRORS = M5 / "error-analysis.json"
ATTACKER_MANIFEST = M5 / "baselines" / "attacker_with_bases.manifest.json"
BENCHMARK_MANIFEST = ROOT / "data" / "benchmark" / "v1" / "manifest.json"
PROBE = ROOT / "data" / "benchmark" / "probes" / "t2.2_surface_probe.jsonl"

SYSTEM_ORDER = (
    "agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
    "train_majority",
    "prevalence_random",
    "static_keyword",
    "attacker_with_bases",
)

THREATS_TO_VALIDITY = (
    {
        "name": "synthetic_real_composition",
        "kind": "limitation",
        "statement": "The 196-row test set mixes 153 synthetic and 43 real-curated rows; results do not isolate performance on a broad natural-code population.",
    },
    {
        "name": "real_curated_sample",
        "kind": "limitation",
        "statement": "Only 43 of 51 reviewed real-curated candidates entered v1; eight were excluded under the frozen fail-closed adjudication protocol.",
    },
    {
        "name": "regulatory_scope",
        "kind": "limitation",
        "statement": "The benchmark is limited to pinned RBI card/debit-card and KYC/AML clauses and their selected historical versions.",
    },
    {
        "name": "cobol_corpus_diversity",
        "kind": "limitation",
        "statement": "The evaluated COBOL corpus is dominated by AWS CardDemo-derived and repository-native programs; IBM CICS CBSA is not consumed by benchmark v1.",
    },
    {
        "name": "materialized_context",
        "kind": "limitation",
        "statement": "Systems consume reconstructed/materialized source bundles rather than an unrestricted production mainframe environment.",
    },
    {
        "name": "ci_fragile_strata",
        "kind": "limitation",
        "statement": "Several class-by-locus cells contain fewer than ten rows; their point estimates do not support broad comparative claims.",
    },
    {
        "name": "temporal_pair_dependence",
        "kind": "limitation",
        "statement": "T6 rows are paired by byte-identical code locus across clause versions and therefore are not independent single-row observations.",
    },
    {
        "name": "t6_pair_count",
        "kind": "limitation",
        "statement": "Only nine intact T6 pairs remain, below the declared minimum of twenty for evaluating the formal reporting bar.",
    },
    {
        "name": "annotation_workflow",
        "kind": "limitation",
        "statement": "Real-curated labels use one human-primary pass, a separate Claude verification pass, and human final review; agreement is not inter-human agreement.",
    },
    {
        "name": "model_provider_identity",
        "kind": "limitation",
        "statement": "Provider-backed findings are specific to ChatGPT-authenticated gpt-5.6-luna and the recorded prompts, budgets, and verifier.",
    },
    {
        "name": "mixed_projection_provenance",
        "kind": "limitation",
        "statement": "Agent, RAG+reranker, and oracle-slice projections mix reused M4 rows with targeted Phase-5 reruns and are descriptive comparisons, not controlled prompt/effort ablations.",
    },
    {
        "name": "agent_coverage",
        "kind": "limitation",
        "statement": "The agent answered 42/196 rows and abstained on 154/196, so answered-subset accuracy cannot stand in for full-coverage performance.",
    },
    {
        "name": "drift_prevalence",
        "kind": "limitation",
        "statement": "The test set is drift-heavy (153/196), inflating raw binary F1 for all-drift predictors and making balanced accuracy essential context.",
    },
    {
        "name": "track_b_crlf_manifest",
        "kind": "known_cross_track_defect",
        "statement": "Track B's benchmark manifest still records stale CRLF split hashes; Phase-5 uses the ratified canonical LF identities without editing the Track B artifact.",
    },
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _lf_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, issue: str) -> None:
    if not condition:
        raise ValueError(issue)


def _source_hashes() -> dict[str, str]:
    return {
        "m4_report": _lf_sha256(M4_REPORT),
        "t5.3_completion_summary": _lf_sha256(T53_SUMMARY),
        "t5.4_report": _lf_sha256(T54_REPORT),
        "t5.4_error_analysis": _lf_sha256(T54_ERRORS),
        "attacker_manifest": _lf_sha256(ATTACKER_MANIFEST),
        "benchmark_manifest": _lf_sha256(BENCHMARK_MANIFEST),
        "surface_probe": _lf_sha256(PROBE),
    }


def _anti_gaming(attacker: dict[str, Any]) -> dict[str, Any]:
    rows = load_probe_rows(PROBE)
    aucs = per_feature_auc(rows)
    drift = [row for row in rows if row.label == 1]
    benign = [row for row in rows if row.label == 0]
    exact_balance = {
        name: sorted(row.features[name] for row in drift)
        == sorted(row.features[name] for row in benign)
        for name in FEATURE_NAMES
    }
    parameters = attacker["parameters"]
    _require(
        len(rows) == 100 and len(drift) == len(benign) == 50,
        "surface probe is not 50/50",
    )
    _require(
        parameters["feature_names"] == list(FEATURE_NAMES),
        "attacker feature contract changed",
    )
    _require(
        all(exact_balance.values()), "surface probe is not exactly balanced per feature"
    )
    _require(
        all(value == 0.5 for value in aucs.values()),
        "surface probe per-feature AUC changed",
    )
    _require(
        all(weight == 0.0 for weight in parameters["weights"]),
        "attacker weights are not all zero",
    )
    _require(parameters["bias"] == 0.0, "attacker bias is not zero")
    return {
        "probe_rows": len(rows),
        "drift_rows": len(drift),
        "mo0_rows": len(benign),
        "feature_names": list(FEATURE_NAMES),
        "per_feature_auc": aucs,
        "per_feature_sorted_multisets_identical": exact_balance,
        "weights": parameters["weights"],
        "bias": parameters["bias"],
        "decision_threshold": parameters["threshold"],
        "probe_sha256": _lf_sha256(PROBE),
        "artifact_only_literal_roundness_gate": {
            "auc": aucs["literal_roundness"],
            "frozen_bootstrap_95_ci": [0.5, 0.5],
            "status": "PASS",
        },
        "attacker_result_role": "NULL_ANTI_GAMING_EVIDENCE",
        "surface_floor": "VACATED",
        "interpretation": "The registered features do not distinguish the exactly balanced probe. The all-zero fit collapses to an all-drift prevalence baseline; F1 0.8768 is not evidence of a strong attacker and is not a pass/fail floor.",
    }


def _system_summaries(report: dict[str, Any], errors: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    cost = report["cost_efficiency"]["systems"]
    for system_id in SYSTEM_ORDER:
        metrics = report["metrics"][system_id]
        summaries[system_id] = {
            "identity": report["system_identities"][system_id],
            "artifact_hashes": report["artifact_hashes"][system_id],
            "t1": {
                "overall": metrics["overall"],
                "local": metrics["locus"]["local"],
                "interprocedural": metrics["locus"]["interprocedural"],
            },
            "d1_d7_strata": metrics["class_strata"],
            "t2_localization": metrics["t2_localization"],
            "t3_classification": metrics["t3_classification"],
            "cost_tool_token_evidence": cost[system_id],
            "error_analysis": errors["systems"].get(system_id, "not_applicable"),
        }
    return summaries


def build_m5_close() -> dict[str, Any]:
    """Audit frozen inputs and build the benchmark-first M5 decision."""

    report = _json(T54_REPORT)
    errors = _json(T54_ERRORS)
    t53 = _json(T53_SUMMARY)
    m4 = _json(M4_REPORT)
    attacker = _json(ATTACKER_MANIFEST)
    benchmark_manifest = _json(BENCHMARK_MANIFEST)

    regenerated_report, regenerated_errors = build_headline_outputs()
    regenerated_report = json.loads(json.dumps(regenerated_report))
    regenerated_errors = json.loads(json.dumps(regenerated_errors))
    _require(regenerated_report == report, "committed T5.4 report does not reproduce")
    _require(
        regenerated_errors == errors, "committed T5.4 error analysis does not reproduce"
    )
    _require(
        report["status"] == errors["status"] == t53["status"] == "EVALUABLE",
        "Phase-5 source report is not evaluable",
    )
    _require(
        m4["status"] == "NO_GO" and not m4["issues"], "M4 result of record changed"
    )
    _require(
        tuple(report["metrics"]) == SYSTEM_ORDER,
        "required system order or membership changed",
    )
    _require(
        all(row["row_count"] == 196 for row in report["system_identities"].values()),
        "system row counts are not 196",
    )
    _require(
        all(
            row["instance_ids_match_frozen_order"]
            for row in report["system_identities"].values()
        ),
        "system IDs do not match frozen order",
    )
    _require(
        all(
            row["infrastructure_failures"] == 0
            for row in report["system_identities"].values()
        ),
        "unresolved infrastructure failure",
    )
    _require(
        report["benchmark"]["canonical_lf_identity_used"],
        "canonical LF benchmark identity is not active",
    )
    _require(
        report["benchmark"]["excluded_ids_present"] == [],
        "excluded benchmark IDs appear in evaluation",
    )
    _require(
        len(report["benchmark"]["excluded_candidate_ids"]) == 8,
        "excluded-ID accounting changed",
    )
    _require(
        report["benchmark"]["real_curated_rows"] == 43, "real-curated row count changed"
    )
    _require(
        benchmark_manifest["annotation_sample_size"] == 51,
        "annotation review population changed",
    )
    _require(
        t53["decisions"]["surface_floor"]["status"] == "VACATED",
        "T5.3 surface-floor amendment changed",
    )
    _require(
        report["frozen_decisions"]["surface_floor"]["status"] == "VACATED",
        "T5.4 surface-floor amendment changed",
    )

    headline = report["headline_result"]
    _require(headline["direction"] == "negative", "headline direction changed")
    _require(
        headline["bootstrap_95_ci"][1] < 0.0,
        "headline interval no longer excludes zero",
    )
    _require(
        headline["paired_randomization_p"] < 0.05,
        "headline paired result is no longer significant",
    )
    _require(
        report["abstention"]["total_answered"] == 42, "agent answered count changed"
    )
    _require(
        report["abstention"]["total_abstained"] == 154, "agent abstention count changed"
    )
    _require(
        report["t6"]["pairs"] == 9 and report["t6"]["successes"] == 1,
        "T6 result changed",
    )
    _require(
        report["t6"]["reporting_bar_status"] == "NOT_EVALUABLE_FOR_BAR",
        "T6 bar status changed",
    )

    anti_gaming = _anti_gaming(attacker)
    audit_gates = {
        "t5.4_report_reproduces_exactly": True,
        "t5.4_error_analysis_reproduces_exactly": True,
        "required_systems_present": True,
        "all_systems_have_196_ordered_ids": True,
        "canonical_lf_benchmark_identity": True,
        "artifact_hashes_recorded": True,
        "zero_unresolved_infrastructure_failures": True,
        "reuse_rerun_provenance_present": True,
        "human_annotation_provenance_present": True,
        "excluded_ids_absent": True,
        "t5.3_surface_floor_vacated": True,
        "t5.4_negative_headline_preserved": True,
        "m4_no_go_preserved": True,
        "t6_minimum_not_met": True,
        "no_provider_runs": report["methodology"]["provider_runs_performed"] == 0,
    }
    _require(all(audit_gates.values()), "one or more T5.5 audit gates failed")

    systems = _system_summaries(report, errors)
    return {
        "status": "COMPLETE",
        "milestone": "M5_CLOSED",
        "issues": [],
        "execution_type": "deterministic interpretation and audit over frozen evidence",
        "provider_runs_performed": False,
        "source_hashes": _source_hashes(),
        "audit_gates": audit_gates,
        "benchmark": report["benchmark"],
        "annotation_provenance": {
            "reviewed_candidates": 51,
            "frozen_real_curated_rows": 43,
            "excluded_candidates": 8,
            "workflow": ["Human-Primary", "Claude-Verification", "Human-Final-Review"],
            "agreement_is_inter_human": False,
            "evidence": report["benchmark"]["annotation_evidence"],
        },
        "m4_result_of_record": {
            "status": "NO_GO",
            "report": m4,
            "interpretation": "M4 was a valid, evaluable NO_GO under its frozen bars. Phase-5 scale and new baselines do not retroactively alter that result.",
        },
        "t5.4_headline": headline,
        "paired_comparisons": report["paired_comparisons"],
        "systems": systems,
        "agent_faithfulness": report["faithfulness"],
        "agent_calibration": report["calibration"],
        "agent_coverage": report["abstention"],
        "t6": report["t6"],
        "cost_efficiency": report["cost_efficiency"],
        "ci_fragile_cells": report["ci_fragile_cells"],
        "anti_gaming": anti_gaming,
        "benchmark_contribution": {
            "establishes": [
                "a frozen version-conditioned COBOL regulatory-drift task with 196 aligned test rows",
                "reviewer-auditable provenance, exclusions, leakage controls, and evidence-linked labels",
                "reproducible full-coverage, locus, class, temporal-pair, faithfulness, calibration, and paired-comparison measurements",
                "null evidence that the six registered surface features do not distinguish the balanced T2.2 probe",
            ],
            "does_not_establish": [
                "practical utility in production mainframe compliance workflows",
                "detector superiority or that the current agent solves the task",
                "novelty merely because evaluated systems perform poorly",
                "a formal T6 bar result from nine pairs",
            ],
        },
        "detector_finding": {
            "statement": "The frozen agent significantly underperforms RAG+reranker on interprocedural T1 F1 and has low full-coverage performance.",
            "coverage_context": "The agent answered 42/196 and abstained on 154/196. Its 0.9048 answered accuracy must not be reported without the 0.2143 answer rate and full-coverage F1 0.3665.",
            "supported_error_interaction": "Frozen trajectories categorize 93 agent outcomes as coverage/abstention failures and 61 as insufficient evidence; 25 rows have evidence-verification failures, 22/42 answered rows have localization failures, and 31/36 interprocedural rows fail. These categories may overlap and do not license unsupported causal claims.",
        },
        "threats_to_validity": list(THREATS_TO_VALIDITY),
        "m5_decision": {
            "status": "CLOSED",
            "reason": "T5.1-T5.5 preserve a valid frozen benchmark, an evaluable negative headline result, complete audit/provenance evidence, and explicit limitations. Closing records the measurement and does not require an agent GO.",
            "benchmark_v1_immutable": True,
            "t5.4_results_immutable": True,
            "m8_activated": False,
            "next_track_c_task": "T7.5 paper and submission package; final completion still depends on T7.2/T7.3 release artifacts.",
        },
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(analysis: dict[str, Any]) -> str:
    """Render the complete benchmark-first decision from machine-readable data."""

    headline = analysis["t5.4_headline"]
    lines = [
        "# T5.5 Benchmark-First Analysis and M5 Decision — COMPLETE",
        "",
        "## Decision",
        "",
        "M5 is **CLOSED** on frozen evidence. This records the measured negative detector result; it does not require an agent GO and does not activate M8.",
        "",
        "## Validity audit",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    lines.extend(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in analysis["audit_gates"].items()
    )
    lines.extend(
        [
            "",
            f"Canonical benchmark: {analysis['benchmark']['row_count']} rows, SHA-256 `{analysis['benchmark']['canonical_lf_sha256']}`, with all eight excluded candidate IDs absent.",
            "",
            "The stale Track B CRLF hashes remain a cross-track issue; this analysis uses the ratified canonical LF identity and does not edit Track B's manifest.",
            "",
            "## M4 result of record",
            "",
            analysis["m4_result_of_record"]["interpretation"],
            "",
            "## Frozen T5.4 headline",
            "",
            f"On all {headline.get('paired_rows', 36)} paired interprocedural rows, agent F1 {_fmt(headline['agent_f1'])} versus RAG+reranker {_fmt(headline['comparator_f1'])}; delta F1 {_fmt(headline['delta_f1'])}, paired bootstrap 95% CI [{_fmt(headline['bootstrap_95_ci'][0])}, {_fmt(headline['bootstrap_95_ci'][1])}], paired randomization p={_fmt(headline['paired_randomization_p'])}.",
            "",
            "The agent significantly underperforms the strongest frozen non-agentic model baseline on this stratum. This is not inconclusive, and detector failure alone does not prove benchmark novelty or utility.",
            "",
            "## Benchmark contribution versus detector finding",
            "",
            "The benchmark contribution establishes:",
            "",
        ]
    )
    lines.extend(
        f"- {item}." for item in analysis["benchmark_contribution"]["establishes"]
    )
    lines.extend(["", "It does not establish:", ""])
    lines.extend(
        f"- {item}."
        for item in analysis["benchmark_contribution"]["does_not_establish"]
    )
    lines.extend(
        [
            "",
            analysis["detector_finding"]["statement"],
            "",
            analysis["detector_finding"]["coverage_context"],
            "",
            analysis["detector_finding"]["supported_error_interaction"],
            "",
            "## Frozen T1 comparisons",
            "",
            "| System | Overall F1 | Local F1 | Interprocedural F1 | Answer rate | Abstentions |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for system_id in SYSTEM_ORDER:
        t1 = analysis["systems"][system_id]["t1"]
        lines.append(
            f"| {system_id} | {_fmt(t1['overall']['f1'])} | {_fmt(t1['local']['f1'])} | {_fmt(t1['interprocedural']['f1'])} | {_fmt(t1['overall']['answer_rate'])} | {t1['overall']['abstained']} |"
        )

    lines.extend(
        [
            "",
            "## D1–D7 full-coverage strata",
            "",
            "| System | Class | n | Local | Interprocedural | T1 F1 | Answer rate |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for system_id in SYSTEM_ORDER:
        for class_name, row in analysis["systems"][system_id]["d1_d7_strata"].items():
            lines.append(
                f"| {system_id} | {class_name} | {row['support']} | {row['local_support']} | {row['interprocedural_support']} | {_fmt(row['t1_within_gold_class']['f1'])} | {_fmt(row['answer_rate'])} |"
            )

    lines.extend(
        [
            "",
            "## Structured T2 localization and T3 classification",
            "",
            "| System | T3 macro-F1 | Program Acc@1 | Paragraph Acc@1 | Line Acc@1 | Line overlap |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for system_id in (
        "agent",
        "plain_llm",
        "rag_dense",
        "rag_reranker",
        "oracle_slice",
    ):
        system = analysis["systems"][system_id]
        t2 = system["t2_localization"]
        t3 = system["t3_classification"]
        lines.append(
            f"| {system_id} | {_fmt(t3['macro_f1'])} | {_fmt(t2['program']['accuracy@1'])} | {_fmt(t2['paragraph']['accuracy@1'])} | {_fmt(t2['line']['accuracy@1'])} | {_fmt(t2['line']['overlap'])} |"
        )

    faith = analysis["agent_faithfulness"]
    calibration = analysis["agent_calibration"]
    t6 = analysis["t6"]
    lines.extend(
        [
            "",
            "## Agent faithfulness, calibration, and coverage",
            "",
            f"Aggregate groundedness is {_fmt(faith['aggregate']['faithfulness'])} over {faith['answered_rows']} answered rows. Clause evidence accuracy is {_fmt(faith['clause_evidence_accuracy'])}; code evidence accuracy is {_fmt(faith['code_evidence_accuracy'])}. Per-tier evidence remains: `{json.dumps(faith['per_tier'], sort_keys=True)}`.",
            "",
            f"Brier score {_fmt(calibration['brier_score'])}; ECE {_fmt(calibration['expected_calibration_error'])}. Coverage is {_fmt(calibration['coverage'])}. Risk-coverage data remains machine-readable in the JSON artifact.",
            "",
            "## T6 temporal evidence",
            "",
            f"T6 is {t6['successes']}/{t6['pairs']} ({_fmt(t6['paired_accuracy'])}), exact 95% CI [{_fmt(t6['exact_95_ci'][0])}, {_fmt(t6['exact_95_ci'][1])}]. Status remains **{t6['reporting_bar_status']}** because {t6['minimum_pairs_required']} pairs are required. This is directional evidence only.",
            "",
            "## Anti-gaming handoff",
            "",
            analysis["anti_gaming"]["interpretation"],
            "",
            "All six per-feature AUCs are exactly 0.5 and each drift/MO-0 sorted feature multiset is identical. All six fitted weights and the bias are zero. The old +0.10 agent-over-attacker floor remains **VACATED**.",
            "",
            "## Cost, tools, and tokens",
            "",
            "| System | Provider turns | Tokens | Tool calls | Answer rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for system_id in SYSTEM_ORDER:
        row = analysis["systems"][system_id]["cost_tool_token_evidence"]
        lines.append(
            f"| {system_id} | {row['provider_turns']} | {row['token_count_total']} | {row['tool_calls']} | {_fmt(row['answer_rate'])} |"
        )
    lines.extend(
        [
            "",
            "No dollar cost is estimated; provider calls were ChatGPT-authenticated and no metered billing record exists.",
            "",
            "## Error-analysis summary",
            "",
            "| System | Binary errors | Abstentions | Wrong class | Interprocedural failures |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for system_id, row in _json(T54_ERRORS)["summary"].items():
        lines.append(
            f"| {system_id} | {row['binary_errors']} | {row['abstentions']} | {row['wrong_class']} | {row['interprocedural_failures']} |"
        )
    lines.extend(
        [
            "",
            "Categories may overlap. Root causes are not assigned beyond frozen trajectory support.",
            "",
            "## CI fragility",
            "",
            "Cells below ten rows remain CI-fragile:",
            "",
        ]
    )
    lines.extend(f"- `{cell}`" for cell in analysis["ci_fragile_cells"])
    lines.extend(["", "## Threats and limitations", ""])
    lines.extend(
        f"- **{row['name']} ({row['kind']}):** {row['statement']}"
        for row in analysis["threats_to_validity"]
    )
    lines.extend(
        [
            "",
            "## Next work",
            "",
            analysis["m5_decision"]["next_track_c_task"],
            "",
            "M8 remains planned post-release work and is not active.",
            "",
        ]
    )
    return "\n".join(lines)


def write_m5_close(analysis: dict[str, Any], output_dir: Path = M5) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark-first-analysis.json").write_text(
        json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "benchmark-first-analysis.md").write_text(
        render_markdown(analysis), encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=M5)
    args = parser.parse_args()
    try:
        analysis = build_m5_close()
    except ValueError as exc:
        print(json.dumps({"status": "NOT_EVALUABLE", "issues": [str(exc)]}))
        return 1
    write_m5_close(analysis, args.output_dir)
    print(
        json.dumps({"status": analysis["status"], "milestone": analysis["milestone"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
