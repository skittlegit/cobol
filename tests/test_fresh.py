"""The fresh held-out test split and the hosts it was generated from."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from cobol_archaeologist.benchmark.fresh import FRESH, LOCAL_HOSTS, hosts
from cobol_archaeologist.benchmark.splits import _base_group
from cobol_archaeologist.schemas import DriftInstance

BENCHMARK = Path(__file__).resolve().parents[1] / "data" / "benchmark"


def _split(name: str) -> list[DriftInstance]:
    return [
        DriftInstance.model_validate_json(line)
        for line in (BENCHMARK / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_hosts_cover_each_interprocedural_operator():
    ops = Counter(host.ops[0] for host in hosts() if host not in LOCAL_HOSTS)

    assert ops == {"MO-1×": 20, "MO-3×": 20, "MO-6×": 20}
    assert all((FRESH / host.filename).is_file() for host in hosts())


def test_test_split_uses_only_held_out_bases_and_no_shared_group():
    test = _split("test")
    held_out = {path.name for path in (BENCHMARK / "seed" / "programs" / "heldout").iterdir()}
    used = {_base_group(row) for row in _split("train") + _split("dev")}

    assert len(test) == 95
    cross = [row for row in test if row.code_locus.is_interprocedural]
    assert len(cross) >= 70
    assert sum(row.drift_type == "D7_conformant" for row in cross) >= 30
    assert all(row.provenance.base_program in held_out for row in test)
    assert not {_base_group(row) for row in test} & used


def test_temporal_pairs_share_source_and_have_opposite_verdicts():
    import json

    from cobol_archaeologist.eval.runner import materialize_row

    rows = {
        row.instance_id: row
        for row in (
            DriftInstance.model_validate_json(line)
            for line in (BENCHMARK / "temporal" / "rows.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    pairs = json.loads((BENCHMARK / "temporal" / "pairs.json").read_text())

    assert len(pairs) >= 20
    for pair in pairs.values():
        old, new = (rows[member] for member in pair["members"])
        assert materialize_row(old, "temporal").source_sha256 == (
            materialize_row(new, "temporal").source_sha256
        )
        assert old.regulation_clause.version != new.regulation_clause.version
        assert {old.drift_type, new.drift_type} == {"D7_conformant", "D1_stale_threshold"}
