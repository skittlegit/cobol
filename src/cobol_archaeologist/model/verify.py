"""Tiered finding verification (Track C, T3.4).

``verify(finding, tools) -> VerificationResult`` decides whether a drift finding
is *backed by evidence* and, if so, at what strength. It attempts evidence in a
fixed tier order and records the tier that succeeded:

    Tier 1 EXECUTED    — behaviourally reproduced via GnuCOBOL (``run_cobol``)
    Tier 2 STATIC      — an AST/dataflow/slice/reachability fact matches the claim
    Tier 3 ENTAILMENT  — the retrieved clause entails the claim (NLI only)

Two properties make this load-bearing for the T4 headline (CONTRACT Part 3,
"faithfulness reported per tier"):

- **No silent tier downgrade.** ``tier_attempts`` records *every* tier tried in
  order, so a consumer can tell a Tier-1 attempt that was *tried and unavailable*
  (CICS code that will not compile) from one never attempted. T4.4 calibration
  depends on that distinction.
- **Citation rejection is independent of tiering.** A correct code fact attached
  to the *wrong* clause is the "plausible but wrong" failure the entailment check
  exists to stop: if the cited clause does not entail the claim,
  ``citation_ok=False`` and the finding is rejected *even when a tier passed*.

DECISION (finding shape): CONTRACT Part 3 says system findings are emitted
``DriftInstance``-shaped, but a ``DriftInstance`` carries the regulation value and
locus, not the concrete *evidence hooks* a verifier checks (execution probe,
the specific literal/comparator asserted, the paragraph claimed dead). Rather
than widen the frozen ``schemas.py`` (a CONTRACT CHANGE), :class:`Finding` wraps
the ``DriftInstance`` prediction and adds verifier-only hooks. A bare
``DriftInstance`` is accepted too and coerced with empty hooks — its Tier-1 and
Tier-2 attempts then record ``unavailable`` (not ``refuted``) and the ladder
falls through to entailment, which is exactly the recorded behaviour the work
order wants.

DECISION (Tier-3 backend / offline determinism): the production entailer is a
pinned NLI cross-encoder (:data:`NLI_MODEL`, family :data:`NLI_FAMILY` —
deliberately *not* the Claude family under test, per the CONTRACT integrity
rule). Neural NLI on long deontic text is exactly what the accuracy report
validates, so its verdicts are cached to a committed
``tests/fixtures/verify/nli_cache.jsonl`` and the offline suite reads the cache
(same pattern as the T3.1 embedding fixtures / planned T3.3b HyDE cache). Where
the neural weights are unavailable, :class:`LexicalEntailer` is a *transparent,
deterministic* token-coverage proxy — never disguised as a neural verdict; the
committed cache tags its backend, and ``scripts/build_verify_nli_cache.py``
regenerates it from the real model. The tier gates test *ladder mechanics and
citation gating*; the neural verdicts' quality is what the (human-labelled,
xfail) accuracy report measures.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import IntEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.model.run_cobol import compile_check, run_cobol
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.schemas import DriftInstance
from cobol_archaeologist.static_analysis.call_graph import build_call_graph
from cobol_archaeologist.tool_types import RunInputs

ROOT = Path(__file__).resolve().parents[3]
NLI_CACHE = ROOT / "tests" / "fixtures" / "verify" / "nli_cache.jsonl"

# --- Tier-3 model pin + family separation (CONTRACT integrity rule) ------------
# The verifier must be a different model family than the system under test. The
# agent under evaluation is Claude (Anthropic); the Tier-3 entailer is a DeBERTa
# NLI cross-encoder. Gate 5 asserts NLI_FAMILY != SUT_FAMILY.
NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
NLI_REVISION = "main"
NLI_FAMILY = "deberta"
NLI_PROVIDER = "huggingface"
SUT_FAMILY = "anthropic"  # the system under test (Claude), per CONTRACT integrity rule

# Entailment decision threshold on P(entailment).
ENTAIL_THRESHOLD = 0.5


# --------------------------------------------------------------------------
# Result + attempt models
# --------------------------------------------------------------------------


class VerificationTier(IntEnum):
    EXECUTED = 1     # behaviourally executed via run_cobol
    STATIC = 2       # AST/dataflow/slice/reachability fact matches the claim
    ENTAILMENT = 3   # retrieved clause entails the claim (NLI); weakest tier


class TierOutcome:
    VERIFIED = "verified"
    REFUTED = "refuted"
    UNAVAILABLE = "unavailable"


class TierAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: VerificationTier
    outcome: str  # verified | refuted | unavailable
    detail: str   # what was checked / why unavailable — quotable in a trace


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool
    tier: VerificationTier | None       # None iff verified is False
    evidence: str                       # what was checked, quotable in a trace
    citation_ok: bool                   # did the cited clause survive checking
    rejected_reason: str | None = None
    tier_attempts: list[TierAttempt]    # every tier tried, in order, w/ outcome


# --------------------------------------------------------------------------
# Finding input (prediction + verifier-only evidence hooks)
# --------------------------------------------------------------------------


class ExecProbe(BaseModel):
    """A Tier-1 execution probe: feed ``stdin`` to the compiled locus program and
    require ``expect_substring`` in stdout for the claim to hold."""

    model_config = ConfigDict(extra="forbid")

    stdin: str = ""
    expect_substring: str
    description: str = ""


class StaticClaim(BaseModel):
    """A Tier-2 static assertion about the locus, checked against tool facts.

    Any subset may be given; the attempt verifies iff *all* provided sub-claims
    hold. ``dead_paragraph`` routes to call-graph reachability (D6)."""

    model_config = ConfigDict(extra="forbid")

    literal: str | None = None         # must appear in the locus paragraph code
    comparator: str | None = None      # comparator token expected in the locus code
    dead_paragraph: str | None = None  # D6: must be unreachable from the true entry


class Finding(BaseModel):
    """A verifiable finding: the ``DriftInstance``-shaped prediction plus the
    concrete evidence hooks the verifier checks. Missing hooks make a tier
    ``unavailable`` (not ``refuted``)."""

    model_config = ConfigDict(extra="forbid")

    prediction: DriftInstance
    claim: str                          # NL proposition for entailment + citation
    exec_probe: ExecProbe | None = None
    static_claim: StaticClaim | None = None

    @classmethod
    def from_prediction(
        cls, prediction: DriftInstance, claim: str | None = None
    ) -> Finding:
        return cls(prediction=prediction, claim=claim or prediction.gold_rationale)


def _coerce(finding: Finding | DriftInstance) -> Finding:
    if isinstance(finding, Finding):
        return finding
    if isinstance(finding, DriftInstance):
        return Finding.from_prediction(finding)
    raise TypeError(
        f"verify() expects Finding or DriftInstance, got {type(finding).__name__}"
    )


# --------------------------------------------------------------------------
# Entailment backends (Tier 3 + citation)
# --------------------------------------------------------------------------


class EntailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entailment: bool
    score: float          # P(premise entails hypothesis) in [0, 1]
    backend: str


class Entailer(Protocol):
    def entail(self, premise: str, hypothesis: str) -> EntailResult: ...


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and any are as at be by for from has have if in into is it its may must "
    "no not of on or shall so than that the their them then there these this to was "
    "were which who will with within without per".split()
)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1}


class LexicalEntailer:
    """Transparent, deterministic token-coverage proxy for entailment.

    Not a neural model and never presented as one: entailment holds iff the
    hypothesis's content tokens are sufficiently covered by the premise's. Used
    offline where the neural weights are unavailable and to seed the committed
    cache (tagged as such)."""

    backend = "lexical_proxy_v1"

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold

    def entail(self, premise: str, hypothesis: str) -> EntailResult:
        h = _content_tokens(hypothesis)
        if not h:
            return EntailResult(entailment=False, score=0.0, backend=self.backend)
        coverage = len(h & _content_tokens(premise)) / len(h)
        return EntailResult(
            entailment=coverage >= self.threshold,
            score=round(coverage, 4),
            backend=self.backend,
        )


class NeuralEntailer:
    """Pinned DeBERTa NLI cross-encoder (network). Lazy: weights load on first
    call, so constructing the entailer offline is free."""

    backend = f"{NLI_FAMILY}:{NLI_MODEL}"

    def __init__(self, model: str = NLI_MODEL, revision: str = NLI_REVISION) -> None:
        self.model = model
        self.revision = revision
        self._pipe = None

    def _ensure(self):
        if self._pipe is None:
            from transformers import pipeline  # network / heavy import

            self._pipe = pipeline(
                "text-classification", model=self.model, revision=self.revision,
                top_k=None,
            )
        return self._pipe

    def entail(self, premise: str, hypothesis: str) -> EntailResult:
        pipe = self._ensure()
        scores = pipe({"text": premise, "text_pair": hypothesis})
        prob = next(
            (s["score"] for s in scores if s["label"].lower() == "entailment"), 0.0
        )
        return EntailResult(
            entailment=prob >= ENTAIL_THRESHOLD,
            score=round(float(prob), 4),
            backend=self.backend,
        )


def _cache_key(premise: str, hypothesis: str) -> str:
    return hashlib.sha1(f"{premise}␟{hypothesis}".encode("utf-8")).hexdigest()


class CachedEntailer:
    """Cache in front of an inner entailer, keyed by (premise, hypothesis).

    ``require_cache`` (offline mode) turns a miss into an error instead of
    invoking the inner model, so the review suite is deterministic and can never
    silently fall back to a live call."""

    def __init__(
        self,
        inner: Entailer | None = None,
        cache_path: Path = NLI_CACHE,
        require_cache: bool = False,
    ) -> None:
        self.inner = inner
        self.cache_path = Path(cache_path)
        self.require_cache = require_cache
        self._cache: dict[str, EntailResult] = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                self._cache[row["key"]] = EntailResult(
                    entailment=row["entailment"],
                    score=row["score"],
                    backend=row["backend"],
                )

    def entail(self, premise: str, hypothesis: str) -> EntailResult:
        key = _cache_key(premise, hypothesis)
        if key in self._cache:
            return self._cache[key]
        if self.require_cache:
            raise KeyError(
                f"NLI cache miss for key {key[:12]} (offline require_cache=True); "
                "regenerate via scripts/build_verify_nli_cache.py"
            )
        if self.inner is None:
            raise RuntimeError("CachedEntailer has no inner entailer for a cache miss")
        result = self.inner.entail(premise, hypothesis)
        self._cache[key] = result
        return result


def default_entailer() -> Entailer:
    """Production entailer: neural NLI behind the committed cache."""
    return CachedEntailer(inner=NeuralEntailer())


# --------------------------------------------------------------------------
# Tier attempts
# --------------------------------------------------------------------------


def _program_source(program: str, tools) -> str | None:
    """Original source text of ``program`` via the ToolLayer's path pointer."""
    try:
        view = tools.read_program(program)
    except Exception:
        return None
    path = Path(view.path)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _tier1_executed(finding: Finding, tools) -> TierAttempt:
    T = VerificationTier.EXECUTED
    probe = finding.exec_probe
    if probe is None:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail="no execution probe; Tier-1 not applicable to this finding",
        )
    program = finding.prediction.code_locus.loci[0].program
    source = _program_source(program, tools)
    if source is None:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"source for {program!r} unavailable to the tool layer",
        )
    try:
        comp = compile_check(source)
    except RuntimeError as exc:
        # DECISION: a missing `cobc` is a broken execution backing, not a fact
        # about the code — for run_cobol itself that raises (CLAUDE.md rule 3),
        # but the verifier is a tiering consumer, so absent Tier-1 backing is
        # recorded as `unavailable` and the ladder degrades to Tier 2/3.
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"Tier-1 execution backing unavailable ({exc})",
        )
    if not comp.ok:
        msg = "; ".join(comp.messages[:2]) if comp.messages else "compile failed"
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"{program} does not compile (Tier-1 unavailable, expected for CICS): {msg}",
        )
    result = run_cobol(source, RunInputs(stdin=probe.stdin))
    if not result.compiled_ok:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"{program} failed to compile under run harness (Tier-1 unavailable)",
        )
    out = result.stdout.strip()
    if probe.expect_substring in result.stdout:
        return TierAttempt(
            tier=T, outcome=TierOutcome.VERIFIED,
            detail=f"ran {program}; observed {probe.expect_substring!r} in output ({out!r})",
        )
    return TierAttempt(
        tier=T, outcome=TierOutcome.REFUTED,
        detail=f"ran {program}; expected {probe.expect_substring!r} absent from output ({out!r})",
    )


