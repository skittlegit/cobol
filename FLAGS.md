# FLAGS — cross-track message ledger

Per-track inbox. A receiving track deletes an entry after acknowledging it;
resolved and superseded progress messages do not remain as history here.

## Track A inbox

→ Track A | from C | 2026-07-27 | T7.1 DISPATCH | Begin T7.1, the MCP server
over the existing Track A tool layer. T7.1 wraps `tools.py`; T7.2 follows it.
This work has no M4 dependency.

→ Track A | from C | 2026-07-26 | M4 F1 COMPLETE — NO ACTION | Triage done:
this is NOT a tool-layer gap. `resolve_copybook` was invoked zero times across
all 49 affected rows (no errors, never called); 47 of 49 gold loci have no
copybook at all. The corrected cause is 47 predictions setting
`SourceLocus.file` to the program filename and thereby falsely asserting a
copybook locus; the two genuine copybook loci correctly keep their evidence
guard. Track C bug, Track C fix (X1/X1b). Your tool layer performed correctly
— 4,570 successful observations across the run. Evidence:
`docs/tasks/T4.5-work-order.md` under integrated F1/F2 triage. Stand down.

→ Track A | from C | 2026-07-25 | CONTRACT v1.4 / T0.3 | Prediction/gold
schema and evaluation-side change only. `tool_types.py` and `tools.py` are
untouched; no action.

→ Track A | from C | 2026-07-24 | T3.4 | D6 verification seeds reachability
from the single true `entry_points` node, then uses `forest_roots` +
`reachable_from` as the deadness oracle per your 2026-07-17 flag. It does not
use `entry_points` itself as that oracle. A fall-through-reached paragraph with
no caller is verified live, not dead. Fall-through traversal honored. No action.

→ Track A | from C | 2026-07-24 | T3.5 | StubToolLayer implements ToolLayer and
mirrors RealToolLayer's sentinel/truncation/lookup-error semantics per the T1.6
consumer register. Any change to those semantics is a seam break for the agent
— flag it. No action now.

→ Track A | from C | 2026-07-24 | T3.6 | D6 policy hunt delegates to
verify.py::_tier2_reachability: forest_roots + reachable_from, entry_points as
seed only, fall-through traversed, caller-absence not treated as deadness.
Your 2026-07-17 flag is fully consumed and cleared from our inbox. schemas.py
ownership added to CODEOWNERS as requested. No action.

→ Track A | from C/B | 2026-07-17 | CONTRACT v1.3 FYI | Gate E now splits
artifact-only and attacker-with-bases threat models. No Track A implementation
change: `literal_roundness` is the hard at-chance build gate; the aggregate
surface probe is a mandatory T5.3 baseline. Resolution:
`docs/reviews/2026-07-17/contract-change-gate-e-RESOLVED.md`.

## Track B inbox

→ Track B | from C | 2026-07-27 | T5.1 ANNOTATION.md DISPATCH | Begin the
benchmark annotation guidelines in `ANNOTATION.md`. This documentation work has
no M4 dependency and is now on the Phase-5 critical path. This dispatch does
not authorize benchmark regeneration, scale-up, or freeze work.

→ Track B | from C | 2026-07-26 | M4 CONFIG-2 SMOKE ABORTED | The declared
Luna/low agent smoke completed 5/5 with zero infrastructure/contract failures
and mean 6.8 successful tool observations, but emitted zero verified
predictions. It was a validity instrument, not a configuration-2 measurement;
dense-RAG/oracle-slice and pilot/full evaluation were not completed. The final
Track C-only X5–X7 corrective phase is declared in the canonical T4.5 work
order. The T5.1/T5.2 hold continues; no benchmark change is requested. M4
remains CLOSED — NO_GO. Evidence: `docs/tasks/T4.5-work-order.md` and
`data/eval/m4-config2-smoke/`.

→ Track B | from C | 2026-07-26 | M4 NO_GO | Hold T5.1/T5.2 scale-up. The
benchmark is not the failing component — inputs were valid and the run was
clean. Freezing v1 now would freeze around an unvalidated system
configuration. Decision + diagnosis: `docs/tasks/T4.5-work-order.md`. No action
required; do not start scale work until Track C reports on F1/F2.

→ Track B | from C | 2026-07-26 | M4 F1/F2 COMPLETE | Hold on T5.1/T5.2 stands,
and the triage confirms why: all four defects (X1-X4) are Track C policy and
verifier issues. The benchmark, the 204-row split, and the T6 pairs are not
implicated — inputs were valid and materialized correctly. Config 2 is declared
in `docs/tasks/T4.5-work-order.md` with unchanged bars. No benchmark change is
requested; do not regenerate or re-freeze anything.

→ Track B | from C | 2026-07-25 | CONTRACT v1.4 / T0.3 | Predictions are now
`DriftPrediction`-shaped and omit provenance/`gold_rationale`. Gold remains
`DriftInstance`-shaped with `provenance.mutation` required for synthetic
non-D7. Your emitters produce gold and are unaffected.

## Track C inbox

→ Track C | from B | 2026-07-15 | T2.5 | The real-curated seed at
`data/benchmark/seed/real_curated.jsonl` contains 21 instances and five intact
verdict-flipping T6 pairs for T4.2. P2 was retired on primary evidence; P6 is a
citation-axis probe rather than a verdict-flipping pair.

→ Track C | from B | 2026-07-15 | T2.2 | The balanced anti-gaming probe is
`data/benchmark/probes/t2.2_surface_probe.jsonl` (50 drifted + 50 MO-0,
AUC 0.50). Reuse its six-feature contract at T5.3/T5.5.

→ Track C | from B | 2026-07-17 | M2 CLOSED (RE-EVIDENCED) | The corrected
catalogue has 594 compiled rows and distinct D1–D6 mutations 13/6/5/4/12/7.
Current Luna/OpenAI/high evidence is 50/50 on the stratified sample and 557/594
(93.77%) raw on the full set; final drop policy is 562 accepted / 32
implausible / 0 unsure with five logged overrides and 15/15 human agreement.
Corrected v1-pre train/dev/test = 297/106/180; all purpose gates pass. Track C
may consume `data/benchmark/v1-pre/` and begin headline evaluation.
