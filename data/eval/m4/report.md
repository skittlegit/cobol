# T8.3 validity and quality

## Comparison scope

Evidence: `report.json:/comparison_scope`

```json
"Repeated hidden-roster follow-up; not a first-look estimate"
```

## Terminal host validity

Evidence: `report.json:/terminal_evidence/host_status`

```json
"VALID"
```

## Full-run task count

Evidence: `report.json:/terminal_evidence/sealed_full_run_tasks`

```json
610
```

## Temporal side count

Evidence: `report.json:/terminal_evidence/sealed_temporal_sides`

```json
40
```

## Historical configurations

Evidence: `report.json:/historical_summaries`

```json
{
  "configuration_1": {
    "historical_report_status": "NO_GO",
    "scope": "Historical evaluation; original roster, no pooling"
  },
  "configuration_2": {
    "initial_five_row_smoke_validity": {
      "available_rows": 5,
      "completed_rows": 5,
      "contract_rejection_rate": 0.0,
      "contract_rejections": 0,
      "failed_gates": [
        "final non-null verified prediction rate is 0.0"
      ],
      "infrastructure_failures": 0,
      "mean_successful_tool_observations": 6.8,
      "non_null_prediction_rate": 0.0,
      "non_null_predictions": 0,
      "provider_turns": 35,
      "status": "NOT_EVALUABLE",
      "successful_tool_observations": 34
    },
    "pre_amendment_smoke_validity": {
      "available_rows": 7,
      "completed_rows": 7,
      "contract_rejection_rate": 0.0,
      "contract_rejections": 0,
      "failed_gates": [
        "final non-null verified prediction rate is 0.0"
      ],
      "infrastructure_failures": 0,
      "mean_successful_tool_observations": 10.857142857142858,
      "non_null_prediction_rate": 0.0,
      "non_null_predictions": 0,
      "provider_turns": 49,
      "status": "NOT_EVALUABLE",
      "successful_tool_observations": 76
    },
    "scope": "Seven-row smoke only; no full evaluation",
    "validity": {
      "available_rows": 7,
      "completed_rows": 7,
      "contract_rejection_rate": 0.0,
      "contract_rejections": 0,
      "failed_gates": [
        "final non-null verified prediction rate is 0.0"
      ],
      "infrastructure_failures": 0,
      "mean_successful_tool_observations": 14.142857142857142,
      "non_null_prediction_rate": 0.0,
      "non_null_predictions": 0,
      "provider_turns": 49,
      "status": "NOT_EVALUABLE",
      "successful_tool_observations": 99
    }
  },
  "configuration_3": {
    "scope": "Fourteen-row smoke per system; no hidden evaluation",
    "system_statuses": {
      "adaptive_agent": "NOT_EVALUABLE",
      "agent": "VALID",
      "oracle_slice": "VALID",
      "plain_llm": "VALID",
      "rag_dense": "VALID",
      "rag_reranker": "VALID"
    }
  }
}
```

## Primary paired comparison

Evidence: `report.json:/primary_comparison`

```json
{
  "bootstrap_95_ci": [
    0.026666666666666724,
    0.5
  ],
  "delta_f1": 0.25911949685534597,
  "effect_size": {
    "direction": "positive",
    "magnitude": 0.25911949685534597,
    "metric": "absolute_f1_difference"
  },
  "left_f1": 0.7924528301886793,
  "left_system": "adaptive_agent",
  "locus": "interprocedural",
  "paired_randomization_p": 0.0511974401279936,
  "paired_rows": 36,
  "right_f1": 0.5333333333333333,
  "right_system": "rag_reranker"
}
```

## Frozen quality gates

Evidence: `report.json:/quality_gates`

```json
{
  "answer_rate": true,
  "answered_accuracy": true,
  "balanced_accuracy": false,
  "interprocedural_advantage": false,
  "t1_f1": true,
  "temporal_paired_accuracy": false,
  "verified_evidence": true
}
```

## Temporal paired result

Evidence: `report.json:/temporal`

```json
{
  "exact_95_ci": [
    0.1539092047845408,
    0.5921885345328282
  ],
  "paired_accuracy": 0.35,
  "pairs": 20,
  "reporting_bar_evaluable": true,
  "reporting_bar_met": false,
  "successes": 7
}
```

## Signed-reference discrepancies

Evidence: `report.json:/signed_reference_discrepancies`

```json
{
  "full_cases": [
    "adaptive_agent-154",
    "adaptive_agent-173"
  ],
  "full_entries": 2,
  "temporal_cases": [
    "adaptive_agent-040"
  ],
  "temporal_entries": 2
}
```

## Validity and quality limitations

Evidence: `report.json:/limitations`

```json
[
  "Repeated previously opened hidden roster; not a first-look estimate.",
  "Systems and historical rosters are not pooled.",
  "No independent faithfulness assessment file was supplied; sealed metric zeros are missing-assessment artifacts.",
  "Full-record trajectory model_id can retain the predecessor runtime default; provider identity is bound to freeze and sealed execution, not this nested field.",
  "No tool-disable capability receipt for baseline provider tasks.",
  "Signed-reference discrepancies are retained as measured; host replay VALID does not assert signed-reference equality."
]
```

