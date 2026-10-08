# Version-conditioned regulatory drift detection in legacy COBOL

## Abstract

Banking systems written in COBOL encode regulations as constants, branches,
reference tables, and batch-step flags. When a regulation changes and the code
does not, the program drifts. We present a benchmark and a detector for this
problem. Each case binds a COBOL program to one regulation clause pinned to a
version and effective date, and asks for one of seven verdicts: six drift
classes and conformance. The detector is a tool-using model (gpt-6-luna) that
must verify every finding against executed, static, or entailment evidence
before it counts; an unverified finding becomes an abstention. Gates were
fixed before any test run. We report two official evaluations.

The first (E1) was a first look at unseen test data. It failed only the
temporal gate (15/22 pairs), and those failures traced to benchmark programs
that omitted part of their clause.

The second (E2) came after fixing what E1 exposed, using dev and new data
only:

- corrected temporal and batch-chain programs;
- a fair response shape for the baseline;
- a new 95-row held-out test split, whose 72 cross-program rows include
  conformant cases and bundles larger than the baseline's retrieval window.

On that split the detector reaches class F1 0.927, balanced accuracy 0.909,
and 20/22 temporal pairs. Every emitted finding is verified. Its
cross-program F1 is 0.911 against 0.721 for a retrieval-reranking baseline: a
margin of +0.190 (95% CI 0.058–0.340, p < 0.001) against the pre-registered
+0.10. The decision is GO. Because E2 follows an inspection of E1, we report
it as a post-hoc evaluation on fresh data.

## Task

A case is a COBOL program bundle (main program, copybooks, and called or
chained programs), one regulation clause with its version, effective date, and
typed current value, and a gold label. The detector sees the source and the
clause, never the label, the mutation that produced the row, or the gold
rationale.

| Class | Meaning |
| --- | --- |
| D1 stale threshold | A regulated value (limit, rate, deadline, unit, or basis) holds a superseded value. |
| D2 missing rule | A required check or outcome is absent from the reachable code. |
| D3 contradiction | Reachable code permits what the clause forbids or withholds what it requires, including a neutralised gate. |
| D4 stale reference data | An embedded reference set lacks or keeps entries the regulation changed. |
| D5 boundary error | The intended rule exists but the comparator is wrong at the edge. |
| D6 dead compliance code | The compliance logic exists but can never execute. |
| D7 conformant | The code satisfies the clause. |

A finding names the class, the program, paragraph, and original source lines,
and a rationale. Every line number refers to the original file; the
preprocessor that masks `EXEC` blocks and expands `COPY REPLACING` preserves
line counts.

Regulations: the RBI (Commercial Banks – Credit Cards and Debit Cards:
Issuance and Conduct) Directions, 2025, the KYC clauses its paragraph 90
incorporates, and the RBI KYC Directions, 2025. Older versions come from the
repealed 2022 credit-card Master Direction and the 2016 KYC Master Direction.
Source PDFs are pinned by SHA-256.

## Benchmark

| Split | Rows | Cross-program | Hand-curated |
| --- | --- | --- | --- |
| train | 307 | 7 | 0 |
| dev | 509 | 114 | 109 |
| test | 116 | 45 | 0 |
| temporal | 22 pairs (44 rows) | 6 pairs | 44 |

**Synthetic rows.** Mutation operators apply drift edits (stale values,
removed checks, inverted or neutralised gates, trimmed reference lists,
comparator changes, disabled guard flags) to AWS CardDemo programs and to
purpose-written seed programs, with cross-program variants through shared
copybooks, called modules, and batch-step chains. Benign edits (label and
comment rewording) are mixed in as conformant rows so that edit artifacts do
not reveal the label. Each row is stored as its base program plus the exact
unified diff the build produced, so the program a system sees is the one that
was compiled, behaviour-checked under GnuCOBOL 3.2.0, and judged.

**Fresh test split.** A test split that has been inspected moves into dev.
The E2 test split comes from 84 seed programs that appear in no other split.

Most are realistic-size cross-program hosts in four families:

- copybook refund cutoffs;
- nested over-limit gates;
- late-payment penalty chains;
- bureau-reporting chains.

Their bundles run 250–370 lines, larger than the baseline's 200-line
retrieval window. Every such host also yields a conformant row, so the
cross-program stratum measures false alarms as well as recall. The rest are
local hosts.

