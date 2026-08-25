# T6 migration candidate roster

This directory currently contains a **candidate-only** 12-case roster selected
from the frozen benchmark-v1 test inventory before configuration-3 results were
available. It is balanced at two candidates per D1-D6 and six local versus six
interprocedural candidates.

The files deliberately separate information by audience:

- `candidate-roster.jsonl` records selection, hashes, capability, and review
  state. It contains no oracle prediction or behavioral specification.
- `detector-visible-candidates.jsonl` contains only the regulation and pinned
  materialized-source envelope. Its verified configuration-3 finding is still
  `null` and gated on detector utility.
- `oracle-candidate-specs.jsonl` separately holds candidate oracle predictions,
  allowlisted loci, intended behavior, and unaffected regression behavior.
- `candidate-manifest.json` pins the inventory and artifact identities and
  records the balance and ineligible state.

Every row is `human_review_pending`, independently unverified, unadjudicated,
and `eligible_for_evaluation=false`. These files are not the canonical
`data/migration/cases.jsonl`; they do not authorize model calls, patches,
validation runs, or migration claims. Promotion requires human-primary review,
independent verification, adjudication where needed, concrete executable/static
fixtures, and a new frozen canonical manifest. The candidate manifest also
discloses three repeated materialized-source pairs (nine distinct bundles across
the twelve benchmark instance IDs); review must deduplicate or justify those
pairs before promotion and statistical scoring.
