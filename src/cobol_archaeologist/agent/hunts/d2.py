"""D2 missing-rule hunt."""

from typing import ClassVar

from cobol_archaeologist.agent.policy import (
    BasePolicyHunt,
    observations,
    require_tools,
)


class D2Hunt(BasePolicyHunt):
    drift_type = "D2_missing_rule"
    required: ClassVar[set[str]] = {
        "grep",
        "find_callers",
        "find_callees",
        "slice_on",
    }

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, self.required)
        checks = {
            "grep": lambda value: isinstance(value, dict) and not value.get("matches"),
            "find_callers": lambda value: value == [],
            "find_callees": lambda value: value == [],
            "slice_on": lambda value: (
                isinstance(value, dict) and not value.get("statements")
            ),
        }
        for tool, is_negative in checks.items():
            values = observations(transcript, tool)
            if not values:
                errors.append(f"{tool} returned no usable absence evidence")
            elif not all(is_negative(value) for value in values):
                errors.append(f"{tool} did not provide negative absence evidence")
        prediction = response.prediction
        if prediction is not None and not prediction.labels.line_level:
            errors.append("D2 requires typed insertion-point line labels")
        return errors
