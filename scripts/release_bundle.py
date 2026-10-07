"""Deterministic allowlisted benchmark archive and unpacked verification.

No provider calls, fetched corpora, model payloads, or evaluation capture logs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

EXPECTED_COUNTS = {"train": 307, "dev": 102, "test": 196}
ANNOTATIONS = {
    "pass_a": "pass_1_Human-Primary.jsonl",
    "pass_b": "pass_2_Claude-Verification.jsonl",
    "adjudications": "adjudication_log.jsonl",
    "adjudicated_real": "real_curated_resolved_v1.jsonl",
}
PUBLIC_SUMMARIES = (
    "release/public/migration-report.json",
    "release/public/migration-report.md",
    "release/public/m4-report.json",
    "release/public/detector-decision.json",
    "release/public/m5-report.json",
    "release/public/paper.md",
    "release/public/paper-numbers.json",
)
ABSOLUTE_HOST_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?<![A-Za-z0-9:/])/(?:Users|home|mnt|tmp|usr|opt|var|private)/"
)
FIXED_PATHS = (
    "LICENSE",
    "README.md",
    "DATASHEET.md",
    "ANNOTATION.md",
    "RELEASE.md",
    "pyproject.toml",
    "setup.py",
    "MANIFEST.in",
    "docs/REPRODUCIBILITY.md",
    "scripts/release_bundle.py",
    "scripts/build_release.py",
    "release/licenses/Apache-2.0.txt",
    "release/licenses/ATTRIBUTION.md",
    "release/licenses/CardDemo-NOTICE.txt",
    "data/manifest.json",
    "data/benchmark/v1/manifest.json",
    "data/benchmark/v1/train.jsonl",
    "data/benchmark/v1/dev.jsonl",
    "data/benchmark/v1/test.jsonl",
    "data/regulations/sources/MANIFEST.json",
    "data/regulations/sources/README.md",
    "data/regulations/clauses.jsonl",
    "vendor/tree-sitter-cobol/LICENSE",
    "vendor/tree-sitter-cobol/PINNED",
    "vendor/tree-sitter-cobol/src/grammar.json",
    "vendor/tree-sitter-cobol/src/node-types.json",
    "vendor/tree-sitter-cobol/src/parser.c",
    "vendor/tree-sitter-cobol/src/scanner.c",
    "vendor/tree-sitter-cobol/src/tree_sitter/parser.h",
) + tuple(f"data/benchmark/annotation/{name}" for name in ANNOTATIONS.values())


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    ).stdout


def clean_identity(root: Path) -> str:
    if git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise ValueError("release requires a clean tracked and untracked Git identity")
    return git(root, "rev-parse", "HEAD").decode().strip()


def safe_file(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError(f"unsafe release path: {name}")
    path = root.joinpath(*relative.parts)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError(f"symlink release path: {name}")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"missing or escaping release file: {name}")
    return path


def paths_for_release(root: Path, profile: str = "benchmark") -> list[str]:
    if profile not in {"benchmark", "successor"}:
        raise ValueError("unsupported release profile")
    tracked = git(root, "ls-files", "-z").decode().split("\0")
    # Validation code only: data/corpora, caches and provider logs cannot enter.
    sources = [
        name
        for name in tracked
        if name.startswith("src/cobol_archaeologist/") and name.endswith(".py")
    ]
    if not sources or "src/cobol_archaeologist/schemas.py" not in sources:
        raise ValueError("required schema validation code is missing")
    return sorted(
        set(FIXED_PATHS)
        | set(sources)
        | (set(PUBLIC_SUMMARIES) if profile == "successor" else set())
    )


def validate_public_summaries(root: Path) -> None:
    for name in PUBLIC_SUMMARIES:
        raw = safe_file(root, name).read_bytes()
        text = raw.decode("utf-8-sig")
        if ABSOLUTE_HOST_PATH.search(text):
            raise ValueError(f"public summary leaks an absolute host path: {name}")
        if name.endswith(".json"):
            summary = json.loads(text)
            if not isinstance(summary, dict) or set(summary) != {
                "schema_version",
                "source_sha256",
                "content",
            }:
                raise ValueError(f"invalid public summary envelope: {name}")
            if (
                summary["schema_version"] != "public-release-summary-v1"
                or not re.fullmatch(r"[0-9a-f]{64}", str(summary["source_sha256"]))
                or not isinstance(summary["content"], dict)
            ):
                raise ValueError(f"invalid public summary schema/source pin: {name}")
        elif "schema_version: public-release-summary-v1" not in text or not re.search(
            r"source_sha256: [0-9a-f]{64}(?:\s|$)", text
        ):
            raise ValueError(f"Markdown summary lacks version/source pin: {name}")


def validate_regulation_clauses(root: Path) -> int:
    from cobol_archaeologist.schemas import RegulationClause

    clauses = [
        json.loads(line)
        for line in safe_file(root, "data/regulations/clauses.jsonl")
        .read_bytes()
        .splitlines()
        if line.strip()
    ]
    identifiers = [row.get("record_id") for row in clauses]
    if (
        not clauses
        or any(not isinstance(item, str) or not item for item in identifiers)
        or len(set(identifiers)) != len(identifiers)
    ):
        raise ValueError("regulation clause record IDs must be nonempty and unique")
    for row in clauses:
        RegulationClause.model_validate(row["clause"])
    return len(clauses)


def validate_benchmark(root: Path) -> dict:
    from cobol_archaeologist.benchmark.annotation import (
        AdjudicationRecord,
        IndependentAnnotation,
        agreement_report,
    )
    from cobol_archaeologist.benchmark.freeze import FreezeManifest, _count_t6_pairs
    from cobol_archaeologist.schemas import DriftInstance

    benchmark_dir = root / "data/benchmark/v1"
    if {path.name for path in benchmark_dir.iterdir()} != {
        "manifest.json",
        "train.jsonl",
        "dev.jsonl",
        "test.jsonl",
    }:
        raise ValueError("unexpected or missing frozen benchmark file")
    manifest = FreezeManifest.model_validate_json(
        safe_file(root, "data/benchmark/v1/manifest.json").read_bytes()
    )
    if manifest.split_counts != EXPECTED_COUNTS:
        raise ValueError("stale benchmark split counts")
    rows = {}
    ids = set()
    for split, count in EXPECTED_COUNTS.items():
        raw = safe_file(root, f"data/benchmark/v1/{split}.jsonl").read_bytes()
        if digest(raw) != manifest.split_sha256[split]:
            raise ValueError(f"benchmark checksum mismatch: {split}")
        parsed = [
            DriftInstance.model_validate_json(line)
            for line in raw.splitlines()
            if line.strip()
        ]
        if len(parsed) != count:
            raise ValueError(f"stale actual row count: {split}")
        for row in parsed:
            if row.instance_id in ids:
                raise ValueError("duplicate instance ID across splits")
            ids.add(row.instance_id)
        rows[split] = parsed
    real = [row for row in rows["test"] if row.provenance.source == "real_curated"]
    if len(real) != manifest.real_curated_test_rows or len(real) != 43:
        raise ValueError("real-curated count must remain 43")
    if manifest.t6_pairs != 9 or _count_t6_pairs(real) != 9:
        raise ValueError("historical T6 pair count must remain 9")
    if (
        len(set(manifest.excluded_candidate_ids)) != 8
        or set(manifest.excluded_candidate_ids) & ids
    ):
        raise ValueError("excluded candidate count/identity mismatch")
    parsed_evidence = {}
    for key, filename in ANNOTATIONS.items():
        raw = safe_file(root, f"data/benchmark/annotation/{filename}").read_bytes()
        if digest(raw) != manifest.annotation_evidence_sha256[key]:
            raise ValueError(f"locked annotation checksum mismatch: {key}")
        model = (
            IndependentAnnotation
            if key in {"pass_a", "pass_b"}
            else AdjudicationRecord
            if key == "adjudications"
            else DriftInstance
        )
        parsed_evidence[key] = [
            model.model_validate_json(line) for line in raw.splitlines() if line.strip()
        ]
    agreement = agreement_report(parsed_evidence["pass_a"], parsed_evidence["pass_b"])
    if agreement.sample_size != manifest.annotation_sample_size:
        raise ValueError("annotation sample size mismatch")
    if {row.instance_id for row in parsed_evidence["adjudicated_real"]} != {
        row.instance_id for row in real
    }:
        raise ValueError("resolved annotations do not match real test IDs")
    resolved_gold = {
        row.instance_id: row.model_dump(mode="json")
        for row in parsed_evidence["adjudicated_real"]
    }
    if resolved_gold != {row.instance_id: row.model_dump(mode="json") for row in real}:
        raise ValueError("resolved annotation gold differs from frozen test gold")
    excluded = {
        row.candidate_id
        for row in parsed_evidence["adjudications"]
        if row.outcome == "exclude"
    }
    if excluded != set(manifest.excluded_candidate_ids):
        raise ValueError("exclusions differ from locked adjudication outcomes")
    groups = [
        {row.provenance.base_program for row in rows[split]}
        for split in EXPECTED_COUNTS
    ]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        raise ValueError("base-program split leakage")
    pins = json.loads(
        safe_file(root, "data/regulations/sources/MANIFEST.json").read_bytes()
    )
    if not pins.get("entries") or any(
        len(entry.get("sha256", "")) != 64 for entry in pins["entries"]
    ):
        raise ValueError("invalid regulation metadata pins")
    validate_regulation_clauses(root)
    return {
        "split_counts": EXPECTED_COUNTS,
        "real_curated_test_rows": 43,
        "historical_t6_pairs": 9,
        "excluded_candidate_ids": manifest.excluded_candidate_ids,
    }


def file_metadata(name: str, raw: bytes) -> dict:
    if name in {
        "release/licenses/Apache-2.0.txt",
        "release/licenses/CardDemo-NOTICE.txt",
    }:
        role, license_name = "third-party-license-or-notice", "Apache-2.0"
    elif name.startswith("data/benchmark/"):
        role, license_name = (
            "benchmark-or-annotation",
            "MIT project annotations; Apache-2.0 CardDemo-derived material; quoted RBI text retains source rights",
        )
    elif name == "data/regulations/clauses.jsonl":
        role, license_name = (
            "quoted-regulation-clauses",
            "external-RBI-source-terms; quoted for compliance-research and citation purposes; no MIT redistribution grant; consult DATASHEET.md and original RBI publication",
        )
    elif name.startswith("data/regulations/"):
        role, license_name = (
            "regulation-source-pin-metadata",
            "MIT metadata; underlying RBI documents excluded, rights not granted",
        )
    else:
        role, license_name = "validation-code-or-documentation", "MIT"
    return {
        "path": name,
        "bytes": len(raw),
        "sha256": digest(raw),
        "role": role,
        "license": license_name,
    }


def render_archive(payloads: dict[str, bytes], manifest: dict) -> bytes:
    all_files = {**payloads, "release/manifest.json": json_bytes(manifest)}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(all_files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, all_files[name])
    return output.getvalue()


def build(root: Path, output: Path, profile: str = "benchmark") -> dict:
    root = root.resolve()
    if output.resolve().is_relative_to(root):
        raise ValueError("build output must be outside the clean working tree")
    commit = clean_identity(root)
    counts = validate_benchmark(root)
    names = paths_for_release(root, profile)
    if profile == "successor":
        validate_public_summaries(root)
    payloads = {name: safe_file(root, name).read_bytes() for name in names}
    # Clean checkout bytes must actually be the recorded revision, including CRLF hazards.
    with tarfile.open(
        fileobj=io.BytesIO(git(root, "archive", commit, *names))
    ) as snapshot:
        committed = {
            member.name: snapshot.extractfile(member).read()
            for member in snapshot.getmembers()
            if member.isfile()
        }
    if committed != payloads:
        raise ValueError("working-tree bytes differ from committed bytes")
    manifest = {
        "schema_version": "licensed-benchmark-release-v1",
        "git_commit": commit,
        "profile": profile,
        "benchmark_manifest_sha256": digest(
            payloads["data/benchmark/v1/manifest.json"]
        ),
        "counts": counts,
        "files": [file_metadata(name, payloads[name]) for name in names],
        "claims": {
            "configuration4": "NOT_EVALUABLE",
            "historical_m4": "NO_GO",
            "provider_resource_telemetry": "not_recorded",
            "successor_results": "consult RELEASE.md; benchmark validation does not validate migration outcomes",
        },
        "excluded": [
            "RBI PDFs",
            "fetched corpora",
            "model caches",
            "provider captures",
            "credentials",
            "superseded benchmarks",
        ],
    }
    raw = render_archive(payloads, manifest)
    if output.exists() and output.read_bytes() != raw:
        raise ValueError("refusing to replace a differing release archive")
    if clean_identity(root) != commit:
        raise ValueError("Git identity changed during release build")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return {
        "git_commit": commit,
        "archive_sha256": digest(raw),
        "archive_bytes": len(raw),
        "manifest": manifest,
    }


def verify_unpacked(root: Path) -> dict:
    manifest = json.loads(safe_file(root, "release/manifest.json").read_bytes())
    if manifest.get("schema_version") != "licensed-benchmark-release-v1":
        raise ValueError("unsupported release manifest")
    expected = {entry["path"] for entry in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise ValueError("duplicate release paths")
    profile = manifest.get("profile")
    if profile not in {"benchmark", "successor"}:
        raise ValueError("unsupported release profile")
    fixed = set(FIXED_PATHS) | (
        set(PUBLIC_SUMMARIES) if profile == "successor" else set()
    )
    if not fixed.issubset(expected) or any(
        name not in fixed
        and not (name.startswith("src/cobol_archaeologist/") and name.endswith(".py"))
        for name in expected
    ):
        raise ValueError("release manifest violates the licensed allowlist")
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != expected | {"release/manifest.json"}:
        raise ValueError("unexpected or missing unpacked release file")
    for entry in manifest["files"]:
        raw = safe_file(root, entry["path"]).read_bytes()
        if entry != file_metadata(entry["path"], raw):
            raise ValueError(
                f"release checksum/size/role/license mismatch: {entry['path']}"
            )
    if (
        digest(safe_file(root, "data/benchmark/v1/manifest.json").read_bytes())
        != manifest["benchmark_manifest_sha256"]
    ):
        raise ValueError("benchmark manifest pin mismatch")
    if validate_benchmark(root) != manifest["counts"]:
        raise ValueError("release counts mismatch")
    if profile == "successor":
        validate_public_summaries(root)
    return {
        "status": "VALID",
        "git_commit": manifest["git_commit"],
        "files": len(expected),
    }


def two_clean_builds(
    root: Path, first: Path, second: Path, profile: str = "benchmark"
) -> dict:
    if first.resolve() == second.resolve():
        raise ValueError("two-build check requires distinct output paths")
    one, two = build(root, first, profile), build(root, second, profile)
    if first.read_bytes() != second.read_bytes():
        raise ValueError("two clean builds differ")
    return {
        "status": "IDENTICAL",
        "git_commit": one["git_commit"],
        "archive_sha256": one["archive_sha256"],
        "second_archive_sha256": two["archive_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify", "two-builds"))
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--second-output", type=Path)
    parser.add_argument(
        "--profile", choices=("benchmark", "successor"), default="benchmark"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / "src"))
    sys.dont_write_bytecode = True
    if args.mode == "verify":
        result = verify_unpacked(args.root)
    elif args.mode == "two-builds" and args.output and args.second_output:
        result = two_clean_builds(
            args.root, args.output, args.second_output, args.profile
        )
    elif args.mode == "build" and args.output:
        result = build(args.root, args.output, args.profile)
    else:
        parser.error(
            "build modes require --output; two-builds also requires --second-output"
        )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
