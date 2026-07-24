"""Deterministic statistical helpers for M4."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def paired_bootstrap_delta(
    left: Sequence[object],
    right: Sequence[object],
    metric: Callable[[Sequence[object]], float],
    *,
    resamples: int = 10_000,
    seed: int = 4405,
) -> tuple[float, float, float]:
    if len(left) != len(right) or not left:
        raise ValueError("paired bootstrap requires equal non-empty samples")
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(resamples):
        indices = [rng.randrange(len(left)) for _ in left]
        lsample = [left[index] for index in indices]
        rsample = [right[index] for index in indices]
        deltas.append(metric(lsample) - metric(rsample))
    observed = metric(left) - metric(right)
    return observed, percentile(deltas, 0.025), percentile(deltas, 0.975)


def paired_randomization_p(
    left_correct: Sequence[bool],
    right_correct: Sequence[bool],
    *,
    samples: int = 20_000,
    seed: int = 4405,
) -> float:
    if len(left_correct) != len(right_correct) or not left_correct:
        raise ValueError("paired test requires equal non-empty samples")
    diffs = [int(left) - int(right) for left, right in zip(left_correct, right_correct)]
    observed = abs(sum(diffs))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        permuted = sum(diff if rng.random() < 0.5 else -diff for diff in diffs)
        if abs(permuted) >= observed:
            extreme += 1
    return (extreme + 1) / (samples + 1)


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    return sum(
        math.comb(n, index)
        * probability**index
        * (1 - probability) ** (n - index)
        for index in range(k + 1)
    )


def exact_binomial_interval(
    successes: int,
    total: int,
    *,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Clopper-Pearson interval without a scipy runtime dependency."""

    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")
    alpha = 1 - confidence
    if successes == 0:
        lower = 0.0
    else:
        lo, hi = 0.0, successes / total
        for _ in range(80):
            mid = (lo + hi) / 2
            upper_tail = 1 - _binomial_cdf(successes - 1, total, mid)
            if upper_tail < alpha / 2:
                lo = mid
            else:
                hi = mid
        lower = (lo + hi) / 2
    if successes == total:
        upper = 1.0
    else:
        lo, hi = successes / total, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            cdf = _binomial_cdf(successes, total, mid)
            if cdf > alpha / 2:
                lo = mid
            else:
                hi = mid
        upper = (lo + hi) / 2
    return lower, upper
