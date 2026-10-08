"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cobol_archaeologist.benchmark.splits import build_splits

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "benchmark"


@pytest.fixture(scope="session")
def presplit_dir(tmp_path_factory) -> Path:
    """Pre-freeze splits, regenerated from the tracked judged instances."""

    out = tmp_path_factory.mktemp("presplit")
    build_splits(
        BENCHMARK / "drift_instances.plausible.jsonl",
        BENCHMARK / "seed" / "real_curated.jsonl",
        out,
    )
    return out
