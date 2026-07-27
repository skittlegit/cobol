"""T5.1 gates for the benchmark annotation protocol."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES = ROOT / "ANNOTATION.md"


def test_annotation_guidelines_cover_frozen_contract_and_adjudication() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")

    required_sections = {
        "Annotation unit",
        "Evidence hierarchy",
        "D1 — Stale threshold or value",
        "D2 — Missing rule",
        "D3 — Contradictory behavior",
        "D4 — Stale reference data",
        "D5 — Boundary error",
        "D6 — Dead compliance code",
        "D7 — Conformant",
        "Locus and label conventions",
        "Versioned-judgment pairs",
        "Independent annotation",
        "Adjudication",
        "Agreement reporting",
        "Anti-gaming",
    }
    assert required_sections <= {
        line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")
    }

    for contract_term in (
        "target_path",
        "is_interprocedural",
        "insertion-point",
        "defensible-ambiguous",
        "Cohen's κ",
        "Krippendorff's α",
        "literal_roundness",
        "provenance",
        "gold_rationale",
    ):
        assert contract_term in text


def test_annotation_guidelines_do_not_expose_gold_to_systems() -> None:
    text = GUIDELINES.read_text(encoding="utf-8").lower()

    assert "never system input" in text
    assert "mutation metadata" in text
    assert "annotator notes" in text
