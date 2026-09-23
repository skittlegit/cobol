"""D3 contradictory-outcomes hunt."""

from cobol_archaeologist.agent.policy import BasePolicyHunt, transcript_tools


class D3Hunt(BasePolicyHunt):
    drift_type = "D3_contradictory"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        prediction = response.prediction
        if prediction is None:
            return errors
        loci = prediction.code_locus.loci
        # Multiple line spans in one paragraph need one acquisition. Requiring
        # duplicate reads adds no independent evidence.
        required_reads = max(
            1,
            len({(locus.program, locus.paragraph) for locus in loci}),
        )
        if transcript_tools(transcript).count("read_paragraph") < required_reads:
            errors.append(
                "required tool evidence missing: "
                f"{required_reads} read_paragraph calls "
                "(one per unique D3 paragraph)"
            )
        if not loci:
            errors.append("D3 requires at least one contradictory source locus")
        if (
            len({locus.program for locus in loci}) > 1
            and not prediction.code_locus.is_interprocedural
        ):
            errors.append("multi-program D3 must be interprocedural")
        rationale = prediction.rationale.lower()
        if not any(
            word in rationale
            for word in (
                "conflict",
                "contradict",
                "disagree",
                "bypass",
                "ignore",
            )
        ):
            errors.append("D3 rationale must name the conflicting outcomes")
        if response.static_claim is None:
            errors.append("D3 requires a concrete static evidence hook")
        return errors
