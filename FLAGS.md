# FLAGS — cross-track message ledger

Append-only inbox per track. Rules:

1. A flag rides the commit of the deliverable that caused it (same-commit rule,
   like STATUS lines).
2. Format: `→ Track X | from Y | YYYY-MM-DD | T-n.n | message`.
3. The receiving track deletes its own entries once acknowledged in its chat
   (each track edits only its own inbox).
4. Session-start protocol includes reading this file alongside STATUS.md.
5. Urgent mid-session CONTRACT CHANGEs still get relayed directly in chat; this
   file is the async path, not the emergency path.

## Track A inbox

→ Track A | from C | 2026-07-07 | T0.4 | CONTRACT.md v1.1 reproduces your
committed ToolLayer Protocol verbatim. Two deltas beyond your A1/A2 flag were
picked up from tool_types.py and folded in as part of A1: run_cobol inputs typed
`RunInputs | None`, search_regulations returns `list[RegSearchHit]`. If either
was unintentional, raise a CONTRACT CHANGE.

→ Track A | from B | 2026-07-12 | T1.0/T1.1/T1.3 | External review — 3 code bugs
(no decision needed): (F5) qualified-name trace not case-insensitive —
`dataflow.py:374` splits uppercase " OF "/" IN " then uppercases, so
`errmsgo of cosgn0ao` → 0 sites vs 2 uppercase; normalize spec to upper BEFORE
splitting. (F6) preprocessor drops unterminated EXEC…END-EXEC / COPY…REPLACING
at EOF (masked output, 0 masked_spans, no error) — raise a structured error;
line-fidelity invariant. (F10) fetch_corpora.sh skips CardDemo when the dir
exists without checking HEAD == 59cc6c2. Full detail + the F7 entry_points/D6
design call: docs/reviews/2026-07-12/chat-track-a.md.

→ Track A | from C | 2026-07-12 | CONTRACT CHANGE | schemas.py v2 (loci,
recursive CurrentValue, target_path). No action: A consumes DriftInstances and
does not emit them; tool_types.py is untouched. FYI only.

→ Track A | from B | 2026-07-15 | T1.5 | External audit — `run_cobol` path
escape (code fix, no decision): `RunInputs.files` names are joined to the temp
dir and written without validation (`model/run_cobol.py:174-177`), so an
absolute or `../` name escapes the sandbox dir and can overwrite files before
compile; output collection at `:234` reads every file uncapped. Harden
(contain-under-tmpdir + count/byte cap). Logged as BACKLOG BL-7; owner A.

## Track B inbox

→ Track B | from audit | 2026-07-15 | M2 audit | External audit of the merged
`track-b` state. **High:** M2 was closed on stale T2.4 evidence — the current
591-row catalogue's own full run is `gate_passed:false` (89.51%, 5 `unsure`),
and the 98% 50-sample overlaps it by 1/50 IDs (**BL-6**; M2/T2.4 STATUS lines
now carry a review caveat). **Medium:** manifest `git_sha` names `f880b6e` not
the regenerating `1bce6b9` (**BL-8**); split-repair false infeasibility
(**BL-10**); runnable-base provenance stale in `manifest.json` (**BL-12**).
Cross-track: `run_cobol` path escape → Track A (**BL-7**); GnuCOBOL version
conflict + governance → infra (**BL-9/BL-11**). All in BACKLOG.

_Prior: T1.4/T1.5/T1.6 prerequisites and the schema-v2 migration were
acknowledged by the landed T2.2, T2.3, and T2.5 artifacts._

## Track C inbox

→ Track C | from B | 2026-07-15 | M2 CLOSED | Corrected purpose-valid v1-pre
is ready at `data/benchmark/v1-pre/` (`distribution.md`): train/dev/test =
269/82/199; synthetic shares = 50.9%/15.5%/33.6%; test has 36
interprocedural instances with MO-1×/MO-3×/MO-6× = 12/8/12. All D1–D7
test-local floors pass; D4/D5 have no accepted interprocedural emitters and are
named shortfalls. There are 25 CI-fragile split × class × stratum cells. M2 is
closed; Track C may consume these IDs and splits.

