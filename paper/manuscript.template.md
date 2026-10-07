# Version-conditioned regulatory conformance in legacy COBOL

**Anonymous draft; submission gates pending.**

## Abstract

We present a benchmark for detecting regulatory drift in COBOL banking code:
the conformance verdict depends on the dated regulation clause as well as the
program. The frozen test contains {{benchmark:real_curated_test_rows}} resolved
real-curated cases out of {{benchmark:annotation_sample_size}} candidates,
alongside synthetic mutations. We evaluate evidence-linked detection,
localization, classification, abstention, and version-paired judgments. The
historical M4 decision remains **NO_GO**. On the frozen M5 interprocedural
stratum, the agent's full-coverage F1 is {{m5:headline_result/agent_f1}}, versus
{{m5:headline_result/comparator_f1}} for reranked retrieval; the difference is
{{m5:headline_result/delta_f1}}. Later configuration-four measurements are
**NOT_EVALUABLE** for release provenance despite valid host execution.
These artifacts support benchmark and diagnostic claims, not agent superiority.

## Task and evidence contract

A case binds a clause version and effective date to original COBOL source
coordinates. The taxonomy distinguishes stale thresholds, missing rules,
contradictions, stale reference data, boundary errors, dead compliance code,
and conformance. The canonical class meanings are:

| Class | Definition |
|---|---|
| D1 stale parameter / threshold | A regulated literal or parameter retains an outdated value instead of the governing clause's value. |
| D2 missing rule | A required implementing check or rule is absent. |
| D3 contradictory / over-permissive | An implemented gate or path permits behavior forbidden by the governing rule, including a bypass of an otherwise intact blocker. |
| D4 stale reference data | An embedded regulator-maintained reference set contains outdated, missing, or altered entries. |
| D5 boundary / comparator error | The intended rule exists, but the wrong comparator changes treatment at its boundary. |
| D6 dead compliance code | A required check is present in the source but unreachable on the relevant execution paths. |
| D7 conformant | The scoped implementation conforms to the governing clause; this is the negative class. |

A valid explanation must support both its cited clause and
its program, paragraph, and line evidence. Interprocedural cases require
reasoning across calls or shared copybooks. Temporal pairs hold code fixed
while changing the governing clause. A version-blind answer can therefore be
incorrect even when its code description is accurate.

The system combines static analysis, regulation retrieval, program slicing,
compiler-backed behavior checks, and evidence validation. The agent can
abstain when the evidence is insufficient. Full-coverage scores retain those
abstentions; answered-only accuracy must be read together with answer rate.
The verification contract distinguishes Tier1 (executed), Tier2 (statically
confirmed), and Tier3 (entailment-only). Tier1 uses executed behavior evidence;
Tier2 confirms the relevant code fact statically; Tier3 checks entailment
without executed or statically confirmed code behavior. Faithfulness is
reported separately for each tier, including its answered-case denominator;
an aggregate does not replace those per-tier results.
Entailment scores do not establish legal validity outside the pinned clauses.

## Benchmark construction and annotation

The frozen train, development, and test sizes are
{{benchmark:split_counts/train}}, {{benchmark:split_counts/dev}}, and
{{benchmark:split_counts/test}}. The test combines
{{m5:benchmark/real_curated_rows}} real-curated rows with a synthetic remainder
within {{m5:benchmark/row_count}} total rows. Synthetic cases use mutation-generated
programs checked against compile and behavior oracles. Real-curated cases use
small authored programs and selected CardDemo programs. Base-program groups
are kept within one split. Candidate provenance, gold answers, and mutation
metadata are withheld from detector prompts. The benchmark annotation was
human-primary with a separate Claude verification pass and final adjudication;
the later migration review's authorized AI-primary workflow is a different
protocol and must not be represented as human annotation.
The human annotation population's demographics and legal qualifications are
not characterized in the frozen report; this limits population-level claims.

The regulation scope is the pinned RBI commercial-bank credit/debit-card
directions and KYC material, including predecessor clauses for temporal
comparisons. It is not a census of banking regulations. Corpus and annotation
population details, exclusion reasons, licenses, and leakage controls are
documented in [the datasheet](../DATASHEET.md) and
[annotation protocol](../ANNOTATION.md). The historical benchmark has
{{benchmark:t6_pairs}} intact temporal pairs. Later temporal measurements use
{{m4:temporal/pairs}} additive pairs and do not enlarge or pool that historical
denominator.

