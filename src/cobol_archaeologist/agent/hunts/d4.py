"""D4 stale-reference-data hunt."""

from cobol_archaeologist.agent.policy import BasePolicyHunt, require_tools


class D4Hunt(BasePolicyHunt):
    drift_type = "D4_stale_reference_data"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, {"resolve_copybook"})
        current = clause.current_value
        if current is None or current.kind != "enum_set":
            errors.append("D4 requires a clause enum_set")
            return errors
        prediction = response.prediction
        if prediction is None:
            return errors
        rationale = prediction.gold_rationale.lower()
        values = current.value if isinstance(current.value, list) else []
        if not any(str(value).lower() in rationale for value in values):
            errors.append("D4 rationale must name a missing or extra enum entry")
        return errors
