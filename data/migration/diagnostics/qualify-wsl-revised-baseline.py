"""Provider-free actual WSL execution of four revised fixtures on original bytes."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from wsl_migration_backend import WSLValidationBackend
from cobol_archaeologist.migration.ai_review import AICaseSpec
from cobol_archaeologist.migration.backend import FixtureProtocol


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Immutable diagnostic already differs: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(raw)


if __name__ == "__main__":
    out = ROOT / "data/migration/ai-review"
    inventory = json.loads((out / "revisions/fixtures-preparation.json").read_bytes())
    script = ROOT / "scripts/wsl_migration_backend.py"
    capabilities = {
        "schema_version": "migration-r2-qualified-wsl-capabilities-v1",
        "execution_environment": "linux-wsl",
        "backend_script": {"path": str(script.relative_to(ROOT)).replace("\\", "/"),
                           "sha256": hashlib.sha256(script.read_bytes()).hexdigest()},
        "cases": [],
    }
    result = {
        "schema_version": "migration-revised-original-baseline-qualification-v1",
        "execution_environment": "linux-wsl",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "provider_calls": 0,
        "patches_applied": 0,
        "qualification_driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": [],
    }
    for case_id in inventory["case_ids"]:
        original = out / "inputs" / case_id
        case = AICaseSpec.model_validate_json((original / "case-input.json").read_bytes())
        fixture_path = out / "revisions/inputs" / case_id / "fixtures.json"
        fixtures = FixtureProtocol.model_validate_json(fixture_path.read_bytes())
        files = {pin.path: (original / "sources" / pin.path).read_bytes().decode("utf-8")
                 for pin in case.frozen_sources}
        backend = WSLValidationBackend(fixtures)
        receipt = backend.capability_receipt()
        if receipt["compiler"] is None:
            raise RuntimeError(receipt["compiler_error"])
        observations = [backend.parse(case, files), backend.compile(case, files),
                        *backend.static(case, files)]
        for check_id in fixtures.checks:
            observation = backend.behavior(case, files, SimpleNamespace(check_id=check_id))
            observations.append(observation)
            print(case_id, check_id, observation.status.value, flush=True)
        capabilities["cases"].append({"case_id": case_id, "backend": receipt})
        result["cases"].append({
            "case_id": case_id,
            "backend": receipt,
            "frozen_sources": [pin.model_dump(mode="json") for pin in fixtures.frozen_sources],
            "fixture_protocol_sha256": fixtures.sha256,
            "fixtures": {"path": fixture_path.relative_to(out).as_posix(),
                         "sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest()},
            "observations": [o.model_dump(mode="json") for o in observations],
        })
    target = ROOT / "data/migration/diagnostics"
    save(target / "wsl-revised-backend-capabilities.json", capabilities)
    save(target / "wsl-revised-original-baseline-qualification.json", result)
    print("All four actual baseline records preserved", flush=True)
