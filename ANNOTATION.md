# COBOL Regulatory-Drift Annotation Guidelines

These guidelines define benchmark gold annotation for COBOL Archaeologist.
They implement the frozen schema and CONTRACT v1.4; they do not change either.
Annotators record what the cited regulation requires and what the cited source
does, not what a detector is likely to predict.

## Annotation unit

One annotation unit is one regulation-clause version evaluated against one
specific COBOL program scope. The output is one `DriftInstance`:

- one temporally pinned `RegulationClause`;
- one or more source loci describing a single compliance judgment;
- exactly one class D1–D7;
- program, paragraph, and line labels;
- a concise evidence-linked `gold_rationale`; and
- provenance recorded only after the independent semantic decision.

Do not combine separate defects merely because they occur in the same program.
Create separate instances when the regulatory obligation, defect class, or
code locus differs. Do not split one interprocedural judgment into several
rows merely because it crosses programs or paragraphs.

## Evidence hierarchy

Use evidence in this order:

1. the archived primary regulation text for the stated version and effective
   date;
2. the original COBOL program and copybook text at pinned source coordinates;
3. compile or behavioral evidence from the version-of-record GnuCOBOL
   toolchain where the program is runnable;
4. parser, call-graph, dataflow, slice, and copybook-expansion evidence that
   preserves original source coordinates;
5. secondary regulatory material only to locate or interpret primary text,
   never to override it.

If primary text, operative date, source identity, or the relevant code behavior
cannot be established, mark the candidate `needs_adjudication`; do not guess a
class or use an LLM verdict as gold. An annotator may consult domain expertise,
but any decisive interpretation must be written in the rationale and linked to
the primary evidence.

## Class decision procedure

First ask whether positive source evidence establishes conformance to the
entire scoped obligation. If yes, use D7. Otherwise classify the evidenced
defect using the rules below. “Searched and found nothing” is not D7; depending
on the evidence it is D2 or unresolved.

### D1 — Stale threshold or value

Use D1 when an implemented scalar, categorical, or enum-valued business rule
does not match the value mandated by the pinned clause version.

- Identify the exact source literal or reference value and its use in the
  compliance decision.
- Resolve the clause's typed `current_value`.
- For a composite value, set `target_path` to the exact non-composite leaf.
- Do not use D1 for a correct value with only an inclusive/exclusive comparator
  defect; that is D5.
- Do not infer staleness solely from round numbers, comments, formatting, or
  apparent code age.

### D2 — Missing rule

Use D2 only when the regulation mandates a check or action and the scoped
implementation lacks it after a bounded, documented search.

- Inspect the expected decision path, callers/callees, relevant variables, and
  shared copybooks or called programs.
- Record `labels.line_level` as the insertion-point line or lines where the
  missing check should live. This is insertion-point matching, not fictional
  deleted-code localization.
- Explain why the proposed insertion point controls the regulated behavior.
- Absence from one paragraph is insufficient if the rule may be implemented
  elsewhere in the reachable path.

### D3 — Contradictory behavior

Use D3 when two reachable implementations produce conflicting compliance
outcomes for the same regulated condition.

- Cite both typed loci and name the conflicting outcomes.
- Confirm that the paths address the same obligation and input condition.
- A legitimate exception, risk tier, version branch, or mutually exclusive
  scope is not a contradiction.
- Set `is_interprocedural=true` whenever the contradiction spans programs and
  also when a single-program, cross-paragraph judgment depends on following
  control or data flow.

### D4 — Stale reference data

Use D4 when a code- or copybook-backed reference collection is missing a
required member, includes an impermissible member, or otherwise differs from
the clause's governed set.

- Enumerate the regulated set and the implemented set in the rationale.
- Cite the declaration and the executable consumer when both are needed to
  establish that the table affects behavior.
- Abbreviated storage codes are not automatically stale; annotate the semantic
  mapping, not surface spelling alone.
- Use D1 instead when the disputed value is a scalar or enum-valued business
  rule rather than shared reference data.

### D5 — Boundary error

Use D5 when the implemented comparator mishandles an equality or edge case
relative to the clause's typed comparator.

- Record both source and clause comparator and the boundary value.
- For a composite `current_value`, set `target_path` to the compared leaf.
- Distinguish `>`, `>=`, `<`, `<=`, equality, and inequality explicitly.
- If the comparator is correct but the literal is obsolete, use D1.

### D6 — Dead compliance code

Use D6 when code that appears to implement the obligation is unreachable from
the true program entry under the supported control-flow semantics.

- Seed reachability from the true entry node and judge deadness with the
  reachability graph, including supported fall-through edges.
- Caller absence alone is not deadness.
- Cite the existing compliance paragraph and the reachability evidence.
- A missing implementation is D2, not D6.

### D7 — Conformant

Use D7 only with positive evidence that the reachable implementation matches
the whole scoped obligation.

- Cite the matching literal or set, comparator, decision path, and relevant
  cross-program behavior.
- Search failure, incomplete evidence, or uncertainty is never conformant by
  default.
- `labels.program_level` and `labels.paragraph_level` are `conformant`;
  `labels.line_level` is empty under the frozen schema.
- For a composite obligation, the rationale must address all leaves needed for
  the scoped judgment, not merely one convenient match.

## Locus and label conventions

`code_locus.loci` contains original-source coordinates. Each locus records the
program, optional paragraph, optional copybook/file, and inclusive 1-based line
span. `file=null` means the program's own source; a program filename must not be
placed in `file`. Every `labels.line_level` reference must fall within a locus
with the same `(program, file)`.

