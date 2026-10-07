"""Freeze isolated stage generation and qualification without calling a provider."""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

try:
    from scripts import seal_r2_stage_generation_session as sealer
    from scripts import stage_successor as S
    from scripts.stage_review_contracts import load_stage_canonical_roster
except ModuleNotFoundError:
    import seal_r2_stage_generation_session as sealer
    import stage_successor as S
    from stage_review_contracts import load_stage_canonical_roster

ROOT = Path(__file__).resolve().parents[1]
NEW_RUNTIME = (
    "scripts/stage_successor.py",
    "scripts/seal_r2_stage_generation_session.py",
    "scripts/validate_r2_stage_generation.py",
    "scripts/prepare_r2_stage_generation.py",
)


def encoded(value):
    return sealer.json_bytes(value)


def pin(root, path):
    return sealer.pin(root, root / path, (root / path).read_bytes()).model_dump(
        mode="json"
    )


def read(root, evidence):
    return sealer.read_pin(
        root,
        evidence.model_dump(mode="json")
        if hasattr(evidence, "model_dump")
        else evidence,
    )


def write(root, path, raw):
    sealer.immutable(sealer.inside(root, path), raw)


def fresh_finding(case, review_root):
    """Build the finding solely from approved scope, regulation and measured baseline."""
    clause = json.loads(read(review_root, case.regulation_evidence))
    measured = [
        p
        for p in case.fixture_evidence
        if p.path.endswith("/revised-original-observations.json")
    ]
    if len(measured) != 1:
        raise ValueError("exactly one measured original observation pin is required")
    baseline = json.loads(read(review_root, measured[0]))["case"]
    if baseline["case_id"] != case.case_id or baseline["frozen_sources"] != [
        s.model_dump(mode="json") for s in case.frozen_sources
    ]:
        raise ValueError("measured baseline case/source binding differs")
    checks = {o["check_id"]: o["status"] for o in baseline["observations"]}
    if (
        checks.get("parser") != "pass"
        or checks.get("compile") != "pass"
        or checks.get(case.intended_behavior.check_id) != "fail"
    ):
        raise ValueError(
            "baseline must parse/compile and demonstrate intended discrepancy"
        )
    if any(checks.get(c.check_id) != "pass" for c in case.unaffected_regressions):
        raise ValueError("baseline unaffected observations must pass")
    loci, lines, extracts = [], [], []
    sources = {
        s.path: read(review_root, evidence).decode("utf-8").splitlines()
        for s, evidence in zip(case.frozen_sources, case.source_evidence, strict=True)
    }
    hosts = [text for path, text in sources.items() if path == case.primary_program]
    if len(hosts) != 1:
        raise ValueError("exact primary host source is required")
    programs = re.findall(
        r"PROGRAM-ID\.\s+([\w-]+)\.", "\n".join(hosts[0]), re.IGNORECASE
    )
    if len(programs) != 1:
        raise ValueError("primary source must declare exactly one program identity")
    program = programs[0]
    for scope in case.allowed_source_scope:
        for start, end in scope.line_spans:
            if scope.path not in sources or end > len(sources[scope.path]):
                raise ValueError("approved locus outside exact source")
            loci.append(
                {
                    "program": program,
                    "paragraph": next(
                        (
                            m.group(1)
                            for line in reversed(sources[scope.path][:start])
                            if (m := re.fullmatch(r"\s*(\d{4}-[\w-]+)\.\s*", line))
                        ),
                        None,
                    ),
                    "file": scope.path,
                    "line_span": [start, end],
                }
            )
            lines.extend(
                {"program": program, "file": scope.path, "line": n}
                for n in range(start, end + 1)
            )
            extracts.append(
                f"{scope.path}:{start}-{end}: "
                + " | ".join(sources[scope.path][start - 1 : end])
            )
    # DECISION: labels required by the internal prediction schema derive only
    # from authorized source spans; stage_successor removes them from prompts.
    target = {}
    current = clause.get("current_value") or {}
    if current.get("kind") == "composite" and case.drift_type in {
        "D1_stale_threshold",
        "D5_boundary_error",
    }:
        candidates = [
            name
            for name in current["value"]
            if name.upper().replace("_", "-") in " ".join(extracts).upper()
        ]
        if len(candidates) != 1:
            raise ValueError(
                "composite target must derive uniquely from authorized source locus"
            )
        target["target_path"] = candidates[0]
    return S.MigrationFinding.model_validate(
        {
            "origin": "oracle_assisted",
            "prediction": {
                "instance_id": case.instance_id,
                **target,
                "drift_type": case.drift_type,
                "regulation_clause": clause,
                "code_locus": {
                    "loci": loci,
                    "slice_vars": [],
                    "is_interprocedural": case.stratum == "interprocedural",
                },
                "labels": {
                    "program_level": "drift",
                    "paragraph_level": "drift",
                    "line_level": lines,
                },
                "rationale": "Pinned original source at the authorized locus: "
                + "; ".join(extracts)
                + ". Executed original observations fail the approved finite intended check; "
                + case.intended_behavior.description,
            },
            "verifier_tier": "executed",
            "verifier_evidence": "Original parser/compile pass; finite intended behavior fails; approved unaffected observations pass. Remediation validation remains pending.",
            "evidence_ledger": [
                "Pinned regulation and authorized source spans",
                "Hash-bound measured original observations",
            ],
        }
    )


