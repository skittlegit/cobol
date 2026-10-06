"""D2 missing-rule hunt."""

from typing import ClassVar

from cobol_archaeologist.agent.policy import (
    BasePolicyHunt,
    require_tools,
)


class D2Hunt(BasePolicyHunt):
    drift_type = "D2_missing_rule"
    required: ClassVar[set[str]] = {
        "grep",
        "slice_on",
    }

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, self.required)
        prediction = response.prediction
        if prediction is not None and not prediction.labels.line_level:
            errors.append("D2 requires typed insertion-point line labels")
        return errors