`slice_vars` lists the variables necessary to connect the cited source to the
judgment. Keep it minimal but sufficient; do not add unrelated identifiers to
make a locus appear interprocedural.

Set `is_interprocedural=true` when loci span more than one program. It may also
be true for a single-program cross-paragraph judgment when following control or
data flow is required. A single-program locus does not force it false.

`target_path` is a dotted path relative to a composite
`regulation_clause.current_value.value` mapping. D1 and D5 require it when the
clause value is composite, and it must resolve to a non-composite leaf. Use null
for a leaf value and for classes where no leaf is being targeted.

For D1–D6, program-level gold is `drift`. Paragraph-level gold describes the
cited compliance paragraph. D2 line labels are insertion points. For D7, use
conformant program/paragraph labels and an empty line list.

## Clause and value conventions

Record `doc`, `clause_id`, `version`, `effective_date`, and exact primary text
from the pinned archive. `version` identifies the cited document version; do
not back-date it to encode an earlier operative lineage.

Encode a measurable mandate as a typed `current_value`. Composite nodes contain
named child values and no comparator; comparators belong to leaves and use only
the frozen vocabulary: `strictly_greater`, `at_least`, `strictly_less`,
`at_most`, `equal`, or `not_equal`. Use null only when the clause mandates a
check rather than a value.

## Versioned-judgment pairs

T6 pairs evaluate byte-identical code against two clause versions. Pair members
must have byte-identical `code_locus`, including locus order, spans,
`slice_vars`, and `is_interprocedural`. Pair identity is derived from structural
equality; do not invent a `pair_id`.

Annotate each side independently from its primary text before comparing
verdicts. Opposite labels are expected for verdict-flipping pairs but must not
be forced. Same-verdict citation probes must be named as such in the registry.

For P1 working-day penalty accrual under the 2022 wording, the old-side verdict
is `defensible-ambiguous`: the amount is explicit but the calendar-day basis is
not. Do not silently label that side conformant or drifted. Route it to
adjudication, retain both readings, and exclude it from a binary paired claim
unless the adjudication record identifies decisive primary authority.

## Gold-only fields and leakage control

`provenance`, `gold_rationale`, mutation metadata, generator seeds, judge
verdicts, existing labels, and prior annotator notes are gold construction
data. They are never system input and are hidden during independent
annotation. Synthetic mutation metadata is attached only after the semantic
label is finalized; it may verify lineage but may not decide the label.

The gold rationale must state the regulatory requirement, the source fact, and
why their relationship yields the selected class. It must stand without naming
the mutation operator. For real-curated rows, provenance annotator notes may
record ambiguity and adjudication references after the independent pass.

## Independent annotation

Each candidate receives two independent annotations from qualified annotators.
Both annotators see the same pinned primary clause, source bundle, build
evidence, and approved static-analysis outputs. Neither sees the other's work,
existing gold, mutation metadata, model predictions, or judge verdicts.

Each pass records:

- include, exclude, or needs-adjudication;
- D1–D7 class when included;
- clause/version identity and typed value;
- loci, target path, labels, and interprocedurality;
- a rationale with source and regulation pointers; and
- one or more structured disagreement codes when uncertain.

The two records are immutable inputs to adjudication. Discussion begins only
after both are timestamped and locked.

## Adjudication

An adjudicator reviews both independent records, the primary evidence, and the
named disagreement—not merely the proposed labels. The adjudicator may accept
one record, synthesize a corrected record, request additional primary evidence,
or exclude the candidate.

Every change log entry records candidate ID, fields changed, both original
values, final value, adjudicator, date, evidence pointer, and rationale.
Adjudication must not erase the independent labels. System outputs and
benchmark performance remain hidden until the dataset is frozen.

## Agreement reporting

Report agreement before adjudication:

- raw agreement for inclusion, class, program label, paragraph label,
  interprocedurality, and exact target path;
- Cohen's κ for mutually exclusive categorical decisions when both annotators
  label every sampled item;
- Krippendorff's α when decisions contain missing values, exclusions, or
  multi-valued localization judgments;
- exact and overlap agreement for source spans; and
- disagreement counts by structured reason.

Publish sample size and confidence intervals. Never report only post-
adjudication agreement, and never pool D1–D7 class agreement with localization
agreement into one flattering number.

## Anti-gaming

Annotate regulatory semantics, not edit artifacts. Do not consult git history,
commit messages, file mtimes, mutation diffs, generator order, or comment
freshness. Formatting discontinuities, identifier style, and literal
roundness are not label evidence. MO-0 benign edits must remain indistinguishable
from drift-producing edits at the annotation interface.

The artifact-only `literal_roundness` probe remains a build integrity gate. The
six-feature attacker-with-bases surface probe remains a declared T5.3 baseline.
Neither probe supplies gold labels or permits an annotator to reverse-engineer
the mutation process.

## Quality-control checklist

Before accepting a row, confirm:

1. primary clause version and effective date are pinned;
2. every line reference resolves to original source;
3. class inclusion and exclusions above are satisfied;
4. D2 insertion points, D6 reachability, and D7 positive evidence use their
   special rules;
5. `target_path` and comparator resolve correctly;
6. labels fall inside loci and interprocedurality is deliberate;
7. rationale is evidence-complete without mutation clues;
8. independent records and any adjudication change log are retained; and
9. the row round-trips the frozen `DriftInstance` schema.
