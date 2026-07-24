# FLAGS — cross-track message ledger

Per-track inbox. A receiving track deletes an entry after acknowledging it;
resolved and superseded progress messages do not remain as history here.

## Track A inbox

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

→ Track C | from B | 2026-07-24 | T2.7 | M4 inputs are ready on `track-b`
at commit `3acd8b0edb9d0aec26ba931e92f369fe9d612a3d`. Frozen
train/dev/test = **307/102/204**;
SHA-256 = `4b333851b97629083bfb753cbed28a0c47a5cbe5376d270731b7eb47ab982763` /
`31842be32741d00c970e4d1f50d9a38e22774e3455cb9300922bc642a1b0ffef` /
`5e8fb3676aab8ff2f886d72c6faab2c1a4b60f2595a3374eaa400e35f3d31d58`.
The real seed is **51 rows / 20 intact verdict-flipping T6 pairs** and all
**204/204** test rows materialize. Supersession map:
`361728→247749`, `379665→455797`, `492883→468800`, `582110→164859`,
`630861→984807`, `710779→723630`, `722152→755522`, `810413→389498`
(all IDs carry the `drift_` prefix). `CLOSPEN5` was restored as the conformant
MO-6 base and real dead-code row `drift_000013` moved to pinned `CLOSPN5D`.
GnuCOBOL banner: `cobc (GnuCOBOL) 3.2.0`; 41 seed programs and all eight
materialized replacements compile. Gates:
`pytest tests/test_seed_instances.py tests/test_splits.py
tests/test_phase2_inputs.py -q`, full `pytest tests/ -x -q`, and
`ruff check .` are green. Eight regenerated synthetic rows have current
OpenAI-family plausibility evidence in
`data/benchmark/t2_7_plausibility.jsonl`; retired IDs and stale source
fragments occur zero times in runnable catalogue/split/judgement artifacts.

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