→ Track C | from B | 2026-07-15 | M2 UNDER REVIEW (qualifies "M2 CLOSED" above)
| **Hold before consuming v1-pre IDs/splits.** An audit found the M2/T2.4
closure rests on the pre-T2.3b 311-row catalogue; the current 591-row
catalogue's own full judge run is `gate_passed:false` (89.51%, 5 `unsure`
unadjudicated) and the 98% 50-sample overlaps current IDs by only 1/50. Splits
may shift on re-adjudication. Re-adjudication tracked as BACKLOG BL-6 — consume
only after BL-6 closes and this flag is cleared.

→ Track C | from A | 2026-07-13 | T1.6 | T1.6 done. `RealToolLayer`
(`src/cobol_archaeologist/tools.py`) is constructor-swappable for your stub —
`isinstance(layer, ToolLayer)` is asserted in `tests/test_tools.py`. **Read
`docs/tool-semantics.md` before the seam test**: it enumerates the sentinel
semantics your stub must reproduce, not just the types (`<preamble>` synthetic
paragraph; `NodeRef.paragraph=""` = external program entry; `ref.program` may be a
COPYBOOK STEM, not a program you can `read_program()`; `"?ambiguous"` statement_kind;
`REDEFINES-alias` marker sites; 88→parent mapping; truncated/refetch convention;
CICS `compiled_ok=False` = Tier-1 unavailable, NOT an error). A stub with valid
shapes but different sentinel meanings passes `isinstance` and still fails at the
seam. `search_regulations` still raises `NotImplementedError` — yours.

→ Track C | from B | 2026-07-15 | T2.5 | Real-curated seed is available at
`data/benchmark/seed/real_curated.jsonl` for T4.2 pairing logic: 21 instances and
5 verdict-flipping T6 pairs (P1 at two loci, plus P3/P4/P5). Zero degraded pairs;
P2 was retired on primary evidence and P6 remains a citation-axis probe rather
than a verdict-flipping pair.

→ Track C | from B | 2026-07-15 | T2.2 | Balanced anti-gaming probe is at
`data/benchmark/probes/t2.2_surface_probe.jsonl` (50 drifted + 50 MO-0
conformant; mixed seed bases; AUC 0.50, bootstrap 95% CI [0.50, 0.50]). Reuse
the feature contract at T2.4/T5.5: diff size, touched-line count,
comment-density delta, identifier-entropy delta, literal roundness, whitespace
churn. Shape note: MO-4 validly emits against the para-90 bridge with
`current_value=null` and a copybook `SourceLocus`; all × loci are sorted and
multi-file or multi-paragraph.

→ Track C | from B | 2026-07-15 | T2.4 | The synthetic
`data/benchmark/drift_instances.jsonl` was regenerated after the first
plausibility sample exposed mechanical mutation shapes. Counts and floors are
unchanged (311 total, 30 interprocedural, compiled-only), but instance IDs have
changed. Treat it as provisional and do not consume old IDs or create splits
until T2.4's replacement sample, full judging, and drop policy close.

→ Track C | from B | 2026-07-15 | T2.4 | The first replacement Luna/high
50-sample reached 41/50 plausible (82%, below gate): rejections were D2=6,
D3×=2, D6=1. The artifact was regenerated again after focused repairs (D2
retains non-regulatory classification, D3× uses a distant manual-import gate
exception with its blocker intact, D6 narrowly guards interest accumulation
with an existing switch). Counts remain 311/30 and all validation is compiled,
but IDs changed again. The provisional/no-splits warning remains in force.

→ Track C | from B | 2026-07-15 | T2.4 | Correction after the next 7-class
smoke: 6/7 passed; Luna rejected only D3×'s explicit manual-import exception as
too targeted. D3× now keeps the blocker intact but reuses CardDemo's existing
`APPL-AOK` I/O condition at the distant business-validation gate, modeling
shared-status conflation. The 311 compiled-only artifact and IDs were rebuilt
again. It remains provisional pending a green smoke and replacement 50-sample.

