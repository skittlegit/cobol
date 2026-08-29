from __future__ import annotations

import pytest

from cobol_archaeologist.benchmark.t6_review import (
    ReviewResponse,
    _canonical_replacement_review_lines,
)
from cobol_archaeologist.schemas import CodeLocus, SourceLocus


def _locus() -> CodeLocus:
    return CodeLocus(
        loci=[
            SourceLocus(
                program="DEMO",
                paragraph="1000-MAIN",
                file=None,
                line_span=(9, 20),
            )
        ],
        slice_vars=[],
        is_interprocedural=False,
    )


def _response(*, lines: list[int], source_alias: str = "src-012345abcdef") -> ReviewResponse:
    return ReviewResponse.model_validate(
        {
            "decision": "include",
            "drift_type": "D1_stale_threshold",
            "line_level": [
                {
                    "program": "DEMO",
                    "line": line,
                    "source_alias": source_alias,
                }
                for line in lines
            ],
            "rationale": "The threshold differs.",
            "uncertainty_notes": None,
        }
    )


def test_replacement_promotion_keeps_only_unambiguous_in_locus_citations() -> None:
    refs = _canonical_replacement_review_lines(
        code_locus=_locus(),
        expected_source_alias="src-012345abcdef",
        response=_response(lines=[6, 13, 14]),
    )

    assert [(ref.program, ref.line, ref.file) for ref in refs] == [
        ("DEMO", 13, None),
        ("DEMO", 14, None),
    ]


def test_replacement_promotion_rejects_non_d7_with_only_context_citations() -> None:
    with pytest.raises(ValueError, match="no citation in the frozen code locus"):
        _canonical_replacement_review_lines(
            code_locus=_locus(),
            expected_source_alias="src-012345abcdef",
            response=_response(lines=[6]),
        )


def test_replacement_promotion_rejects_wrong_source_alias() -> None:
    with pytest.raises(ValueError, match="wrong source alias"):
        _canonical_replacement_review_lines(
            code_locus=_locus(),
            expected_source_alias="src-fedcba543210",
            response=_response(lines=[13]),
        )
