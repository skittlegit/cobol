"""D5 boundary/comparator hunt."""

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


class D5Hunt(BasePolicyHunt):
    drift_type = "D5_boundary_error"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, {"read_paragraph"})
        prediction = response.prediction
        current = clause.current_value
        if prediction is None or current is None:
            return errors + ["D5 requires a typed current value"]
        if current.kind == "composite":
            if not prediction.target_path:
                return errors + ["composite D5 requires target_path"]
            try:
                leaf = resolve_path(current, prediction.target_path)
            except KeyError:
                return errors + ["D5 target_path does not resolve"]
        else:
            leaf = current
        if leaf.comparator is None:
            errors.append("D5 target leaf requires a typed comparator")
        source_comparator = (
            response.static_claim.comparator if response.static_claim else None
        )
        if source_comparator is None:
            errors.append("D5 requires a source comparator evidence hook")
        elif leaf.comparator and source_comparator == _TOKENS[leaf.comparator]:
            errors.append("source comparator matches clause; not a D5 boundary error")
        return errors
