"""T2.1 gate: every clause record in data/regulations/clauses.jsonl validates
against the frozen RegulationClause schema, and the curation set meets the
T2.1 work order's done-when bar (>=15 clauses, each pinned to version +
effective_date).

The nested `clause` object is the schema-frozen contract shape; the sibling
`check` object holds T2.1 curation fields (required check, drift classes,
mutation ops, locus, T6 pairing) that are intentionally NOT part of the frozen
schema and are validated structurally here instead.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from cobol_archaeologist.schemas import RegulationClause

CLAUSES = (
    Path(__file__).resolve().parents[1] / "data" / "regulations" / "clauses.jsonl"
)


def load_records() -> list[dict]:
    records = []
    for i, line in enumerate(CLAUSES.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"clauses.jsonl line {i} is not valid JSON: {exc}")
    return records


def test_clauses_file_exists():
    assert CLAUSES.is_file(), f"missing curation deliverable: {CLAUSES}"


def test_gate_minimum_clause_count():
    # Brief done-when: >=15 clauses with version + effective_date.
    assert len(load_records()) >= 15


def test_every_clause_validates_against_frozen_schema():
    for rec in load_records():
        rid = rec.get("record_id", "<no record_id>")
        assert "clause" in rec, f"{rid}: record missing nested 'clause' object"
        try:
            # extra="forbid" on RegulationClause and CurrentValue means this
            # rejects any stray top-level qualifier (e.g. a comparator placed
            # beside {kind, value} instead of inside value) — the exact
            # contract violation that failed the T2.1 gate during curation.
            RegulationClause.model_validate(rec["clause"])
        except ValidationError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"{rid}: clause failed schema validation:\n{exc}")


def test_every_clause_pinned_in_time():
    for rec in load_records():
        clause = rec["clause"]
        rid = rec.get("record_id", "<no record_id>")
        assert clause.get("version"), f"{rid}: clause missing version"
        assert clause.get("effective_date"), f"{rid}: clause missing effective_date"


def test_record_ids_unique():
    ids = [rec.get("record_id") for rec in load_records()]
    assert all(ids), "every record must carry a record_id"
    assert len(ids) == len(set(ids)), "record_id values must be unique"


def test_curation_fields_present():
    for rec in load_records():
        rid = rec.get("record_id", "<no record_id>")
        check = rec.get("check")
        assert isinstance(check, dict), f"{rid}: missing 'check' curation object"
        assert check.get("description"), f"{rid}: check needs a required-check sentence"
        assert isinstance(
            check.get("drift_classes"), list
        ), f"{rid}: check.drift_classes must be a list"


REPEALED_2022_DOC = (
    "RBI Master Direction - Credit Card and Debit Card - "
    "Issuance and Conduct Directions, 2022"
)
CC_2025_DOC = "RBI-Commercial-Banks-CC-DC-Directions-2025"


def test_cc_records_anchored_to_2025_directions():
    # Re-anchored 2026-07-09: the 2022 MD was repealed for commercial banks on
    # 2025-11-28 and reissued as the Commercial Banks Directions 2025. No CC
    # clause may still carry the repealed 2022 document identity.
    for rec in load_records():
        doc = rec["clause"]["doc"]
        assert doc != REPEALED_2022_DOC, f"{rec['record_id']}: still on repealed 2022 MD"
        if rec.get("record_id", "").startswith("CC-"):
            assert doc == CC_2025_DOC, f"{rec['record_id']}: CC record not anchored to 2025 Directions"
            assert rec["clause"]["version"] == "2025-11-28"


def test_kyc_bridge_is_2025_paragraph_90():
    # Regression guard for the re-anchor: the KYC/AML/CFT incorporation bridge is
    # 2025 paragraph 90 (was clause 29 in the repealed 2022 MD, NOT clause 20 --
    # 2025 para 20 is the unused-card closure rule). The 2022 origin is preserved.
    bridges = [r for r in load_records() if r.get("record_id") == "CC-29"]
    assert len(bridges) == 1, "expected exactly one CC-29 bridge record"
    assert bridges[0]["clause"]["clause_id"] == "90"
    assert bridges[0]["check"]["prior_2022"]["clause_id"] == "29"


def test_clause_docs_agree_with_manifest():
    # CLAUDE.md: any doc referencing a regulation must agree with data/manifest.json.
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    known = {
        reg["clause_doc_id"]
        for reg in manifest["regulations"]
        if "clause_doc_id" in reg
    }
    for rec in load_records():
        doc = rec["clause"]["doc"]
        assert doc in known, f"{rec['record_id']}: doc '{doc}' not in manifest clause_doc_id set {known}"