def _build_program_graph(program: str, tools):
    source = _program_source(program, tools)
    if source is None:
        return None
    # Parse from the ToolLayer's path so line/paragraph identity matches the tool.
    path = Path(tools.read_program(program).path)
    prog = parse_program(path, include_preamble=True)
    pres = {prog.program_id: preprocess(source)}
    return prog, build_call_graph([prog], pres)


def _tier2_reachability(program: str, dead_para: str, tools) -> TierAttempt:
    """D6: verify ``dead_para`` is unreachable from the program's true entry.

    Per Track A's 2026-07-17 flag, this consumes ``forest_roots`` + ``reachable_from``
    (which traverses ``edge_kind="fallthrough"``) and MUST NOT treat ``entry_points``
    or ``callers`` as the deadness oracle — a fall-through-reached paragraph has no
    caller yet is live."""
    T = VerificationTier.STATIC
    built = _build_program_graph(program, tools)
    if built is None:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"cannot build call graph for {program!r}",
        )
    prog, graph = built
    pid = prog.program_id
    want = dead_para.upper()
    entries = graph.entry_points(pid)             # the true entry: reachability SEED only
    reached = graph.reachable_from(entries)       # traverses fallthrough edges
    roots = {n.paragraph.upper() for n in graph.forest_roots(pid)}
    reached_names = {n.paragraph.upper() for n in reached}
    entry_names = [n.paragraph for n in entries]
    if want in reached_names:
        return TierAttempt(
            tier=T, outcome=TierOutcome.REFUTED,
            detail=f"{dead_para} IS reachable from entry {entry_names} "
                   f"(reachable_from traverses fallthrough); not dead",
        )
    is_root = want in roots
    return TierAttempt(
        tier=T, outcome=TierOutcome.VERIFIED,
        detail=f"{dead_para} unreachable from entry {entry_names}; forest_root={is_root} "
               f"(forest_roots + reachable_from; entry_points not used as oracle)",
    )


