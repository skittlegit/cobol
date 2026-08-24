# T5.5A core ablation supplement

Status: **EVALUABLE**. M4 and M5 remain closed.

| Configuration | Overall F1 | Local F1 | Interproc F1 | Answer rate | Groundedness | Tokens | Tool calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| control | 0.3421 | 0.5581 | 0.0606 | 0.1972 | 0.5714 | 4121935 | 833 |
| no_slicing | 0.3200 | 0.4878 | 0.1176 | 0.1972 | 0.7857 | 4056266 | 701 |
| no_execution | 0.2286 | 0.3784 | 0.0606 | 0.1127 | 0.7500 | 4169633 | 537 |
| no_entailment | 0.3467 | 0.5366 | 0.1176 | 0.2113 | 0.4667 | 4409573 | 627 |
| no_reranking | 0.3684 | 0.5366 | 0.1714 | 0.2113 | 0.7333 | 3930398 | 689 |

## Paired effects

### no_slicing

- overall: delta F1 -0.0221; paired 95% CI [-0.1394, 0.0930], n=71.
- local: delta F1 -0.0703; paired 95% CI [-0.2471, 0.1011], n=35.
- interprocedural: delta F1 0.0570; paired 95% CI [0.0000, 0.1758], n=36.

### no_execution

- overall: delta F1 -0.1135; paired 95% CI [-0.2462, 0.0206], n=71.
- local: delta F1 -0.1798; paired 95% CI [-0.3750, 0.0000], n=35.
- interprocedural: delta F1 0.0000; paired 95% CI [-0.1667, 0.1667], n=36.

### no_entailment

- overall: delta F1 0.0046; paired 95% CI [-0.1025, 0.1105], n=71.
- local: delta F1 -0.0216; paired 95% CI [-0.1472, 0.0940], n=35.
- interprocedural: delta F1 0.0570; paired 95% CI [-0.1212, 0.2424], n=36.

### no_reranking

- overall: delta F1 0.0263; paired 95% CI [-0.0663, 0.1226], n=71.
- local: delta F1 -0.0216; paired 95% CI [-0.1479, 0.0971], n=35.
- interprocedural: delta F1 0.1108; paired 95% CI [0.0000, 0.2618], n=36.

## Coverage, faithfulness, and efficiency tradeoffs

| Configuration | Answer-rate delta | Faithfulness delta | Token delta | Tool-call delta |
|---|---:|---:|---:|---:|
| no_slicing | +0.0000 | +0.2143 | -65669 | -132 |
| no_execution | -0.0845 | +0.1786 | +47698 | -296 |
| no_entailment | +0.0141 | -0.1048 | +287638 | -206 |
| no_reranking | +0.0141 | +0.1619 | -191537 | -144 |

## Bounded component findings

- **no_execution:** Execution grounding has the strongest directional contribution on this panel: its removal produced the largest overall and local F1 decreases and the largest coverage decrease. Both paired confidence intervals include zero, so this is not a definitive component effect.
- **no_slicing:** Slicing shows a directional overall/local benefit and reduces tool use, but the interprocedural direction reverses and every paired confidence interval includes zero.
- **no_entailment:** Entailment verification appears directionally useful for faithfulness: removal increased coverage by one row while lowering faithfulness, with no supported F1 improvement.
- **no_reranking:** Reranking does not show a benefit on this supplemental panel: removal raised the point estimates for overall and interprocedural F1, but the paired intervals include zero and do not support changing the frozen architecture.

All four overall paired 95% confidence intervals include zero. Class/locus cells and the single intact temporal pair in this panel are CI-fragile.

## Versioning disposition

`NOT_INDEPENDENTLY_ABLATABLE`: Temporal identity is embedded in the benchmark-supplied RegulationClause and prompt contract. The frozen T5.4 architecture has no independent runtime version/effective-date retrieval filter whose removal leaves all other components unchanged.

The contribution of version awareness is not experimentally estimated.

This is a 71-row supplemental panel, not the frozen 196-row headline test.