Each host was compiled and checked on every leg of its clause (307 behaviour
checks) before mutation. A plausibility judge from a different model family
than the detector (Claude) reviewed every candidate against a fixed rubric.
No base program, row identifier, or detector-visible source is shared with
train or dev.

**Temporal pairs.** Each pair is one program judged against two versions of a
KYC beneficial-owner clause. The program keeps the threshold of the 2016
Master Direction (as consolidated 2018-07-12), so it is conformant under that
version and a stale threshold under the 2025 Directions. Targets: company
controlling ownership (more than 25 to more than 10 percent; 10 pairs), trust
beneficiaries (15% or more to 10 percent or more; 7 pairs), and partnership
interests (more than 15 to more than 10 percent; 5 pairs). Each change was
verified in the pinned primary texts, and each program implements every leg of
its clause (79 behaviour checks). A pair counts only if both sides are
correct.

## Detector

One Codex task per case runs gpt-6-luna with the materialised source and the
clause. The model gathers evidence only through a bridge command that exposes
bounded analysis tools: paragraph and program views, callers and callees,
variable traces and slices across programs, copybook resolution, data layouts,
grep, and compile-and-run of snippets under GnuCOBOL (24 calls per case). Any
other shell command invalidates the case. The host rebuilds the tool log from
the Codex event stream and hashes each cited observation itself, so the
evidence ledger cannot cite what the model did not observe.

Before a finding is emitted it must pass two checks. The verifier assigns a
tier: executed (a GnuCOBOL probe reproduces the claimed behaviour), static (an
AST, dataflow, slice, or reachability fact matches the claim), or
entailment-only (a DeBERTa NLI model judges that the cited clause entails the
claim). Tier-3-only findings are not emitted. A class guard then checks the
evidence each class requires, for example an exact source literal for D1 and
D6 or a canonical missing member for D4. A finding that fails either check
becomes an abstention.

**Development.** The detector was tuned only on train and dev. Three rounds
on a fixed 30-row dev subset at `high` effort raised its balanced accuracy on
that subset from 0.62 to 0.78, and three full dev runs raised dev balanced
accuracy from 0.757 to 0.876, through class-arbitration rules (for example: a
gate compared against zero is a contradiction, not a stale value; doing more
than the clause requires is not drift; judge the obligation the program
implements). The method version is a hash of every file that can change an
answer and is part of every result's key.

**Baseline.** `rag_reranker` retrieves clause context with hybrid search and a
reranker and asks the same model for a verdict over a bounded code context,
five cases per call, without tools. Its findings pass through the same
verifier; the detector's class guards do not apply to it.

## Evaluation protocol

The gates were fixed in `eval/report.py` before the test split was run.

| Gate | Requirement |
| --- | --- |
| Class F1 | >= 0.70 |
| Balanced accuracy | >= 0.65 |
| Answer rate | >= 0.60 |
| Answered accuracy | >= 0.80 |
| Cross-program F1 advantage over the baseline | >= +0.10, bootstrap CI above 0, paired randomisation p < 0.05 |
| Temporal paired accuracy | >= 0.70 on >= 20 pairs |
| Unverified findings emitted | 0 |

The decision is GO when every gate passes, NO_GO otherwise, and NOT_EVALUABLE
when required rows are missing or failed on infrastructure. The test split
and temporal pairs are run once for the frozen detector, at effort `max`.

## Results

**E2 decision: GO.** All seven gates pass on the held-out test split.

| Gate | E2 (test) | Required | Pass |
| --- | --- | --- | --- |
| Class F1 | 0.927 | >= 0.70 | yes |
| Balanced accuracy | 0.909 | >= 0.65 | yes |
| Answer rate | 1.000 | >= 0.60 | yes |
| Answered accuracy | 0.916 | >= 0.80 | yes |
| Cross-program F1 advantage over the baseline | +0.190 (CI 0.058–0.340, p < 0.001, n = 72) | >= +0.10 | yes |
| Temporal paired accuracy | 20/22 = 0.909 | >= 0.70 | yes |
| Unverified findings | 0 | 0 | yes |

Per-class recall on the test split:

| Class | Recall |
| --- | --- |
| D1 | 16/16 |
| D2 | 3/4 |
| D3 | 12/12 |
| D4 | 2/2 |
| D5 | 5/5 |
| D6 | 12/12 |
| D7 | 36/44 |

The detector never abstained.