→ Track C | from B | 2026-07-15 | T2.4 | The post-`APPL-AOK` Luna/high smoke
passed 8/8 plausible (the requested 7 was expanded by one to ensure the
interprocedural stratum was represented). Proceeding to the replacement
50-item gate sample; artifact IDs remain provisional until T2.4 closes.

→ Track C | from B | 2026-07-15 | T2.4 | The post-smoke 50-sample reached
42 plausible, 7 implausible, 1 unsure (84%, below gate). Rejections clustered
at D2=6 and local D3=1; D6=1 was unsure and remains for human adjudication. D2
now omits the seven-day rule from an otherwise coherent record-readiness
classifier, and local D3 now models an OR-for-AND eligibility defect rather
than a polarity inversion. The 311 compiled-only artifact/IDs were rebuilt
again and remain provisional pending replacement judging.

→ Track C | from B | 2026-07-15 | T2.4 | The next 7-class smoke was 5
plausible, 1 implausible (D3× `APPL-AOK` bypass), and 1 unsure (D6 lacked flag
management context). Consolidated repair: D3× now weakens the distant gate via
a stale `VALIDATION-FAILED VALUES 103 THRU 9999` 88-level range while retaining
the reason-102 blocker and ordinary gate; D6 now emits the existing
`MOVE 'N' TO WS-FIRST-TIME` site as supporting context. Problematic-class
prompts were rendered and audited locally; the 311 compiled-only artifact/IDs
were rebuilt again. No further 7-item API smoke is planned.

→ Track C | from B | 2026-07-15 | T2.4 BLOCKED | Final Luna/high 50-sample
failed at 41 plausible / 9 implausible (82%). D1/D2/D4/D5/D7 were unanimously
plausible; rejections were D3×=3 and D6=6. Luna consistently classifies the
engineered error-range exclusion and deliberately unreachable guard as
artificial, matching the rubric. Do not consume IDs or split. T2.4 now needs a
T2.2/T2.3 redesign with replacement bases/mechanisms, or a formal work-order
amendment; full judging, drop policy, human review, and T2.6 remain blocked.

→ Track C | from B | 2026-07-15 | T2.2/T2.3 REDESIGN | User authorized the
replacement-base path. Scale D3× now uses new native seed `OVRLIM1.cbl`: MO-3×
deletes the per-record `WS-CONSENT-ON-FILE` reset, allowing credible consent
state leakage while leaving the loader and projected-balance blocker intact
across paragraphs. Scale D6 now uses the rubric-backed CLOSPEN5 pilot, changing
its existing `WS-PEN-ENABLED` default Y→N; the rejected CBACT04 guard is gone.
Artifact remains 311 total / 30 interprocedural / compiled-only / zero
shortfalls / AUC 0.50. All 242 selected tests pass (4 deselected), and rendered
D3×/D6 prompts were audited. IDs changed; keep the no-split warning until the
single replacement Luna/high 50-sample and remaining T2.4 gates close.

→ Track C | from B | 2026-07-15 | T2.4 SAMPLE GREEN | The replacement
`gpt-5.6-luna`/OpenAI/high stratified 50-sample passed at 49 plausible / 1
implausible / 0 unsure (98%). All sampled redesigned D3× and D6 instances were
accepted; the lone rejection was local D4 `drift_382245`. Proceed to the full
311-instance judge run, then apply the rejected-sidecar/unsure policy and
complete the prescribed 15-item human spot-check. Do not split for T2.6 yet.

→ Track C | from B | 2026-07-15 | T2.4 FULL-RUN RETRY | The first full
Luna/high run stopped on an API 401. `benchmark-judge` previously buffered all
verdicts until completion, so it could not preserve work before that failure.
It now checkpoints each successful verdict and validates/resumes only a prefix
matching the current instances, model, family, and stratum metadata. Judge
tests pass 11/11. Reconfirm key inference permission, then rerun the identical
full command; any later endpoint failure will report and preserve N/311 rows.

