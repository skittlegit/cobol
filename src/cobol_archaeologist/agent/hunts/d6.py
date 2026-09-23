"""D6 dead or disabled compliance-code hunt."""

from cobol_archaeologist.agent.policy import BasePolicyHunt, require_tools
from cobol_archaeologist.model.verify import VerificationTier


class D6Hunt(BasePolicyHunt):
    drift_type = "D6_dead_code"

    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, {"read_paragraph"})
        claim = response.static_claim
        if claim is None or not (claim.dead_paragraph or claim.literal):
            errors.append("D6 requires a dead_paragraph or disabled-guard literal hook")
        return errors

    def validate_trajectory(self, trajectory):
        errors = super().validate_trajectory(trajectory)
        verification = trajectory.verification
        if verification is None:
            return errors
        if verification.tier != VerificationTier.STATIC:
            errors.append("D6 requires Tier-2 delegated reachability verification")
        evidence = verification.evidence
        if not (
            "forest_roots + reachable_from" in evidence
            or "literal" in evidence
        ):
            errors.append("D6 lacks delegated dead-code evidence")
        return errors