**Errors.** The main weakness is false alarms on conformant code: 8 of 44
conformant rows were called D3.

- Four come from bureau-chain hosts, where a run-control module turns the
  bureau step on for one region only. The detector reads this as a regional
  carve-out the clause does not allow; for these programs that reading is
  arguable.
- Two point at a real edge of the programs' arithmetic: a rounded
  one-percent cutoff.
- In the temporal set, two old-side programs were called D2 and D3. Every
  new side was right.

**How we got here.** The first official run (E1), on an earlier fresh split,
passed every gate except temporal paired accuracy (15/22).

- Reading the failures showed that several of our temporal programs omitted
  part of their clause, so their conformant labels were wrong.
- E1 also showed low recall on dead compliance code (D6, 4/22). That too
  traced to the benchmark: the batch-chain hosts linked their two steps only
  implicitly.

We fixed both in dev and wrote new test programs. One intermediate split was
too easy for the margin gate to be informative: every cross-program row was
a drift case, and every bundle fit inside the baseline's window. We also gave
the baseline the same response shape the detector gets for conformant
answers; without it, the baseline's correct conformant answers had been
rejected. The detector itself did not need tuning for E2. Every test split
that had been inspected is now in dev.

## Migration

For a verified finding, a patch can be generated and validated. Validation
applies the patch, checks its edit scope, compiles every host program, checks
source assertions, confirms the intended fixtures fail before the patch, and
runs every fixture after it. On four cases with oracle findings (two
cross-program D1, one D4, one D5) all four patches passed. This is finite
fixture-level evidence, not proof of program equivalence.

## Related work

**COBOL and mainframes.** MainframeBench evaluates mainframe knowledge,
question answering, and COBOL summarisation
([XMainframe](https://arxiv.org/abs/2408.04660)). COBOLEval evaluates generated
COBOL with GnuCOBOL ([COBOLEval](https://github.com/zorse-project/COBOLEval)).

**Regulation and source code.** GDPR-Bench-Android evaluates GDPR compliance
detection in Android apps ([GDPR-Bench-Android](https://arxiv.org/abs/2511.00619)).
Compliance-to-Code maps Chinese financial regulatory clauses to executable
logic ([Compliance-to-Code](https://arxiv.org/abs/2505.19804)). Other work
evaluates regulatory compliance of tool invocation rather than of source code
([Logic-Guided Synthesis](https://arxiv.org/abs/2601.08196)).

**Temporal legal reasoning.** Statutory question answering under
post-cutoff staleness ([Asking For An Old Friend](https://arxiv.org/abs/2605.23497v2))
and temporal reasoning over Indian financial regulation
([IndiaFinBench](https://arxiv.org/abs/2604.19298v2)).

**Industrial modernisation.** AWS Transform documents mainframe analysis and
COBOL-to-Java refactoring
([documentation](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-mainframe.html)).

The task here is the conjunction of legacy source conformance and dated
regulatory evidence. We make no claim of priority.

## Limitations

- Synthetic rows and purpose-written seed programs may differ from deployed
  banking software; the fresh test bases come from a few template families,
  so rows within a family share structure.
- The test split has no hand-curated rows; the annotated rows are in dev.
- Every temporal pair has the same direction (old side conformant, new side
  D1), and all come from beneficial-owner thresholds.
- Twice a post-run inspection found benchmark programs that omitted part of
  their clause; both sets are corrected in dev. E2 is post hoc with respect
  to E1: its test data is fresh, but the benchmark and baseline fixes
  followed an inspection of E1's failures.
- Some E2 conformant hosts carry scaffolding (a region gate) and rounding that
  the detector reads as contradictions; a future split should remove both.
- The plausibility judge (Claude) also wrote the fresh seed programs. It is
  independent of the system under test, not of the benchmark's authorship.
- Compiler probes show behaviour on specified inputs, not semantic
  equivalence or legal compliance. Findings are aids for qualified review.
- Rows within a base-program group are dependent; small cells are fragile.

## Reproducibility

```bash
pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q
python -m cobol_archaeologist.eval.runner detector --split test
python -m cobol_archaeologist.eval.runner detector --split temporal
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.report --split test
```

Corpora (AWS CardDemo, Apache-2.0; IBM CICS CBSA, EPL-2.0) are fetched at
pinned commits and not redistributed. Results are written only by
`eval/runner.py` and scored only by `eval/report.py`.