## Retries and resumptions

Evidence: `report.json:/retry_accounting`

```json
"Preserved diagnostic files and interruption registry; not a complete provider attempt count. Counted repair substitutions remain separately zero."
```

## Missing provider measurements

Evidence: `report.json:/resource_telemetry`

```json
{
  "complete_provider_retry_count": "not_recorded",
  "metered_billing": "not_recorded",
  "provider_cache_reads": "not_recorded",
  "provider_cache_writes": "not_recorded",
  "provider_end_to_end_latency": "not_recorded",
  "provider_per_tool_latency": "not_recorded",
  "provider_tokens": "not_recorded",
  "provider_turns": "not_recorded"
}
```

## agent: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/agent`

```json
{
  "T1": {
    "answer_rate": 0.5612244897959183,
    "answered_accuracy": 0.9454545454545454,
    "f1": 0.7509881422924901,
    "fn": 58,
    "fp": 5,
    "precision": 0.95,
    "recall": 0.6209150326797386,
    "tn": 9,
    "tp": 95
  },
  "T2": {
    "line": {
      "accuracy@1": 0.477124183006536,
      "accuracy@3": 0.5228758169934641,
      "overlap": 0.27712418300653596
    },
    "paragraph": {
      "accuracy@1": 0.5947712418300654,
      "accuracy@3": 0.6143790849673203
    },
    "program": {
      "accuracy@1": 0.6209150326797386,
      "accuracy@3": 0.6209150326797386
    }
  },
  "T3_macro_F1": 0.41699294860512465,
  "balanced_accuracy": {
    "interprocedural": 0.4375,
    "local": 0.43271879635516003,
    "overall": 0.415108679130567
  },
  "brier_score": 0.2834090909090909,
  "class_stratum_counts": [
    {
      "answered": 42,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 8,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 2,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 14,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 2,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 8,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 11,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 7,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 2,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 12,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 2,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.22272727272727266,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 196,
  "verification_tier_counts": {
    "2": 110
  }
}
```

## adaptive_agent: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/adaptive_agent`

```json
{
  "T1": {
    "answer_rate": 0.7091836734693877,
    "answered_accuracy": 0.8848920863309353,
    "f1": 0.7797833935018051,
    "fn": 45,
    "fp": 16,
    "precision": 0.8709677419354839,
    "recall": 0.7058823529411765,
    "tn": 15,
    "tp": 108
  },
  "T2": {
    "line": {
      "accuracy@1": 0.49673202614379086,
      "accuracy@3": 0.5228758169934641,
      "overlap": 0.45141612200435727
    },
    "paragraph": {
      "accuracy@1": 0.6274509803921569,
      "accuracy@3": 0.6470588235294118
    },
    "program": {
      "accuracy@1": 0.7058823529411765,
      "accuracy@3": 0.7058823529411765
    }
  },
  "T3_macro_F1": 0.6099435586639419,
  "balanced_accuracy": {
    "interprocedural": 0.453125,
    "local": 0.5389913117185845,
    "overall": 0.5273597811217511
  },
  "brier_score": 0.17803956834532372,
  "class_stratum_counts": [
    {
      "answered": 37,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 6,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 11,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 11,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 6,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 12,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 16,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 9,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 30,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 1,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.07877697841726616,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 196,
  "verification_tier_counts": {
    "1": 4,
    "2": 135
  }
}
```

## plain_llm: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/plain_llm`

```json
{
  "T1": {
    "answer_rate": 0.6020408163265306,
    "answered_accuracy": 0.8559322033898306,
    "f1": 0.7407407407407407,
    "fn": 53,
    "fp": 17,
    "precision": 0.8547008547008547,
    "recall": 0.6535947712418301,
    "tn": 1,
    "tp": 100
  },
  "T2": {
    "line": {
      "accuracy@1": 0.05228758169934641,
      "accuracy@3": 0.08496732026143791,
      "overlap": 0.05228758169934641
    },
    "paragraph": {
      "accuracy@1": 0.5882352941176471,
      "accuracy@3": 0.6339869281045751
    },
    "program": {
      "accuracy@1": 0.6535947712418301,
      "accuracy@3": 0.6535947712418301
    }
  },
  "T3_macro_F1": 0.34031188668807305,
  "balanced_accuracy": {
    "interprocedural": 0.1875,
    "local": 0.3764568764568765,
    "overall": 0.33842529259765924
  },
  "brier_score": 0.2878177966101695,
  "class_stratum_counts": [
    {
      "answered": 47,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 12,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 3,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 15,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 5,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 17,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 1,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 16,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 2,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.23686440677966097,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 40,
  "verification_tier_counts": {
    "1": 19,
    "2": 94,
    "3": 5
  }
}
```

## rag_dense: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/rag_dense`

