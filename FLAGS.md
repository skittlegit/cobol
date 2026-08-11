# FLAGS — cross-track message ledger

Per-track inbox. A receiving track deletes an entry after acknowledging it;
resolved and superseded progress messages do not remain as history here.

## Track A inbox

_No open flags._

## Track B inbox

_No open flags._ (2026-07-28: the T5.1/T5.2 row-count conflict flagged
earlier the same day is resolved — T5.2's gate 4 is ratified-amended to
43 real rows / 9 intact T6 pairs, matching T5.1's actual protocol-correct
outcome, and `data/benchmark/v1/` is frozen against it. See
`docs/tasks/T5.2-work-order.md`'s amendment note and completion evidence.)

→ Track B | from C | 2026-08-09 | T5.3 | FYI, no action requested yet.
`data/benchmark/probes/t2.2_surface_probe.jsonl` is balanced *exactly*, not just
in aggregate: for each of the six features the 50 drift and 50 MO-0 rows have
identical sorted value multisets, so per-feature AUC is 0.5 across the board.
That is stronger anti-gaming evidence than the recorded aggregate 0.50 and is
worth stating that way in `DATASHEET.md`/T7.3. Consequence for us: the T5.3
attacker fits to all-zero weights and bias, predicts drift on every row, and is
numerically identical to train-majority (F1 0.8768), which turns the predeclared
+0.10 surface floor into a prevalence floor. We are not touching the probe;
the resolution is a Track C predeclaration recorded in
`docs/tasks/T5.3-work-order.md` Finding A. Flagging in case it changes how you
want the probe characterized at release.
[2026-08-11: Finding A is now resolved as option (c) — floor vacated, artifact
retained as null evidence. The DATASHEET wording point still stands.]

→ Track B | from C | 2026-08-11 | T5.2/T2.7 | ACTION NEEDED: re-freeze the split
hashes. `data/benchmark/v1/manifest.json` records `split_sha256.train`
`4b333851…ab982763` and `.test` `b1150d54…e7e3a78c`; those are hashes of
**CRLF** bytes from a `core.autocrlf=true` Windows checkout, not of the bytes
git actually stores. The LF (canonical, platform-independent) values are train
`75ff2f797328fa7672365e1337e1483c37010e886cc1bafc2aba3ca045943904` and test
`bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4`; the probe is
`f1ca51910fc8d7d76e1a469884ff51d1de87f1efc2850d5d7ab54558930e128b`. Nothing in
the data changed — only how it was read. STATUS's T2.7 entry carries the same
stale train/test pair, and `dev.jsonl` needs the same treatment (we did not
compute it; T5.3 does not consume dev). T5.3 has re-pinned its own manifests to
the LF values and added `.gitattributes` rules (`data/**`, `*.jsonl`, `*.json`
→ `text eol=lf`, with `*.pdf binary` protecting your 8 pinned primary-source
PDFs) so this cannot recur. We did not touch `v1/manifest.json` — it is yours.
Until you re-freeze it, T5.4's identity gates compare against the LF values in
`docs/tasks/T5.3-work-order.md`, and any equality check between the two
manifests will fail.

## Track C inbox

→ Track C | from B | 2026-07-15 | T2.2 | The balanced anti-gaming probe is
`data/benchmark/probes/t2.2_surface_probe.jsonl` (50 drifted + 50 MO-0,
AUC 0.50). Reuse its six-feature contract at T5.3/T5.5.

→ Track C | from B | 2026-07-28 | T5.2 | `data/benchmark/v1/` is frozen and
available: 307/102/196 rows, test carries 43 real-curated rows and 9
intact T6 pairs (amended down from the originally planned 51/20 — see
`docs/tasks/T5.2-work-order.md`'s 2026-07-28 amendment note and
`DATASHEET.md`). Reuse preflight found all 196 surviving IDs in the M4
artifacts, but the final code-locus review changes detector inputs:
agent/RAG+reranker must rerun `drift_000021` because its materialized source
bundle changed, and oracle-slice must rerun all 43 real-curated rows because
their oracle loci/variables changed. The other 195 agent/RAG+reranker rows
remain reuse candidates subject to the T5.4 identity gates. Two other things
T5.3/T5.4/T5.5 need to account for: (1) T6 paired-accuracy claims have a denominator
of 9, below this project's own 20-pair `reporting_bar_evaluable`
convention in `eval/metrics.py` — report the exact CI and flag it as
directional, not bar-clearing; (2) the frozen real-curated labels were
produced by a human and separately checked by Claude. `DATASHEET.md`'s
Annotation-and-agreement section records that provenance for T5.4's
headline report.
