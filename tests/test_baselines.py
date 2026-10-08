"""The rag_reranker baseline is told the same response shape as the detector."""

from __future__ import annotations

from cobol_archaeologist.eval.baselines import build_prompt
from cobol_archaeologist.schemas import DriftPrediction


def test_baseline_prompt_states_the_conformant_label_shape():
    # DriftPrediction rejects a D7 answer with drift labels or cited lines, so
    # a baseline that is not told this loses correct conformant answers.
    prompt = " ".join(build_prompt([]).split())

    assert "D7_conformant, set labels.program_level and labels.paragraph_level to conformant" in prompt
    assert "labels.line_level to an empty list" in prompt
    assert "For every other class, set labels.program_level to drift" in prompt
    assert DriftPrediction.model_fields["labels"]