```json
{
  "T1": {
    "answer_rate": 0.5408163265306123,
    "answered_accuracy": 0.8773584905660378,
    "f1": 0.7131782945736433,
    "fn": 61,
    "fp": 13,
    "precision": 0.8761904761904762,
    "recall": 0.6013071895424836,
    "tn": 1,
    "tp": 92
  },
  "T2": {
    "line": {
      "accuracy@1": 0.058823529411764705,
      "accuracy@3": 0.08496732026143791,
      "overlap": 0.043814192343604105
    },
    "paragraph": {
      "accuracy@1": 0.5751633986928104,
      "accuracy@3": 0.6013071895424836
    },
    "program": {
      "accuracy@1": 0.6013071895424836,
      "accuracy@3": 0.6013071895424836
    }
  },
  "T3_macro_F1": 0.32193129451193964,
  "balanced_accuracy": {
    "interprocedural": 0.1875,
    "local": 0.34339902521720705,
    "overall": 0.312281501747986
  },
  "brier_score": 0.28464622641509435,
  "class_stratum_counts": [
    {
      "answered": 41,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 12,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 8,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 14,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 3,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 14,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 13,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 1,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.22971698113207545,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 40,
  "verification_tier_counts": {
    "1": 25,
    "2": 76,
    "3": 5
  }
}
```

## rag_reranker: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/rag_reranker`

```json
{
  "T1": {
    "answer_rate": 0.6020408163265306,
    "answered_accuracy": 0.847457627118644,
    "f1": 0.7286245353159851,
    "fn": 55,
    "fp": 18,
    "precision": 0.8448275862068966,
    "recall": 0.6405228758169934,
    "tn": 2,
    "tp": 98
  },
  "T2": {
    "line": {
      "accuracy@1": 0.032679738562091505,
      "accuracy@3": 0.06535947712418301,
      "overlap": 0.042934951758481166
    },
    "paragraph": {
      "accuracy@1": 0.6209150326797386,
      "accuracy@3": 0.6405228758169934
    },
    "program": {
      "accuracy@1": 0.6405228758169934,
      "accuracy@3": 0.6405228758169934
    }
  },
  "T3_macro_F1": 0.34524807453950784,
  "balanced_accuracy": {
    "interprocedural": 0.1875,
    "local": 0.3810129264674719,
    "overall": 0.34351725186198506
  },
  "brier_score": 0.30103813559322035,
  "class_stratum_counts": [
    {
      "answered": 43,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 12,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 8,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 15,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 3,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 17,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 19,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 1,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.2555084745762711,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 40,
  "verification_tier_counts": {
    "1": 41,
    "2": 72,
    "3": 5
  }
}
```

## oracle_slice: validity, overall/local/interprocedural quality, calibration and fragile cells

Evidence: `report.json:/system_summaries/oracle_slice`

```json
{
  "T1": {
    "answer_rate": 0.29591836734693877,
    "answered_accuracy": 0.7931034482758621,
    "f1": 0.4360189573459715,
    "fn": 107,
    "fp": 12,
    "precision": 0.7931034482758621,
    "recall": 0.3006535947712418,
    "tn": 0,
    "tp": 46
  },
  "T2": {
    "line": {
      "accuracy@1": 0.20915032679738563,
      "accuracy@3": 0.23529411764705882,
      "overlap": 0.17391845627139746
    },
    "paragraph": {
      "accuracy@1": 0.17647058823529413,
      "accuracy@3": 0.2679738562091503
    },
    "program": {
      "accuracy@1": 0.3006535947712418,
      "accuracy@3": 0.3006535947712418
    }
  },
  "T3_macro_F1": 0.10308254963427377,
  "balanced_accuracy": {
    "interprocedural": 0.0,
    "local": 0.19008264462809918,
    "overall": 0.1503267973856209
  },
  "brier_score": 0.47443965517241377,
  "class_stratum_counts": [
    {
      "answered": 23,
      "class": "D1_stale_threshold",
      "rows": 49,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D1_stale_threshold",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 5,
      "class": "D2_missing_rule",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D2_missing_rule",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 15,
      "class": "D3_contradictory",
      "rows": 15,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D3_contradictory",
      "rows": 8,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 2,
      "class": "D4_stale_reference_data",
      "rows": 14,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D4_stale_reference_data",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 18,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D5_boundary_error",
      "rows": 0,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 1,
      "class": "D6_dead_code",
      "rows": 11,
      "small_cell": true,
      "stratum": "local"
    },
    {
      "answered": 0,
      "class": "D6_dead_code",
      "rows": 12,
      "small_cell": true,
      "stratum": "interprocedural"
    },
    {
      "answered": 11,
      "class": "D7_conformant",
      "rows": 39,
      "small_cell": false,
      "stratum": "local"
    },
    {
      "answered": 1,
      "class": "D7_conformant",
      "rows": 4,
      "small_cell": true,
      "stratum": "interprocedural"
    }
  ],
  "expected_calibration_error": 0.5094827586206896,
  "faithfulness_status": "not_recorded_no_independent_assessments",
  "host_status": "VALID",
  "records": 196,
  "tasks": 98,
  "verification_tier_counts": {
    "2": 55,
    "3": 3
  }
}
```
