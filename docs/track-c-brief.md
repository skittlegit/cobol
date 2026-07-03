# Track C — Execution Brief (T0.3, T0.4, T0.6, T3.1–T3.6)

Agent, RAG & Evaluation track. Near-term milestones: close the M0 items this
track owns, then **M3 — Agent Grounded** (agent navigates real tools, emits
findings with a verifiable trace: clause → slice → behavior → citation). Phase
4+ (T4.x metrics runs, baselines, migration, paper) is out of scope for this
brief. Tasks marked **[chat]** happen in the Track C chat; **[code]** via Claude
Code in this repo. Read `CLAUDE.md` first.

## Dependency correction (supersedes earlier Track C assessment)

T0.4 is **not fully blocked**. `CONTRACT.md` has two halves: the **tool I/O
contract is already fixed** — copy it verbatim from
`docs/track-a-phase1-brief.md` §T1.6 (Track A implements those signatures; do
not redesign them). Only the **metrics-targets half** waits on Track B's T0.2
taxonomy lock. Materialize the tool half now.

## Not blocked on Track A: the stub strategy

All Phase-3 code develops against the `tools.py` _interface_, not Track A's
implementation. Build `src/cobol_archaeologist/agent/stub_tools.py`: a
`StubToolLayer` returning canned, schema-valid responses from fixtures
(`tests/fixtures/stub_tools/`). The agent loop takes the tool layer as a
constructor argument; swapping stub→real at the Week-7 seam test must be a
one-line change.

---

## T0.3 — Freeze DriftInstance schema **[code]**

Pydantic v2 models: `RegulationClause` with `doc`, `clause_id`, `version`,
`effective_date`, `text`, and `current_value{kind, value}`,
`CodeLocus{programs, paragraphs, line_span, slice_vars, is_interprocedural}`,
`Labels{program_level, paragraph_level, line_level}`,
`Provenance{source: "synthetic"|"real_curated", base_program, mutation}`, and
`DriftInstance` composing them with
`drift_type: Literal["D1_stale_threshold", …, "D7_conformant"]` and
`gold_rationale`. `effective_date` and `version` are **required, not optional**
— the temporal axis is the project's novelty and must be structurally
unavoidable. **Done when:** round-trip test (model → JSON → model) passes on a
fixture instance; the D-class literals await Track B's T0.2 lock before the
freeze is declared (the code can land now).

## T0.4 — CONTRACT.md **[chat → repo doc]** — `docs/CONTRACT.md`

Two sections: (1) **Tool I/O** — the §T1.6 table from the Track A brief,
verbatim, plus the structured-return rule (summaries + pointers, ≤60-line code
caps). (2) **Metrics + targets** — embed the definitions below and set the bar:
suggested **T1 F1 ≥ 0.70 overall**, and the headline: **agent beats dense-RAG by
a clear, CI-backed margin on interprocedural instances**. **Done when:** signed
off in all three track chats (post it; A and B confirm).

Metric definitions (source of truth once this doc lands):

- **T1 Detection** P/R/F1 on a class-balanced set · **T2 Localization**
  Accuracy@k + line-overlap at program/paragraph/line · **T3 Classification**
  Macro-F1 over D1–D7 ·
- **T4 Faithfulness** — cited clause correct AND cited code fact matches
  `gold_rationale`; **reported per verification tier** (see T3.4) · **T5
  Migration** (optional) behavioral pass rate · **T6 Versioned judgment** — same
  code, two clause versions, different correct answers; paired accuracy. All
  metrics stratified by `is_interprocedural` and `drift_type`; headline
  comparisons carry bootstrap CIs + a paired significance test.

## T0.6 — Lit review + novelty sentence **[chat]**

Verify the open cell (COBOL × financial regulation × temporal drift) against,
minimum: GDPR-Bench-Android, CompliBench, XMainframe/MainframeBench,
COBOL-Coder, CardDemo MCP work, plus a fresh search for anything newer
(reg-compliance benchmarks, legacy-code agents, temporal code reasoning).
Deliverable: `docs/T0.6-related-work.md` — table (work | what it does | why it
doesn't cover our cell) + **one-sentence novelty claim**. Use live web search;
do not rely on memory for prior-art claims. **Done when:** claim drafted and it
survives the table.

---

## T3.1 — Structure-aware chunking **[code]**

Chunk regulation documents on their hierarchy (chapter → section → clause), each
chunk carrying `heading_path`, `clause_id`, `version`, `effective_date` as
metadata. Input: Track B's `data/regulations/clauses.jsonl` + source PDFs.
**Done when:** chunks align to clause boundaries on the anchor doc (fixture test
with 10 hand-checked boundaries).

## T3.2 — Hybrid retrieval + reranker **[code]**

Dense embeddings + BM25 with reciprocal-rank fusion; cross-encoder reranker on
top-20 → top-5. Offline-capable embedder (deployment target is air-gapped banks
— no cloud-only components in the retrieval path). **Done when:** top-k
relevance beats dense-only on a ≥20-query eval set (queries written while doing
T2.1 review; commit as `tests/fixtures/retrieval_queries.jsonl`).

## T3.3 — HyDE **[code]** — `rag/`, `model/prompt.py`

Generate a short NL description of the code slice ("what rule does this
implement?"), retrieve on that instead of raw variable names. **Done when:**
measurable retrieval gain vs raw-query on the same eval set.

## T3.4 — Entailment verification + tiers **[code]** — `model/verify.py`

`verify(finding) -> Verification{tier, evidence, passed}` with tiers: **1**
behaviorally executed via `run_cobol` · **2** statically confirmed (AST/dataflow
fact matches claim) · **3** entailment-only (NLI: clause ⊨ claim). Requirements:
the NLI verifier is a **different model family** than the system under test; its
own accuracy is **human-validated on ≥50 labeled pairs** and reported; every
finding records its tier (CICS code will mostly cap at Tier 2 — that's expected
and must be visible, not hidden). **Done when:** rejects a planted unsupported
citation; tier recorded per finding; verifier accuracy measured.

## T3.5 — ReAct agent loop **[code]** — `agent/loop.py`

think → tool call → observe, against the tool-layer interface (stub first, real
at the seam test). Budgeted (max tool calls per finding, logged trajectory),
structured scratchpad, **abstention** ("insufficient evidence") as a first-class
terminal state. **Done when:** on stub fixtures, answers "where is the late-fee
rule and what clause does it implement?" with correct citations and a clean
trajectory log.

## T3.6 — Drift-detection policy **[code]** — `model/prompt.py`, `agent/`

Given a clause record, hunt the codebase and classify per D1–D7, emitting a
`DriftInstance`-shaped finding + confidence + verification tier, or abstain.
**Done when:** a finding validates against `schemas.DriftInstance` and passes
T3.4 verification on a stub case.

## Standing rules

1. The tool contract is Track A's to implement, this track's to consume —
   mismatches are a **CONTRACT CHANGE — affects Tracks A/B/C**, never a local
   workaround.
2. Any judge/verifier model must be a different family than the system under
   test; record family + version in every run log.
3. Retrieval and verification components must run offline (local embedder, local
   NLI) — this is a deployment requirement (T7.2), cheaper to honor now than
   retrofit.
4. Log every agent trajectory (tool calls, tokens, outcome) from day one — T4.3
   trajectory eval consumes them.
