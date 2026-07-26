# M4 F1 + F2 triage

**Owner:** Track C · **Date:** 2026-07-26 · **Cost:** zero — all analysis reads
committed artifacts at `357f483`.

## 1 — F1: the `resolve_copybook` guard (49 rows)

**Verdict: Track C policy bug. Track A is cleared.**

49 abstentions read `policy evidence guard: required tool evidence missing:
resolve_copybook`.

| Evidence | Finding |
|---|---|
| `resolve_copybook` invocations across all 49 rows | **0** — never called, so zero errors |
| Agent activity on those rows | mean **4.02** steps; 63 `read_paragraph`, 55 `grep`, 50 `read_program`, 20 `run_cobol` |
| Gold loci that reference a copybook (`file != None`) | **2 of 49** |
| Gold drift types | D1 ×37, D3 ×12 |
| Stratum | 47 single-paragraph, 2 interprocedural |

The T3.6 hunt policy makes copybook resolution an **unconditional** precondition
for D1/D3, then rejects findings for lacking evidence about a copybook that does
not exist. Schema v2 already carries the correct discriminator:
`SourceLocus.file is None` ⇒ the program's own source.

**Origin:** the T3.6 work order's per-class detection contract specified D1's
evidence hook with MO-1× (threshold-in-copybook) in mind and failed to condition
it on the locus. Track C's error, authored in this chat.

**Impact:** 49/157 abstentions = **31% of all abstentions, 24% of the test
split** — and concentrated in the two most tractable classes.

## 2 — F2: the interprocedural stratum (36 rows)

**This corrects a claim I made on 2026-07-26.** I previously argued that because
the agent's abstention rate is uniform across strata (75% / 77%), coverage could
not explain the interprocedural gap. That reasoning was wrong: the comparison is
against dense-RAG, whose coverage is *not* flat.

| System | Coverage (of 36) | Accuracy when answering | Correct / 36 |
|---|---|---|---|
| Agent | 9 (25%) | **0.556** | **5** |
| dense-RAG | 19 (53%) | 0.474 | **9** |
| Oracle-slice | 15 (42%) | 0.067 | 1 |

The agent remains the most accurate per answer even interprocedurally, and still
loses — dense-RAG produces **9 correct answers to the agent's 5** purely by
answering twice as often. Dense-RAG's coverage falls from 65%→53% moving into
this stratum while the agent's holds at ~25%; the agent's absolute coverage
deficit is the driver. **Coverage explains the headline gap after all, in both
strata.**

**The copybook fix barely helps here.** Of 27 interprocedural abstentions, only
**2** are the policy guard; **25** are substantive. Fixing F1 will raise overall
coverage substantially while leaving the headline stratum nearly untouched.

**Three further causes, visible in the 25 substantive reasons:**

- **C1 — NLI verifier rejecting at the coin-flip line.** `citation rejected:
  cited clause … does not entail the claim (P=0.4995, deberta-v3-base-mnli-
  fever-anli)`. A 0.5 threshold rejecting at P=0.4995 discards findings on
  numerical noise. Consistent with Tier 3 faithfulness of 1/16 — the entailment
  gate is both unreliable *and* aggressive.
- **C2 — a second undocumented hard guard.** `batched evidence minimum not met:
  2 successful observation(s), 3 required`. Another fixed threshold in the hunt
  policy, not derived from the drift class.
- **C3 — composite-clause leaf confusion.** *"the observed 7 and 500 values
  match clause leaves"* and *"the observed literal 500 is a penalty multiplier,
  not a resolved source value for the no-capitalization leaf."* With 7 of 21
  clauses composite, the agent cannot reliably identify **which leaf** a literal
  should be compared against. This is the exact failure predicted in the T0.3a
  ratification (Item 3), which added `target_path` to *gold* — the prediction
  side never got the corresponding leaf-disambiguation support.

## 3 — Fixes

| ID | Fix | Owner | Size |
|---|---|---|---|
| **X1** | Condition the copybook evidence requirement on `file != None`; otherwise `read_paragraph`/`grep` literal evidence satisfies the D1/D3 hook | C | one condition |
| **X2** | Derive the evidence minimum from the drift class instead of a fixed 3; a single-locus D1 needs one literal observation, not three | C | small |
| **X3** | Raise the entailment-rejection margin off 0.5 (reject only below a declared band, e.g. ≤0.40) and record the NLI probability on every finding | C | small |
| **X4** | Surface the clause's leaf structure to the hunt when `current_value.kind == "composite"`, so the agent enumerates candidate leaves rather than guessing | C | moderate |

All four are Track C. **None require Track A or Track B.**

## Correction — 2026-07-26 (same day, pre-implementation)

The F1 mechanism recorded above is **wrong**, and the fix it implied (X1:
"condition the copybook requirement on `file != None`") would have been a
no-op. Corrected by inspecting `agent/hunts/d1.py` and recovering the proposed
predictions from `trajectory.model_responses`.

**What the guard actually does.** `D1Hunt.validate_response` is already
conditional:

    if any(locus.file for locus in loci):
        errors += require_tools(transcript, {"resolve_copybook"})

It keys on the **prediction's** loci, not gold's.

**What actually happened.** All **49/49** proposed predictions set `file` on
their loci, with values such as `CLOSPEN1.cbl` — a *program* filename, not a
copybook. Per schema v2, `SourceLocus.file` is `None` when the line lives in
the program's own source and non-null only when it resolves through a COPY
expansion. The agent populated it with the program name, thereby asserting a
copybook locus, and the guard correctly demanded `resolve_copybook` evidence
the agent had no reason to gather.

**So the guard is correct and the prediction is wrong.** Root cause is the
`file` field's semantics not surviving into the prediction path: the name
`file` reads naturally as "the file this line is in," and the prompt did not
disambiguate. This is a Track C schema-ergonomics defect originating in the
T0.3a schema-v2 design authored in the Track C chat.

**Unchanged:** the 49 rows, 31% of abstentions, D1×37 / D3×12, 47/49
single-paragraph, and the conclusion that Track A is not implicated.
`resolve_copybook` was still never invoked and the tool layer still performed
correctly.

**Separately confirmed latent bug:** `agent/hunts/d4.py` requires
`resolve_copybook` **unconditionally**. D4 was not among the 49 rows, so this
has not yet fired, but it will. Fixed as X1b.
