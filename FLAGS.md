# FLAGS — cross-track message ledger

Per-track inbox. A receiving track deletes an entry after acknowledging it;
resolved and superseded progress messages do not remain as history here.

## Track A inbox

→ Track A | from C | 2026-07-24 | T3.3a | `RealToolLayer.search_regulations` is
now live (was `NotImplementedError`): it delegates to Track C's
`rag/search.RegulationSearch`. Only the `search_regulations` method body in
`tools.py` changed — signature, other methods, and `tool_types.py` are
untouched, so `issubclass(RealToolLayer, ToolLayer)` still holds. **One action:**
your test `tests/test_tools.py::test_search_regulations_is_a_typed_stub` still
asserts `pytest.raises(NotImplementedError)` and is now RED by design — please
retire/update it (T1.6's stub-era guard; the CONTRACT method is implemented as
of this task). No other Track A change needed.

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

_No open flags._

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
