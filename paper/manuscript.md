# Version-conditioned regulatory conformance in legacy COBOL

**Anonymous submission package; audited artifact bindings recorded.**

## Abstract

We present a benchmark for detecting regulatory drift in COBOL banking code:
the conformance verdict depends on the dated regulation clause as well as the
program. The frozen test contains 43 ([c9594a463d8b688c7](claim-map.json)) resolved
real-curated cases out of 51 ([c565cb3f05cc85d90](claim-map.json)) candidates,
alongside synthetic mutations. We evaluate evidence-linked detection,
localization, classification, abstention, and version-paired judgments. The
historical M4 decision remains **NO_GO**. On the frozen M5 interprocedural
stratum, the agent's full-coverage F1 is 0.4 ([cd5a4e05b68128ba4](claim-map.json)), versus
0.6938775510204082 ([c4bb0e16cf1a544e0](claim-map.json)) for reranked retrieval; the difference is
-0.29387755102040813 ([c114b55680168d4b7](claim-map.json)). Later configuration-four measurements are
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
307 ([ca9a69b7e2f875f1f](claim-map.json)), 102 ([cdfbd70427e858aa5](claim-map.json)), and
196 ([ce254b3e7baea5d6c](claim-map.json)). The test combines
43 ([c0d5c8b1811953c5c](claim-map.json)) real-curated rows with a synthetic remainder
within 196 ([c250118d7d995249c](claim-map.json)) total rows. Synthetic cases use mutation-generated
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
9 ([cc60e0fede2451448](claim-map.json)) intact temporal pairs. Later temporal measurements use
20 ([cb0498eaeb5c11cb8](claim-map.json)) additive pairs and do not enlarge or pool that historical
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

The M5 agent answers 42 ([cf6ce992acebbcb45](claim-map.json)) of
196 ([cc5b0c7da5c708a21](claim-map.json)) cases, with answer rate
0.21428571428571427 ([c694177342b97faeb](claim-map.json)). Its answered-only accuracy is
0.9047619047619048 ([cd5245c19d8d3fa17](claim-map.json)); its full-coverage F1 is
0.36649214659685864 ([c050a2c472b81f453](claim-map.json)). The primary interprocedural effect interval is
[-0.4989621200147516 ([c3aa723f0e3855093](claim-map.json)),
-0.11013148303511262 ([c7f867f261235d2bc](claim-map.json))], with paired randomization probability
0.011749412529373532 ([c34b15b3401556269](claim-map.json)). These results indicate
underperformance against the frozen strongest non-agentic model baseline.
The historical temporal score is 1 ([c895e8892dc00a8c8](claim-map.json)) successful pairs out of
9 ([c756121365dd8e988](claim-map.json)), with exact interval [0.0028091367465991612 ([cafc570fa17d92101](claim-map.json)),
0.4824965149173369 ([cb6446543d15a4d90](claim-map.json))]. Its reporting bar is not evaluable at that support.

The attacker-with-bases weights were all zero in the frozen experiment. Its
result is null anti-gaming evidence, not a successful adaptive attacker or an
agent surface-floor test. The prior attacker floor remains vacated.
Supplemental ablations are reported separately and do not reopen M4 or M5.
The repeated hidden-roster follow-up retains its signed-reference
discrepancies, host-validity distinction, and failed quality bars. Later
configuration-four results are descriptive and **NOT_EVALUABLE**; the
historical M4 result remains **NO_GO** throughout this paper.

## Related work

**COBOL and mainframes.** MainframeBench evaluates mainframe knowledge, question answering, and COBOL summarization. [XMainframe: A Large Language Model for Mainframe Modernization](https://arxiv.org/abs/2408.04660)

**COBOL and mainframes.** COBOLEval evaluates generated COBOL solutions using a HumanEval-derived task and GnuCOBOL. [COBOLEval](https://github.com/zorse-project/COBOLEval)

**Regulation and source code.** GDPR-Bench-Android evaluates automated GDPR compliance detection in Android applications. [GDPR-Bench-Android](https://arxiv.org/abs/2511.00619)

**Regulation and source code.** Compliance-to-Code maps structured Chinese financial regulatory clauses to executable compliance logic. [Compliance-to-Code](https://arxiv.org/abs/2505.19804)

**Non-source-code compliance.** This work evaluates regulatory compliance in tool invocation rather than COBOL source conformance. [Evaluating Implicit Regulatory Compliance in LLM Tool Invocation via Logic-Guided Synthesis](https://arxiv.org/abs/2601.08196)

**Temporal legal reasoning.** This statutory question-answering study distinguishes post-cutoff staleness and recency bias and studies retrieval constrained by temporal validity. [Asking For An Old Friend](https://arxiv.org/abs/2605.23497v2)

**Temporal legal reasoning.** IndiaFinBench includes temporal reasoning over Indian financial regulatory text. [IndiaFinBench](https://arxiv.org/abs/2604.19298v2)

**Industrial modernization.** AWS Transform documents mainframe analysis, business-logic extraction, documentation, and COBOL-to-Java refactoring. [AWS Transform mainframe modernization documentation](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-mainframe.html)

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
report to the same source commit and benchmark manifest. The final artifact bindings and passed submission gates are recorded in the claim map.

## Conclusion

The benchmark makes version-conditioned source conformance and evidence
quality measurable. Historical M4 remains **NO_GO**, M5 retains measured
underperformance, and configuration four remains **NOT_EVALUABLE** for
release provenance. The results justify careful evidence contracts and
preservation of negative measurements; they do not justify autonomous legal
certification or claims that the agent dominates the baselines.

## Migration measurements

The source-bound numerical appendix includes the migration report's measured outcomes and mandatory-check counts. Detector-led results and oracle-assisted results remain separate; oracle-assisted fixtures do not establish general migration capability or legal correctness. Raw compiler logs and backend paths remain outside this anonymous paper.

The oracle-assisted track evaluated 4 ([c067f17b4ac4eb5c5](claim-map.json)) cases: 4 ([ccdcb778d20ee43a6](claim-map.json)) passed, 0 ([c6eb8b1d8d280e460](claim-map.json)) failed, and 0 ([c3e1b749dbbc73165](claim-map.json)) abstained, across 3 ([ca9d6df6ca122f081](claim-map.json)) distinct source bundles. The detector-led track has 0 ([c2a367b7823e411d1](claim-map.json)) eligible cases and remains inactive because detector release provenance is not evaluable. Successful finite oracle-assisted validations do not establish end-to-end detector-led migration success.
