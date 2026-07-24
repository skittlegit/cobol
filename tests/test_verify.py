"""T3.4 gates — tiered finding verification.

Gate 1  each fixture verifies at its expected tier; tier_attempts records the
        full ladder, including `unavailable` Tier-1 attempts.
Gate 2  the planted unsupported citation is rejected (citation_ok=False).
Gate 3  tier ordering: a Tier-2-verifiable finding does not report Tier 3; a
        Tier-1-unavailable finding falls through to Tier 2, not Tier 3.
Gate 4  D6 uses forest_roots + reachable_from; entry_points/callers is NOT the
        deadness oracle (a fall-through-reached paragraph with no caller is live).
Gate 5  family separation: the Tier-3 model family differs from the SUT family.
Gate 6  offline determinism: Tier-3/citation verdicts come from the committed
        nli_cache.jsonl (CachedEntailer require_cache), reproducibly.

All offline except the single true-execution Tier-1 test (needs `cobc`). The
tier gates assert ladder mechanics + citation gating; the neural entailer's
verdict quality is the (human-labelled, xfail) accuracy report's job.
"""

import os
import shutil
from pathlib import Path

import pytest

from cobol_archaeologist.model import verify as V
from cobol_archaeologist.model.verify import (
    CachedEntailer,
    Finding,
    LexicalEntailer,
    NLI_CACHE,
    VerificationResult,
    VerificationTier,
    verify,
)
from cobol_archaeologist.tools import RealToolLayer

REPO_ROOT = Path(__file__).resolve().parents[1]
FIX = REPO_ROOT / "tests" / "fixtures" / "verify"
CORPUS = FIX / "corpus"

_HAVE_COBC = bool(os.environ.get("COBC") or shutil.which("cobc"))
needs_cobc = pytest.mark.skipif(not _HAVE_COBC, reason="cobc not found (run scripts/setup_cobc.sh)")


@pytest.fixture(scope="module")
def tools() -> RealToolLayer:
    return RealToolLayer(corpus_root=CORPUS, copybook_paths=[])


@pytest.fixture(scope="module")
def offline_entailer() -> CachedEntailer:
    # The shipping offline path: cache-backed, no inner model, miss -> error.
    return CachedEntailer(cache_path=NLI_CACHE, require_cache=True)


def load(name: str) -> Finding:
    return Finding.model_validate_json((FIX / f"{name}.json").read_text(encoding="utf-8"))


def outcomes(result: VerificationResult) -> list[tuple[str, str]]:
    return [(a.tier.name, a.outcome) for a in result.tier_attempts]


# --- Gate 1: each fixture verifies at its expected tier ------------------------


@needs_cobc
def test_tier1_executed(tools, offline_entailer):
    r = verify(load("supported_tier1"), tools, entailer=offline_entailer)
    assert r.verified and r.tier == VerificationTier.EXECUTED
    assert r.citation_ok
    # ladder starts at Tier 1 and stops on success.
    assert outcomes(r) == [("EXECUTED", "verified")]


def test_tier2_static_on_noncompiling_cics(tools, offline_entailer):
    r = verify(load("supported_tier2"), tools, entailer=offline_entailer)
    assert r.verified and r.tier == VerificationTier.STATIC
    assert r.citation_ok
    # Tier 1 was TRIED and unavailable (CICS won't compile / no backing), then Tier 2.
    assert outcomes(r) == [("EXECUTED", "unavailable"), ("STATIC", "verified")]


def test_tier3_entailment_only(tools, offline_entailer):
    r = verify(load("supported_tier3"), tools, entailer=offline_entailer)
    assert r.verified and r.tier == VerificationTier.ENTAILMENT
    assert outcomes(r) == [
        ("EXECUTED", "unavailable"), ("STATIC", "unavailable"), ("ENTAILMENT", "verified"),
    ]
    # Tier 3 is flagged as the weakest tier on the result.
    assert "weakest tier" in r.evidence


def test_d6_reachability_verifies(tools, offline_entailer):
    r = verify(load("d6_reachability"), tools, entailer=offline_entailer)
    assert r.verified and r.tier == VerificationTier.STATIC
    assert "unreachable" in r.evidence


def test_tier1_attempt_is_recorded_unavailable_not_skipped(tools, offline_entailer):
    # A finding that cannot execute still records a Tier-1 attempt (never omitted).
    for name in ("supported_tier2", "supported_tier3", "unsupported_citation", "d6_reachability"):
        r = verify(load(name), tools, entailer=offline_entailer)
        assert r.tier_attempts[0].tier == VerificationTier.EXECUTED
        assert r.tier_attempts[0].outcome == "unavailable"


# --- Gate 2: citation rejection ------------------------------------------------


def test_unsupported_citation_is_rejected(tools, offline_entailer):
    r = verify(load("unsupported_citation"), tools, entailer=offline_entailer)
    assert r.citation_ok is False
    assert r.verified is False and r.tier is None
    assert r.rejected_reason and "citation rejected" in r.rejected_reason
    # The code fact DID pass at Tier 2 — rejection is independent of tiering.
    assert ("STATIC", "verified") in outcomes(r)
    assert "45" in r.evidence  # the passing code fact is preserved for the trace


# --- Gate 3: tier ordering / no silent downgrade -------------------------------


def test_tier2_verifiable_does_not_report_tier3(tools, offline_entailer):
    r = verify(load("supported_tier2"), tools, entailer=offline_entailer)
    tiers_attempted = {a.tier for a in r.tier_attempts}
    assert VerificationTier.ENTAILMENT not in tiers_attempted  # stopped at Tier 2
    assert r.tier == VerificationTier.STATIC


