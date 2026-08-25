"""Provider-neutral T6.2 prompt and immutable per-case staging helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from cobol_archaeologist.migration.contracts import (
    MigrationRequest,
    MigrationTrack,
    PatchArtifact,
)

if TYPE_CHECKING:
    from cobol_archaeologist.eval.config3_live import Config3RunFreeze
    from cobol_archaeologist.eval.schemas import EvaluationRecord

MIGRATION_SYSTEM_PROMPT = """You are a COBOL remediation agent operating on one case.
Use only the supplied verified finding and staged source files. Work only inside
the staged case directory. Never inspect credentials, git history, mutation
provenance, hidden labels, or another case. Either emit a minimal unified diff
touching only lines necessary to address the verified finding, with rationale, intended behavior, and
affected locations, or explicitly abstain. Preserve source-line and
program/copybook boundaries. You propose a patch; a separate validator decides
whether it is safe or behaviorally correct."""


def _canonical_model_hash(model) -> str:
    raw = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_detector_evidence_binding(
    request: MigrationRequest,
    *,
    records: list[EvaluationRecord],
    records_sha256: str,
) -> None:
    """Bind a detector request to one canonically verified config-3 record."""

    if request.track != MigrationTrack.DETECTOR_LED:
        return
    binding = request.detector_evidence
    if binding is None:
        raise ValueError("detector-led request lacks configuration-3 evidence")
    if binding.detector_records_sha256 != records_sha256:
        raise ValueError("detector record collection hash differs from request pin")
    matches = [
        record for record in records if record.instance_id == request.case.instance_id
    ]
    if len(matches) != 1:
        raise ValueError("detector request must resolve exactly one config-3 record")
    record = matches[0]
    if (
        record.run_key != binding.evaluation_run_key
        or _canonical_model_hash(record) != binding.evaluation_record_sha256
    ):
        raise ValueError("config-3 detector record identity differs from request pin")
    if (
        record.system_id != "adaptive_agent"
        or record.abstained
        or record.infrastructure_error is not None
        or record.prediction is None
        or record.verification is None
        or not record.verification.verified
        or record.prediction != request.finding.prediction
        or record.verification.tier is None
        or record.verification.tier.name.lower() != request.finding.verifier_tier
        or record.verification.evidence != request.finding.verifier_evidence
    ):
        raise ValueError(
            "detector-led finding is not the verified adaptive config-3 prediction"
        )


def build_migration_prompt(request: MigrationRequest) -> str:
    """Build the complete case-local prompt without resolving hidden refs."""

    case = request.case
    finding = request.finding
    visible_case = {
        "case_id": case.case_id,
        "instance_id": case.instance_id,
        "drift_type": case.drift_type,
        "stratum": case.stratum,
        "validation_capability": case.validation_capability,
        "primary_program": case.primary_program,
        "source_files": [source.path for source in case.frozen_sources],
        "source_sha256": {source.path: source.sha256 for source in case.frozen_sources},
    }
    if request.track == MigrationTrack.ORACLE_ASSISTED:
        visible_case.update(
            {
                "allowed_source_scope": [
                    scope.model_dump(mode="json") for scope in case.allowed_source_scope
                ],
                "intended_behavior": case.intended_behavior.model_dump(mode="json"),
                "unaffected_regressions": [
                    check.model_dump(mode="json")
                    for check in case.unaffected_regressions
                ],
                "affected_hosts": list(case.affected_hosts),
            }
        )
    visible_finding = {
        "origin": finding.origin,
        "prediction": finding.prediction.model_dump(mode="json"),
        "verifier_tier": finding.verifier_tier,
        "verifier_evidence": finding.verifier_evidence,
    }
    if request.track == MigrationTrack.ORACLE_ASSISTED:
        visible_finding["evidence_ledger"] = list(finding.evidence_ledger)
    payload = json.dumps(
        {
            "case": visible_case,
            "verified_finding": visible_finding,
            "provider": request.provider.model_dump(mode="json"),
            "method": request.method.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        f"Evaluation track: {request.track.value}.\n"
        "The JSON below is the complete authorized input. Do not seek other data.\n"
        f"{payload}\n"
        "Return one patch-or-abstention object matching the migration contract."
    )


def migration_run_key(request: MigrationRequest) -> str:
    """Derive a reproducible run key from frozen identity and visible input."""

    schema_sha256 = {
        "request": hashlib.sha256(
            json.dumps(
                MigrationRequest.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "response": hashlib.sha256(
            json.dumps(
                PatchArtifact.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    }
    material = {
        "request": request.model_dump(mode="json"),
        "schema_sha256": schema_sha256,
        "system_prompt": MIGRATION_SYSTEM_PROMPT,
        "user_prompt": build_migration_prompt(request),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_artifact_identity(
    request: MigrationRequest,
    artifact: PatchArtifact,
) -> None:
    """Fail closed unless a model artifact belongs to the frozen request."""

    if artifact.run_key != migration_run_key(request):
        raise ValueError("artifact run key does not match the frozen request")
    if artifact.case_id != request.case.case_id:
        raise ValueError("artifact case ID does not match the frozen request")
    if artifact.track != request.track:
        raise ValueError("artifact track does not match the frozen request")


def assert_track_authorized(
    request: MigrationRequest,
    *,
    config3_output_dir: Path,
    config3_freeze: Config3RunFreeze,
) -> None:
    """Revalidate canonical configuration-3 evidence before track activation."""

    from cobol_archaeologist.eval.config3_live import (
        load_revalidate_configuration3_decision,
        load_verified_config3_detector_records,
    )

    decision, _ = load_revalidate_configuration3_decision(
        output_dir=config3_output_dir,
        freeze=config3_freeze,
    )
    if request.track == MigrationTrack.DETECTOR_LED and decision.status != "GO":
        raise PermissionError(
            "detector-led migration is inactive unless the canonically revalidated "
            f"configuration-3 decision is GO (observed {decision.status})"
        )
    if request.track == MigrationTrack.DETECTOR_LED:
        records, records_sha256 = load_verified_config3_detector_records(
            output_dir=config3_output_dir,
            freeze=config3_freeze,
        )
        validate_detector_evidence_binding(
            request,
            records=records,
            records_sha256=records_sha256,
        )


def stage_case_sources(
    request: MigrationRequest,
    *,
    canonical_root: Path,
    staging_root: Path,
) -> Path:
    """Copy hash-verified sources into a fresh run-key staging directory."""

    run_key = migration_run_key(request)
    case_root = staging_root / run_key
    case_root.mkdir(parents=True, exist_ok=False)
    canonical_resolved = canonical_root.resolve()
    try:
        for frozen in request.case.frozen_sources:
            source = (canonical_resolved / frozen.path).resolve()
            source.relative_to(canonical_resolved)
            content = source.read_bytes()
            observed = hashlib.sha256(content).hexdigest()
            if observed != frozen.sha256:
                raise ValueError(
                    f"frozen source hash mismatch for {frozen.path}: "
                    f"expected {frozen.sha256}, observed {observed}"
                )
            target = case_root / frozen.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    except Exception:
        shutil.rmtree(case_root)
        raise
    return case_root
