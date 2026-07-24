"""Build the committed T3.4 NLI cache (`tests/fixtures/verify/nli_cache.jsonl`).

Collects every (premise, hypothesis) pair the verifier suite needs — the cited
clause vs claim for each Finding fixture, plus the verifier-accuracy pairs — and
writes their entailment verdicts so the offline suite is deterministic
(``CachedEntailer(require_cache=True)``), mirroring the T3.1 fixture protocol.

Backends:
  (default)   LexicalEntailer  — transparent token-coverage proxy; runs offline.
  --neural    NeuralEntailer   — the pinned DeBERTa NLI model (network); the
                                 verdicts of record for the accuracy report.

Each row is tagged with its backend, so a lexical-proxy-seeded cache is never
mistaken for a neural verdict. Re-run with --neural at review to replace them.

Usage:
    python scripts/build_verify_nli_cache.py [--neural]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cobol_archaeologist.model.verify import (
    NLI_CACHE,
    Finding,
    LexicalEntailer,
    NeuralEntailer,
    _cache_key,
)

FIX = ROOT / "tests" / "fixtures" / "verify"
FIXTURES = [
    "supported_tier1", "supported_tier2", "supported_tier3",
    "unsupported_citation", "d6_reachability",
]
ACCURACY_PAIRS = FIX / "accuracy_pairs.jsonl"


def collect_pairs() -> list[tuple[str, str, str]]:
    """(premise, hypothesis, source) pairs, de-duplicated by verify key."""
    pairs: dict[str, tuple[str, str, str]] = {}
    for name in FIXTURES:
        fnd = Finding.model_validate_json((FIX / f"{name}.json").read_text(encoding="utf-8"))
        clause = fnd.prediction.regulation_clause
        key = _cache_key(clause.text, fnd.claim)
        pairs[key] = (clause.text, fnd.claim, f"fixture:{name}")
    if ACCURACY_PAIRS.exists():
        for line in ACCURACY_PAIRS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = _cache_key(row["premise"], row["hypothesis"])
            pairs[key] = (row["premise"], row["hypothesis"], f"accuracy:{row['pair_id']}")
    return [(*v,) for v in pairs.values()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--neural", action="store_true", help="use the pinned NLI model (network)")
    args = ap.parse_args()

    entailer = NeuralEntailer() if args.neural else LexicalEntailer()
    rows = []
    for premise, hypothesis, source in collect_pairs():
        res = entailer.entail(premise, hypothesis)
        rows.append({
            "key": _cache_key(premise, hypothesis),
            "entailment": res.entailment,
            "score": res.score,
            "backend": res.backend,
            "source": source,
            "premise_preview": premise[:80],
            "hypothesis_preview": hypothesis[:80],
        })
    rows.sort(key=lambda r: r["source"])
    NLI_CACHE.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} cache rows to {NLI_CACHE} (backend={entailer.backend})")


if __name__ == "__main__":
    main()
