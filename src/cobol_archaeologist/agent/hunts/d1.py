"""D1 stale-threshold hunt."""

from cobol_archaeologist.agent.policy import (
    BasePolicyHunt,
    require_tools,
    transcript_tools,
)
from cobol_archaeologist.schemas import resolve_path


class D1Hunt(BasePolicyHunt):
    drift_type = "D1_stale_threshold"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        prediction = response.prediction
        if prediction is None:
            return errors
        loci = prediction.code_locus.loci
        tools = set(transcript_tools(transcript))
        if not tools & {"read_paragraph", "resolve_copybook", "grep"}:
            errors += require_tools(transcript, {"read_paragraph"})
        if any(locus.file for locus in loci):
            errors += require_tools(transcript, {"resolve_copybook"})
        current = clause.current_value
        if current is None:
            errors.append("D1 requires a current clause value")
            leaf = None
        elif current.kind == "composite":
            if not prediction.target_path:
                errors.append("composite D1 requires target_path")
                leaf = None
            else:
                try:
                    leaf = resolve_path(current, prediction.target_path)
                except KeyError:
                    errors.append("D1 target_path does not resolve")
                    leaf = None
        else:
            leaf = current
        if leaf is not None:
            values = leaf.value if isinstance(leaf.value, list) else [leaf.value]
            rationale = prediction.gold_rationale.lower()
            if not any(str(value).lower() in rationale for value in values):
                errors.append(
                    "D1 rationale must compare against the current target value"
                )
        if response.static_claim is None or response.static_claim.literal is None:
            errors.append("D1 requires a literal evidence hook")
        return errors