def test_tier1_unavailable_falls_through_to_tier2_not_tier3(tools, offline_entailer):
    r = verify(load("d6_reachability"), tools, entailer=offline_entailer)
    assert r.tier == VerificationTier.STATIC
    assert VerificationTier.ENTAILMENT not in {a.tier for a in r.tier_attempts}


# --- Gate 4: D6 uses forest_roots + reachable_from, NOT entry_points/callers ---


def test_d6_flags_isolated_forest_root_dead(tools):
    # DEADISO ISO-PARA: forest root, unreachable from MAIN-PARA -> dead.
    attempt = V._tier2_reachability("DEADISO", "ISO-PARA", tools)
    assert attempt.outcome == "verified"
    assert "forest_root=True" in attempt.detail


def test_d6_does_not_flag_fallthrough_reached_paragraph_dead(tools):
    # FALLTHRU NEXT-PARA is reached ONLY by fall-through: it has NO caller, yet is
    # live. A callers/entry_points-based oracle would wrongly call it dead; the
    # reachable_from traversal (which follows edge_kind="fallthrough") does not.
    assert tools.find_callers("FALLTHRU", "NEXT-PARA") == []  # no caller edge
    attempt = V._tier2_reachability("FALLTHRU", "NEXT-PARA", tools)
    assert attempt.outcome == "refuted"  # NOT dead — reachable_from includes it
    assert "reachable" in attempt.detail.lower()


def test_reachability_source_uses_forest_roots_and_reachable_from():
    # Guard: the reachability path is built on the F7-corrected primitives, not
    # entry_points-as-deadness. (Names present in the implementation.)
    import inspect

    src = inspect.getsource(V._tier2_reachability)
    assert "reachable_from" in src and "forest_roots" in src
    assert "entry_points not used as oracle" in src


# --- Gate 5: family separation -------------------------------------------------


def test_tier3_model_family_differs_from_system_under_test():
    assert V.NLI_FAMILY and V.SUT_FAMILY
    assert V.NLI_FAMILY.lower() != V.SUT_FAMILY.lower()
    # the entailer advertises the non-SUT family in its backend id.
    assert V.NLI_FAMILY in V.NeuralEntailer().backend


# --- Gate 6: offline determinism (committed cache) -----------------------------


def test_offline_cache_is_used_and_deterministic(tools):
    e1 = CachedEntailer(cache_path=NLI_CACHE, require_cache=True)
    e2 = CachedEntailer(cache_path=NLI_CACHE, require_cache=True)
    a = verify(load("supported_tier3"), tools, entailer=e1)
    b = verify(load("supported_tier3"), tools, entailer=e2)
    assert a.model_dump() == b.model_dump()


def test_require_cache_raises_on_miss():
    e = CachedEntailer(cache_path=NLI_CACHE, require_cache=True)
    with pytest.raises(KeyError):
        e.entail("a premise never cached", "a hypothesis never cached")


def test_lexical_entailer_matches_committed_cache_directions(offline_entailer):
    # The committed cache was seeded by the lexical proxy; re-deriving the fixture
    # pairs reproduces the same entailment directions (regeneration is stable).
    lex = LexicalEntailer()
    for name in ("supported_tier1", "supported_tier2", "supported_tier3",
                 "unsupported_citation", "d6_reachability"):
        f = load(name)
        clause = f.prediction.regulation_clause
        cached = offline_entailer.entail(clause.text, f.claim)
        fresh = lex.entail(clause.text, f.claim)
        assert cached.entailment == fresh.entailment, name


# --- verifier accuracy report (xfail until human labels; T3.1 Gate B protocol) -

ACCURACY_PAIRS = FIX / "accuracy_pairs.jsonl"


def _load_accuracy_pairs() -> list[dict]:
    import json

    return [json.loads(line) for line in
            ACCURACY_PAIRS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_accuracy_pairs_are_well_formed():
    pairs = _load_accuracy_pairs()
    assert len(pairs) >= 50
    assert all(p["human_label"] is None for p in pairs), "human labels are authored at review, not here"
    kinds = {p["pair_id"].split("_")[1] for p in pairs}
    assert {"pos", "neg", "part"} <= kinds  # deliberate entailed/not/partial mix


@pytest.mark.xfail(reason="pending human labels (Track C chat), per T3.1 Gate B protocol",
                   strict=False)
def test_verifier_accuracy_false_accept_rate(offline_entailer):
    pairs = _load_accuracy_pairs()
    labels = [p["human_label"] for p in pairs]
    assert all(lbl is not None for lbl in labels), "human_label column not yet filled"

    false_accepts = negatives = 0
    for p in pairs:
        verdict = offline_entailer.entail(p["premise"], p["hypothesis"]).entailment
        human_entail = p["human_label"] == "entailed"
        if not human_entail:
            negatives += 1
            if verdict:
                false_accepts += 1
    far = false_accepts / negatives if negatives else 0.0
    assert far <= 0.10, f"false-accept rate {far:.2%} exceeds the 10% bar"


# --- coercion: a bare DriftInstance is accepted --------------------------------


def test_bare_drift_instance_is_coerced(tools):
    # A bare DriftInstance (claim defaults to gold_rationale) is accepted; use the
    # lexical entailer since that ad-hoc claim is not a committed cache pair.
    di = load("supported_tier3").prediction
    r = verify(di, tools, entailer=LexicalEntailer())  # no Finding wrapper
    assert isinstance(r, VerificationResult)
    # no hooks -> Tiers 1&2 unavailable, entailment decides.
    assert r.tier_attempts[0].outcome == "unavailable"
