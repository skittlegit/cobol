import json
from pathlib import Path

from cobol_archaeologist.rag.chunker import (
    BOUNDARY_REPORT,
    build_all_chunks,
    load_clause_records,
    main,
    _content_overlap,
)


def test_gate_a_clause_records_reconcile_to_exactly_one_chunk():
    chunks = build_all_chunks()
    for record in load_clause_records():
        clause = record["clause"]
        matches = [
            chunk
            for chunk in chunks
            if chunk.doc == clause["doc"] and chunk.clause_id == clause["clause_id"]
        ]
        assert len(matches) == 1, record["record_id"]
        assert _content_overlap(clause["text"], matches[0].text) >= 0.8, record["record_id"]


def test_bl13_nested_definition_groups_do_not_reuse_curated_clause_ids():
    chunks = build_all_chunks()
    ovd = next(
        record
        for record in load_clause_records()
        if record["record_id"] == "KYC-ovd-list"
    )["clause"]
    regulated_entities = next(
        chunk
        for chunk in chunks
        if chunk.doc == ovd["doc"]
        and chunk.page_start >= 10
        and "Regulated Entities (REs)" in chunk.text.splitlines()[0]
    )

    assert regulated_entities.clause_id != ovd["clause_id"]
    assert regulated_entities.clause_id is not None
    assert "(2)" in regulated_entities.clause_id


def test_gate_b_anchor_boundary_report_contains_promoted_golden_boundaries():
    main()
    promoted = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "chunks"
        / "anchor-boundaries-golden.json"
    )
    report = json.loads(BOUNDARY_REPORT.read_text(encoding="utf-8"))
    for boundary in json.loads(promoted.read_text(encoding="utf-8")):
        assert boundary in report, boundary["clause_id"]


def test_gate_c_chunk_output_is_deterministic():
    first = [chunk.model_dump(mode="json") for chunk in build_all_chunks()]
    second = [chunk.model_dump(mode="json") for chunk in build_all_chunks()]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