def load_inputs(root):
    migration = root / "data/migration"
    manifest = json.loads((migration / "roster-manifest.json").read_bytes())
    for name in (
        "canonical_roster",
        "oracle_assisted_roster",
        "detector_led_roster",
        "review_protocol",
        "disposition",
        "wave_map",
    ):
        read(root, manifest[name])
    if (
        manifest["schema_version"] != "r2-stage-reviewed-roster-manifest-v1"
        or manifest["generation_denominators"]["detector_led"] != 0
    ):
        raise ValueError("unsupported stage intake or active detector track")
    cases = load_stage_canonical_roster(
        root / manifest["canonical_roster"]["path"],
        review_evidence_root=root / manifest["review_evidence_root"],
        protocol_path=root / manifest["review_protocol"]["path"],
        disposition_path=root / manifest["disposition"]["path"],
    )
    if not cases or [c.case_id for c in cases] != manifest["accepted_case_ids"]:
        raise ValueError("stage roster must match a nonempty accepted subset")
    if manifest["generation_denominators"] != {
        "detector_led": 0,
        "oracle_assisted": len(cases),
        "combined": len(cases),
    }:
        raise ValueError("stage generation denominators differ")
    if (root / manifest["oracle_assisted_roster"]["path"]).read_bytes() != (
        root / manifest["canonical_roster"]["path"]
    ).read_bytes() or (root / manifest["detector_led_roster"]["path"]).read_bytes():
        raise ValueError("non-pooled roster bytes differ")
    return cases, manifest


