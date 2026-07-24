"""D3 contradictory-outcomes hunt."""

from cobol_archaeologist.agent.policy import BasePolicyHunt, transcript_tools


class D3Hunt(BasePolicyHunt):
    drift_type = "D3_contradictory"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        if transcript_tools(transcript).count("read_paragraph") < 2:
            errors.append("required tool evidence missing: two read_paragraph calls")
        prediction = response.prediction
        if prediction is None:
            return errors
        loci = prediction.code_locus.loci
        if len(loci) < 2:
            errors.append("D3 requires at least two conflicting loci")
        if (
            len({locus.program for locus in loci}) > 1
            and not prediction.code_locus.is_interprocedural
        ):
            errors.append("multi-program D3 must be interprocedural")
        rationale = prediction.gold_rationale.lower()
        if not any(word in rationale for word in ("conflict", "contradict", "disagree")):
            errors.append("D3 rationale must name the conflicting outcomes")
        if response.static_claim is None:
            errors.append("D3 requires a concrete static evidence hook")
        return errors