def _tier2_static(finding: Finding, tools) -> TierAttempt:
    T = VerificationTier.STATIC
    sc = finding.static_claim
    if sc is None:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail="no static claim; Tier-2 not applicable to this finding",
        )
    locus = finding.prediction.code_locus.loci[0]
    if sc.dead_paragraph is not None:
        return _tier2_reachability(locus.program, sc.dead_paragraph, tools)

    if locus.paragraph is None:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail="locus has no paragraph; literal/comparator check needs one",
        )
    try:
        code = tools.read_paragraph(locus.program, locus.paragraph).code
    except Exception as exc:  # unknown program/paragraph
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail=f"locus {locus.program}:{locus.paragraph} not readable ({exc})",
        )

    checks: list[str] = []
    if sc.literal is not None:
        if sc.literal not in code:
            return TierAttempt(
                tier=T, outcome=TierOutcome.REFUTED,
                detail=f"claimed literal {sc.literal!r} absent from {locus.program}:{locus.paragraph}",
            )
        checks.append(f"literal {sc.literal!r} present")
    if sc.comparator is not None:
        if sc.comparator not in code:
            return TierAttempt(
                tier=T, outcome=TierOutcome.REFUTED,
                detail=f"claimed comparator {sc.comparator!r} absent from {locus.program}:{locus.paragraph}",
            )
        checks.append(f"comparator {sc.comparator!r} present")
    if not checks:
        return TierAttempt(
            tier=T, outcome=TierOutcome.UNAVAILABLE,
            detail="static claim carried no checkable literal/comparator/dead_paragraph",
        )
    return TierAttempt(
        tier=T, outcome=TierOutcome.VERIFIED,
        detail=f"{locus.program}:{locus.paragraph} — " + "; ".join(checks),
    )