def prepare(root=ROOT, *, frozen_at=None, cli_version=None):
    root = Path(root).resolve()
    cases, intake = load_inputs(root)
    review = root / intake["review_evidence_root"]
    base = root / "data/migration/generation"
    old = json.loads(
        (review / "stage-review/runtime-source-inventory.json").read_bytes()
    )
    for path, digest in old.items():
        read(root, {"path": path, "sha256": digest})
    runtime = {**old, **{path: pin(root, path)["sha256"] for path in NEW_RUNTIME}}
    runtime_hash = sealer.digest(
        json.dumps(runtime, sort_keys=True, separators=(",", ":")).encode()
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path, digest in sorted(runtime.items()):
            raw = read(root, {"path": path, "sha256": digest})
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, raw)
    write(root, base / "runtime-source.zip", archive.getvalue())
    if cli_version is None:
        cli_version = subprocess.run(
            ["codex", "--version"],
            check=True,
            capture_output=True,
            text=True,
            shell=True,
        ).stdout.strip()
    if not cli_version:
        raise ValueError("actual CLI version is required")
    detector = {
        name: pin(root, "data/eval/m4/" + file)
        for name, file in (
            ("evaluation_manifest", "evaluation-manifest.json"),
            ("detector_decision", "detector-decision.json"),
            ("input_roster", "r2-input-roster.json"),
        )
    }
    S.validate_configuration4_binding(
        S.Configuration4Binding.model_validate(detector), evidence_root=root
    )
    entries = []
    for purpose, case in [("official", c) for c in cases] + [
        ("qualification", cases[0])
    ]:
        protocol = next(
            (
                p
                for p in case.fixture_evidence
                if p.sha256 == case.validation_protocol_sha256
            ),
            None,
        )
        if protocol is None:
            raise ValueError("case validation protocol pin is absent")
        method_pins = {
            "runner": pin(root, NEW_RUNTIME[1]),
            "validator": pin(root, NEW_RUNTIME[2]),
            "backend": pin(root, "scripts/wsl_migration_backend.py"),
            "validation_protocol": pin(
                root, review.relative_to(root).as_posix() + "/" + protocol.path
            ),
        }
        req = S.SuccessorMigrationRequest(
            case=case,
            execution_purpose=purpose,
            finding=fresh_finding(case, review),
            detector=detector,
            schema_sha256=S.successor_schema_hashes(),
            method={
                "codex_cli_version": cli_version,
                "runtime_source_sha256": runtime_hash,
                **{name + "_sha256": p["sha256"] for name, p in method_pins.items()},
                "max_turns": 20,
                "max_input_tokens": 32000,
                "max_output_tokens": 8000,
            },
        )
        key = S.successor_run_key(req)
        folder = base / "requests" / purpose / case.case_id
        stage = base / "sources" / purpose / key
        for source, evidence in zip(
            case.frozen_sources, case.source_evidence, strict=True
        ):
            raw = read(review, evidence)
            if sealer.digest(raw) != source.sha256:
                raise ValueError("source evidence differs from canonical source")
            write(root, stage / source.path, raw)
        write(root, folder / "request.json", encoded(req.model_dump(mode="json")))
        packet = {
            "system": S.SYSTEM_PROMPT,
            "user": S.build_successor_prompt(req),
            "staged_sources": [
                str(stage / s.path).replace("\\", "/") for s in case.frozen_sources
            ],
            "output_schema": S.PROPOSAL_ADAPTER.json_schema(),
        }
        write(root, folder / "prompt.json", encoded(packet))
        launch = f"Read only {str(folder / 'prompt.json').replace(chr(92), '/')} and the staged source files explicitly listed in that packet. Do not inspect other files, fixtures, review records, hidden labels, history or other cases. Do not write, apply patches, call providers or spawn agents. Follow the packet and return only exact JSON. Fresh isolated collaboration subagent: fork_turns none, gpt-6-luna max."
        write(root, folder / "launch.txt", launch.encode())
        entries.append(
            {
                "case_id": case.case_id,
                "execution_purpose": purpose,
                "run_key": key,
                "request": pin(
                    root, (folder / "request.json").relative_to(root).as_posix()
                ),
                "request_sha256": S.model_sha256(req),
                "prompt": pin(
                    root, (folder / "prompt.json").relative_to(root).as_posix()
                ),
                "launch": pin(
                    root, (folder / "launch.txt").relative_to(root).as_posix()
                ),
                "method_pins": method_pins,
                "staging_root": stage.relative_to(root).as_posix(),
                "source_pins": [
                    pin(root, (stage / s.path).relative_to(root).as_posix())
                    for s in case.frozen_sources
                ],
            }
        )
    freeze_path = base / "runtime-manifest.json"
    existing = json.loads(freeze_path.read_bytes()) if freeze_path.exists() else None
    manifest = {
        "schema_version": "migration-stage-successor-runtime-manifest-v1",
        "frozen_at": frozen_at
        or (existing["frozen_at"] if existing else datetime.now(UTC).isoformat()),
        "provider": {"model": "gpt-6-luna", "reasoning_effort": "max"},
        "runtime_source_sha256": runtime_hash,
        "runtime_archive": pin(
            root, (base / "runtime-source.zip").relative_to(root).as_posix()
        ),
        "runtime_sources": [
            {"path": p, "sha256": h} for p, h in sorted(runtime.items())
        ],
        "requests": entries,
        "roster_manifest": pin(root, "data/migration/roster-manifest.json"),
        "official_run_keys": [
            e["run_key"] for e in entries if e["execution_purpose"] == "official"
        ],
        "qualification_run_keys": [
            e["run_key"] for e in entries if e["execution_purpose"] == "qualification"
        ],
        "generation_denominators": intake["generation_denominators"],
        "provider_calls": 0,
        "qualification_disclosure": {
            "reused_case_id": cases[0].case_id,
            "repeated_case_exposure": True,
            "official_denominator_contribution": 0,
            "proposal_transfer_permitted": False,
            "prompt_tuning_permitted": False,
        },
    }
    write(root, freeze_path, encoded(manifest))
    for entry in entries:
        sealer.check_freeze(
            root=root,
            freeze_path=freeze_path,
            request_path=root / entry["request"]["path"],
            launch_path=root / entry["launch"]["path"],
        )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    print(json.dumps(prepare(parser.parse_args().root), sort_keys=True, indent=2))
