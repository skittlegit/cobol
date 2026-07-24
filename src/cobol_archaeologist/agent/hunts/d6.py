"""D6 dead-code hunt.

This module deliberately supplies only a ``dead_paragraph`` evidence hook.
Reachability is decided by the existing T3.4 verifier, not here.
"""

from cobol_archaeologist.agent.policy import BasePolicyHunt, require_tools
from cobol_archaeologist.model.verify import VerificationTier


class D6Hunt(BasePolicyHunt):
    drift_type = "D6_dead_code"

    # DECISION (reachability ownership): provide only the evidence hook and
    # require verifier-authored Tier-2 evidence; never rebuild graph semantics.
    def validate_response(self, response, transcript, clause):
        errors = super().validate_response(response, transcript, clause)
        errors += require_tools(transcript, {"read_paragraph"})
        if (
            response.static_claim is None
            or response.static_claim.dead_paragraph is None
        ):
            errors.append("D6 requires a dead_paragraph verifier hook")
        return errors

    def validate_trajectory(self, trajectory):
        errors = super().validate_trajectory(trajectory)
        verification = trajectory.verification
        if verification is None:
            return errors
        if verification.tier != VerificationTier.STATIC:
            errors.append("D6 requires Tier-2 delegated reachability verification")
        evidence = verification.evidence
        if "forest_roots + reachable_from" not in evidence:
            errors.append("D6 lacks delegated reachability evidence")
        return errors