## Methods and results

The compared methods include plain language-model inference, dense retrieval,
reranked retrieval, oracle slicing, the agent, training-majority, prevalence
random, static-keyword, and the attacker-with-bases control. Oracle results
are upper-bound diagnostics. The complete [numerical appendix](numbers.md)
reports every frozen method, overall and local/interprocedural results,
class breakdowns, localization, faithfulness by tier, calibration,
abstention, paired effects, intervals, and significance values. Empty and
small cells remain explicitly fragile. No failing or inconclusive cell is
converted into evidence of superiority.

The M5 agent answers {{m5:metrics/agent/overall/answered}} of
{{m5:metrics/agent/overall/support}} cases, with answer rate
{{m5:metrics/agent/overall/answer_rate}}. Its answered-only accuracy is
{{m5:metrics/agent/overall/answered_accuracy}}; its full-coverage F1 is
{{m5:metrics/agent/overall/f1}}. The primary interprocedural effect interval is
[{{m5:headline_result/bootstrap_95_ci/0}},
{{m5:headline_result/bootstrap_95_ci/1}}], with paired randomization probability
{{m5:headline_result/paired_randomization_p}}. These results indicate
underperformance against the frozen strongest non-agentic model baseline.
The historical temporal score is {{m5:t6/successes}} successful pairs out of
{{m5:t6/pairs}}, with exact interval [{{m5:t6/exact_95_ci/0}},
{{m5:t6/exact_95_ci/1}}]. Its reporting bar is not evaluable at that support.

The attacker-with-bases weights were all zero in the frozen experiment. Its
result is null anti-gaming evidence, not a successful adaptive attacker or an
agent surface-floor test. The prior attacker floor remains vacated.
Supplemental ablations are reported separately and do not reopen M4 or M5.
The repeated hidden-roster follow-up retains its signed-reference
discrepancies, host-validity distinction, and failed quality bars. Later
configuration-four results are descriptive and **NOT_EVALUABLE**; the
historical M4 result remains **NO_GO** throughout this paper.

## Related work

{{related_work}}

We position the task by its conjunction of legacy source conformance and
dated regulatory evidence. The comparison establishes task differences, not
the absence of other work. We make no first, priority, or system-superiority
claim.

## Limitations, ethics, and reproducibility

The cases are dependent within base-program and source-bundle groups. Small
interprocedural cells and limited temporal support constrain inference.
Synthetic mutations and authored cases may differ from deployed banking
software. Finite compiler fixtures demonstrate behavior on specified inputs,
not full semantic equivalence or certified legal compliance. Retrieval and
entailment failures, abstentions, repeated hidden-roster exposure, mixed
reuse/rerun provenance, and unavailable resource telemetry are retained.
Model identities are reported in the generated appendix; unavailable billing
or token telemetry is never silently represented as zero expenditure.

Use is intended for research and assisted review. Incorrect conformance
claims could mislead maintainers or harm banking customers; deployment should
include qualified domain review. Public program provenance and license
notices must accompany redistribution. The project and CardDemo licensing
are described in [LICENSE](../LICENSE) and [the datasheet](../DATASHEET.md);
regulation text provenance is retained rather than asserted to be project-owned.
No customer account records or deployment credentials are included here.

Build and audit with `python scripts/build_paper.py` and
`python scripts/build_paper.py --check`. These commands perform deterministic
analysis without provider calls. The [claim map](claim-map.json) pins every
numeric table cell and inline claim to an exact JSON pointer and source-byte
hash. The final reproduction statement must bind the deployment installation,
licensed benchmark release archive, release validation, and terminal migration
report to the same source commit and benchmark manifest. This draft does not
claim that those submission gates are complete.

## Conclusion

The benchmark makes version-conditioned source conformance and evidence
quality measurable. Historical M4 remains **NO_GO**, M5 retains measured
underperformance, and configuration four remains **NOT_EVALUABLE** for
release provenance. The results justify careful evidence contracts and
preservation of negative measurements; they do not justify autonomous legal
certification or claims that the agent dominates the baselines.
