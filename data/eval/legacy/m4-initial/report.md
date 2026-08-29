# M4 — NO_GO

## Headline metrics

| System | T1 F1 | Precision | Recall | Answer rate |
|---|---:|---:|---:|---:|
| Agent | 0.3665 | 0.8750 | 0.2318 | 0.2304 |
| Dense-RAG | 0.7279 | 0.7803 | 0.6821 | 0.6471 |
| Oracle-slice | 0.5714 | 0.7129 | 0.4768 | 0.4951 |

## Agent coverage, faithfulness, and calibration

- Coverage: 47/204 (0.2304).
- Aggregate faithfulness: 0.4255 (n=47).
- Per-tier faithfulness: Tier 1 0.1667 (n=6), Tier 2 0.7200 (n=25), Tier 3 0.0625 (n=16).
- Brier score: 0.1816; expected calibration error: 0.1713.
- T6: 2/20 (0.1000), exact 95% CI [0.0123, 0.3170].

## Frozen decisions

```json
{
  "overall_f1": {
    "observed": 0.3664921465968586,
    "required": 0.7,
    "met": false
  },
  "interprocedural_vs_dense": {
    "delta": -0.30303030303030304,
    "bootstrap_95_ci": [
      -0.4929396662387676,
      -0.12521739130434784
    ],
    "paired_p": 0.006349682515874206,
    "met": false
  },
  "oracle_slice_deconfounder": {
    "delta": -0.19636363636363635,
    "bootstrap_95_ci": [
      -0.4330392943063352,
      0.034782608695652195
    ],
    "loop_adds_value": false
  },
  "t6_reporting_bar": {
    "pairs": 20,
    "successes": 2,
    "paired_accuracy": 0.1,
    "exact_95_ci": [
      0.012348527170294832,
      0.3169827140190823
    ],
    "reporting_bar_evaluable": true,
    "reporting_bar_met": false
  }
}
```
