# Plausibility-judging rubric

Used by `benchmark/judge.py` when judging whether a mutated benchmark row looks
like drift that could occur in real legacy code. Restored from the archived T2.4
work order.


Judge whether a mutated COBOL locus resembles regulatory drift that a real
legacy maintainer could leave behind. This is not a correctness
re-annotation—the clause and mutation label are fixed. The question is whether
the code shape is credible enough for benchmark use.

## Verdicts

- **plausible:** a realistic maintenance history could produce the shown code;
  the change fits surrounding COBOL style and uses believable values or flow.
- **implausible:** the code is mechanically damaged or contrived, with absurd
  values, pointless structure, unrelated edits, sharp style discontinuity, or
  an obvious generator fingerprint.
- **unsure:** credibility depends on missing operational context or domain
  facts. Preserve the uncertainty and send it to human adjudication.

## Review dimensions

1. **Legacy-maintenance story:** can a stale constant, missed branch, inverted
   gate, old reference list, boundary choice, or disabled flag result from an
   ordinary incomplete change?
2. **Style continuity:** do names, fixed-format layout, comments, paragraph
   structure, indentation, and literal formatting match the surrounding file?
3. **Magnitude and semantics:** are replacement values historically or
   operationally believable, and does the edit affect the regulated behavior
   at the displayed locus?
4. **Artificiality:** reject unmatched syntax, wholesale unrelated deletion,
   mutation-announcing sentinel text, or changes whose only purpose is to
   satisfy a benchmark label.

The judge sees the clause text and mutated context, but not gold rationale,
drift label, mutation operator, or provenance. Conformant controls are included:
plausible means the code or maintenance edit looks natural, not that the
excerpt must violate its clause.

## Worked seed examples

### Example 1 — BOIDENT1 stale beneficial-owner threshold

`BOIDENT1` retains the former 15-percent partnership threshold after the KYC
rule moved to more than 10 percent. **Plausible:** a documented historical
value survived an amendment, and the comparison remains ordinary COBOL.

### Example 2 — LATEFEE1 charges the total amount due

`LATEFEE1` computes the late charge from `WS-TOTAL-AMT-DUE` instead of the
outstanding amount after the due date. **Plausible:** both are nearby compatible
business amounts, so choosing the old/wrong base resembles an incomplete
migration rather than a type error.

### Example 3 — CLOSPEN5 penalty path disabled by a flag

`CLOSPEN5` contains the penalty paragraph but initializes its enabling flag to
`N`. **Plausible:** pilot and feature flags commonly survive rollout, the value
matches the representation, and the guarded code remains stylistically
consistent. An impossible value or unrelated random flag would be
**implausible**.

## Human spot-check and run protocol

Review exactly 15 unique instances from the stratified 50-item sample and
record `instance_id`, one of the three verdicts, and a short reason. Agreement
is exact verdict agreement; disagreements remain visible, and every `unsure`
must be adjudicated before closure.

Configure the API key, different-family model, endpoint, and explicit reasoning
effort. Run the deterministic sample first, then the full catalogue, then apply
all unsure adjudications and the 15-row review. Checkpoints resume compatible
rows only; `--reuse-judgements` additionally requires matching instance ID,
drift type, stratum, model, family, and prompt contract.