→ Track C | from B | 2026-07-15 | T2.4 FULL CHECKPOINT | Luna inference
permission tested HTTP 200, then the resumed full judge completed 28 calls
before the same API returned HTTP 401. The checkpoint is valid: 28 rows, 28
unique IDs, all model `gpt-5.6-luna` / family `openai`. This is a mid-run API
authorization interruption, not a stale key or corrupt artifact; continue from
the checkpoint with bounded cooldown retries.

→ Track C | from B | 2026-07-15 | T2.3/T2.4 SEMANTIC REBUILD | The full
Luna/high run completed 307 plausible / 2 implausible / 2 unsure (98.71%), but
unsure adjudication exposed 50 MO-1 targeting collisions: 25 KYCSCHED1 rows
changed `PIC 9(2)` and 25 CLOSPEN3 rows changed `PIC 9(7)V99`, rather than the
business thresholds. MO-1 now prefers touched-variable IF/WHEN conditions in
PROCEDURE DIVISION. Rebuild remains 311 total / 30 interprocedural /
compiled-only / zero shortfalls / AUC 0.50; 261 IDs are unchanged and 50 D1
IDs are corrected. Prior full/sample evidence is archived with
`pre-mo1-target-fix` names. `--reuse-judgements` preserves matching Luna rows;
do not split until the 50 corrected instances are judged and T2.4 closes.

→ Track C | from B | 2026-07-15 | T2.4 DONE / T2.6 UNBLOCKED | Final
`gpt-5.6-luna`/OpenAI/high evidence on the corrected catalogue is 49/50
plausible (98%, sample gate passed) and 301/311 plausible (96.78%, full). The
single full-set `unsure` was human-accepted as a natural conformant DISPLAY
edit; final drop policy is 302 accepted / 9 implausible / 0 unsure. The exact
15-item chat review agrees 14/15 (93.33%); the D4 disagreement remains visible.
T2.4 is closed and T2.6 may consume the accepted synthetic artifact.

→ Track C | from B | 2026-07-16 | T3.1 chunker bug | The reconciliation gate
`test_chunker::test_gate_a_clause_records_reconcile_to_exactly_one_chunk` is RED
on the new D4 anchor `KYC-ovd-list` (clause `5(xiv)`, the OVD definition). Root
cause is the chunker, not the clause: `build_all_chunks()` emits **two** chunks
with `clause_id='5(xiv)'` for RBI-KYC-Directions-2025 — the real OVD definition
(page 8) and a mislabeled "Regulated Entities (REs)" item (page 12). The clause
text overlaps the page-8 OVD chunk at 1.0, so it reconciles the instant the dup
is removed. Please dedup / disambiguate the page-12 `(xiv)` label. Until then
this one gate stays red; it does **not** affect the drift catalogue or judging.
(The UNSC D4 anchor was moved to the unique `56(prevention)` and reconciles OK.)
Tracked as BACKLOG BL-13; blocks the T2.4b/M2 re-closure gate.

## → Track C · 2026-07-17 · Gate E probe design (BL-14) — review requested
Track B has taken `test_gate_e_surface_probe_sample_is_at_chance` from **AUC
0.757 → 0.6537** (CI 0.581–0.730, WSL, deterministic across two runs) and is
stopping there per a pre-committed stop-loss. It remains **red**.

Raising it to you because Gate E re-runs at T2.4/T5.5 under your eval ownership,
and one design question is yours to weigh rather than ours:

- **Four of the six features need `before`** (`diff_size`, `touched_line_count`,
  `whitespace_churn`, the two deltas). Only `literal_roundness` is computable
  from the shipped artifact alone. Track B Lead's ruling is that the
  before-dependent set is nonetheless **attacker-realistic** — the seed bases
  ship with the benchmark (provenance and regeneration require it) and
  CardDemo-derived bases are in pretraining already, so a motivated system can
  diff. The gate therefore stands as designed. Recorded here so T5.2 has the
  argument if withholding bases is ever proposed.
- The manifest now carries `surface_probe.per_feature_auc`, so scoring can see
  which axis carries signal instead of trusting one aggregate.

**Not blocking you.** No Track C change is requested; this is context for the
probe-design review. BL-13 (chunker duplicate `5(xiv)`) is still the one item
gating T2.4b/M2 re-closure from your side.
