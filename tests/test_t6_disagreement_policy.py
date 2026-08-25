from __future__ import annotations

from cobol_archaeologist.benchmark.t6_review import (
    ReviewResponse,
    review_disagreement_dimensions,
)


def _response(
    *,
    decision: str = "include",
    drift_type: str = "D2_missing_rule",
    lines: tuple[int, ...] = (10,),
) -> ReviewResponse:
    return ReviewResponse.model_validate(
        {
            "decision": decision,
            "drift_type": drift_type,
            "line_level": [
                {
                    "program": "SAMPLE",
                    "line": line,
                    "source_alias": "src-0123456789ab",
                }
                for line in lines
            ],
            "rationale": "Test-only response.",
            "uncertainty_notes": None,
        }
    )


def test_decision_and_drift_disagreements_require_adjudication() -> None:
    primary = _response()
    verifier = _response(decision="needs_adjudication", drift_type="D3_contradictory")

    assert review_disagreement_dimensions(primary, verifier) == (
        "decision",
        "drift_type",
    )


def test_exact_citation_coordinate_difference_requires_adjudication() -> None:
    assert review_disagreement_dimensions(_response(lines=(10,)), _response(lines=(11,))) == (
        "line_level",
    )


def test_citation_order_alone_is_not_a_disagreement() -> None:
    assert review_disagreement_dimensions(
        _response(lines=(10, 11)), _response(lines=(11, 10))
    ) == ()