def _tier3_entailment(finding: Finding, entailer: Entailer) -> TierAttempt:
    T = VerificationTier.ENTAILMENT
    clause = finding.prediction.regulation_clause
    res = entailer.entail(clause.text, finding.claim)
    if res.entailment:
        return TierAttempt(
            tier=T, outcome=TierOutcome.VERIFIED,
            detail=f"clause {clause.doc} {clause.clause_id} entails the claim "
                   f"(P={res.score}, {res.backend}); Tier-3 is entailment-only (weakest tier)",
        )
    return TierAttempt(
        tier=T, outcome=TierOutcome.REFUTED,
        detail=f"clause {clause.doc} {clause.clause_id} does not entail the claim "
               f"(P={res.score}, {res.backend})",
    )


# --------------------------------------------------------------------------
# verify()
# --------------------------------------------------------------------------


def verify(
    finding: Finding | DriftInstance,
    tools,
    *,
    entailer: Entailer | None = None,
) -> VerificationResult:
    """Verify ``finding`` against ``tools`` (a ``ToolLayer``); see module docstring.

    ``entailer`` overrides the Tier-3 / citation backend (tests inject an offline
    one); production uses :func:`default_entailer`."""
    fnd = _coerce(finding)
    clause = fnd.prediction.regulation_clause
    entailer = entailer or default_entailer()

    # --- citation check (independent of tiering) ---
    citation = entailer.entail(clause.text, fnd.claim)
    citation_ok = citation.entailment

    # --- tier ladder: 1 -> 2 -> 3, stop at first success, record every attempt ---
    attempts: list[TierAttempt] = []
    verified_tier: VerificationTier | None = None
    evidence = ""

    a1 = _tier1_executed(fnd, tools)
    attempts.append(a1)
    if a1.outcome == TierOutcome.VERIFIED:
        verified_tier, evidence = VerificationTier.EXECUTED, a1.detail
    else:
        a2 = _tier2_static(fnd, tools)
        attempts.append(a2)
        if a2.outcome == TierOutcome.VERIFIED:
            verified_tier, evidence = VerificationTier.STATIC, a2.detail
        else:
            a3 = _tier3_entailment(fnd, entailer)
            attempts.append(a3)
            if a3.outcome == TierOutcome.VERIFIED:
                verified_tier, evidence = VerificationTier.ENTAILMENT, a3.detail

    # --- combine: a passing tier is necessary; a supported citation is too ---
    if verified_tier is None:
        return VerificationResult(
            verified=False, tier=None,
            evidence="no tier could verify the claim; agent should abstain",
            citation_ok=citation_ok,
            rejected_reason="unverifiable: all three tiers failed",
            tier_attempts=attempts,
        )
    if not citation_ok:
        return VerificationResult(
            verified=False, tier=None,
            evidence=evidence,  # the code fact that DID pass — preserved for the trace
            citation_ok=False,
            rejected_reason=(
                f"citation rejected: cited clause {clause.doc} {clause.clause_id} does not "
                f"entail the claim (P={citation.score}, {citation.backend}) — a correct code "
                f"fact attached to the wrong clause"
            ),
            tier_attempts=attempts,
        )
    return VerificationResult(
        verified=True, tier=verified_tier, evidence=evidence,
        citation_ok=True, rejected_reason=None, tier_attempts=attempts,
    )
