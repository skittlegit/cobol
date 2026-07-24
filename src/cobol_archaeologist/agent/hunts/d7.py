"""D7 positive-conformance hunt."""

from cobol_archaeologist.agent.policy import BasePolicyHunt, require_tools
from cobol_archaeologist.schemas import resolve_path

_TOKENS = {
    "strictly_greater": ">",
    "at_least": ">=",
    "strictly_less": "<",
    "at_most": "<=",
    "equal": "=",
    "not_equal": "<>",
}


class D7Hunt(BasePolicyHunt):
    drift_type = "D7_conformant"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, {"read_paragraph"})
        prediction = response.prediction
        if prediction is None:
            return errors
        labels = prediction.labels
        if (
            labels.program_level != "conformant"
            or labels.paragraph_level != "conformant"
            or labels.line_level
        ):
            errors.append("D7 requires conformant labels and no drift line labels")
        claim = response.static_claim
        if claim is None or not (claim.literal or claim.comparator):
            errors.append("D7 requires positive literal/comparator evidence")
            return errors
        current = clause.current_value
        if current is not None and current.kind == "composite":
            if not prediction.target_path:
                errors.append("composite D7 requires target_path for value matching")
                return errors
            try:
                current = resolve_path(current, prediction.target_path)
            except KeyError:
                errors.append("D7 target_path does not resolve")
                return errors
        if (
            claim.comparator
            and current is not None
            and current.comparator is not None
            and claim.comparator != _TOKENS[current.comparator]
        ):
            errors.append("D7 source comparator does not match the clause")
        return errors
