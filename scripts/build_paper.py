"""Deterministic anonymous draft and exhaustive, source-bound numeric audit.

Uses committed JSON measurements; never runs models or changes frozen code.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "benchmark": "data/benchmark/v1/manifest.json",
    "m5": "data/eval/m5/report.json",
    "m4": "data/eval/m4/report.json",
    "ablations": "data/eval/m5/ablations/report.json",
}
SECTIONS = {
    "benchmark": [
        "split_counts",
        "real_curated_test_rows",
        "t6_pairs",
        "annotation_sample_size",
    ],
    "m5": [
        "methodology",
        "benchmark",
        "metrics",
        "ci_fragile_cells",
        "paired_comparisons",
        "faithfulness",
        "calibration",
        "abstention",
        "t6",
        "cost_efficiency",
        "frozen_decisions",
        "headline_result",
    ],
    "m4": [
        "historical_summaries",
        "system_summaries",
        "paired_comparisons",
        "primary_comparison",
        "quality_gates",
        "temporal",
        "resource_telemetry",
    ],
    "ablations": ["metrics", "paired_comparisons", "tradeoffs"],
}
TOKEN = re.compile(r"\{\{([a-z0-9_]+):([^{}]+)\}\}")
QUALIFIERS = {
    "not_recorded",
    "not_applicable",
    "CI-fragile",
    "ok",
    "NO_GO",
    "NOT_EVALUABLE",
    "VALID",
    "VACATED",
    "NOT_EVALUABLE_FOR_BAR",
    "COMPLETE",
    "PASS",
    "FAIL",
    "inactive",
    "INACTIVE",
    "validation_passed",
    "abstained",
}
FORBIDDEN = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|Users[\\/]deepa|sk-[A-Za-z0-9]{20}|BEGIN PRIVATE KEY)"
)
PRIVATE_SECTIONS = {
    "abstention_reasons",
    "annotation_evidence",
    "excluded_candidate_ids",
    "raw_validation_logs",
    "validation_logs",
    "raw_logs",
    "backend",
    "compiler",
    "evidence",
    "source_pins",
    "method_identity",
}


def private_entry(key, value):
    # Empirical failure counts remain public; structured failure diagnostics do
    # not belong in anonymous artifacts.
    scalar_count = isinstance(value, (int, float, bool)) or value is None
    return key in PRIVATE_SECTIONS or (key == "failures" and not scalar_count)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def resolve(document, pointer: str):
    value = document
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def leaves(value, pointer=""):
    if isinstance(value, dict):
        for key, child in value.items():
            # Free-text failure logs are retained in the original reports, not
            # redistributed in anonymous submission artifacts.
            if not private_entry(key, child):
                yield from leaves(child, pointer + "/" + encoded(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, pointer + "/" + str(index))
    elif (
        isinstance(value, (int, float, bool))
        or value is None
        or (isinstance(value, str) and value in QUALIFIERS)
    ):
        yield pointer, value


def display(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def render_html(markdown: str) -> str:
    """Small dependency-free renderer for this generated document's grammar."""

    def inline(line):
        line = html.escape(line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", line)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", line)

    parts = []
    paragraph = []
    table = False

    def flush():
        if paragraph:
            parts.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    for line in markdown.splitlines():
        if line.startswith("|"):
            flush()
            if not table:
                parts.append("<table>")
                table = True
            if re.fullmatch(r"[|\s:-]+", line):
                continue
            cells = line.strip("|").split("|")
            parts.append(
                "<tr>"
                + "".join("<td>" + inline(c.strip()) + "</td>" for c in cells)
                + "</tr>"
            )
        else:
            if table:
                parts.append("</table>")
                table = False
            if not line:
                flush()
            elif line.startswith("#"):
                flush()
                level = len(line) - len(line.lstrip("#"))
                parts.append(
                    f"<h{level}>" + inline(line[level:].strip()) + f"</h{level}>"
                )
            else:
                paragraph.append(line)
    flush()
    if table:
        parts.append("</table>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>Anonymous regulatory conformance paper</title>"
        "<style>body{max-width:72rem;margin:3rem auto;padding:1rem;font:17px/1.6 serif}"
        "table{border-collapse:collapse;font:13px/1.5 monospace;width:100%}"
        "td{border:1px solid #bbb;padding:.4rem;overflow-wrap:anywhere}"
        "a{color:#164c89}code{overflow-wrap:anywhere}</style><body>"
        + "\n".join(parts)
        + "</body></html>\n"
    )


def pinned_json(root: Path, pin: dict) -> dict:
    if set(pin) != {"path", "sha256"} or not re.fullmatch(
        r"[0-9a-f]{64}", pin["sha256"]
    ):
        raise ValueError("Invalid finalization artifact pin")
    path = (root / pin["path"]).resolve()
    if (
        Path(pin["path"]).is_absolute()
        or ".." in Path(pin["path"]).parts
        or not path.is_relative_to(root.resolve())
        or path.is_symlink()
    ):
        raise ValueError("Finalization artifact must remain within the checkout")
    raw = path.read_bytes()
    if sha(raw) != pin["sha256"]:
        raise ValueError(f"Stale finalization pin: {pin['path']}")
    return json.loads(raw)


def finalization(root: Path, binding_path: Path | None, migration: dict | None) -> dict:
    pending = [
        "completed deployment validation",
        "completed licensed release validation",
        "same commit and benchmark manifest binding",
        "terminal migration report",
    ]
    result = {
        "state": "DRAFT_SUBMISSION_GATES_PENDING",
        "release_binding": None,
        "migration_binding": None,
        "gates_pending": pending,
    }
    if binding_path is None:
        return result
    binding_path = (root / binding_path).resolve()
    if not binding_path.is_relative_to(root.resolve()):
        raise ValueError("Finalization binding must remain within the checkout")
    binding = json.loads(binding_path.read_bytes())
    required = {
        "schema_version",
        "source_commit",
        "benchmark_manifest",
        "migration_report",
        "release_manifest",
        "release_two_builds",
        "release_unpacked_validation",
        "deployment_receipt",
    }
    if (
        set(binding) != required
        or binding["schema_version"] != "paper-finalization-binding-v1"
    ):
        raise ValueError("Invalid paper finalization binding schema")
    commit = binding["source_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Finalization requires an explicit archive source commit")
    pinned = {
        name: pinned_json(root, binding[name])
        for name in required - {"schema_version", "source_commit"}
    }
    actual_manifest = sha((root / SOURCES["benchmark"]).read_bytes())
    if (
        binding["benchmark_manifest"]["path"] != SOURCES["benchmark"]
        or binding["benchmark_manifest"]["sha256"] != actual_manifest
    ):
        raise ValueError("Paper benchmark manifest binding mismatch")
    report = pinned["migration_report"]
    if (
        binding["migration_report"]["path"] != "data/migration/report.json"
        or report != migration
    ):
        raise ValueError("Finalization migration report mismatch")
    if (
        report.get("schema_version") == "migration-stage-report-v1"
        and report.get("status") == "COMPLETE"
    ):
        pending.remove("terminal migration report")
    manifest = pinned["release_manifest"]
    builds = pinned["release_two_builds"]
    unpacked = pinned["release_unpacked_validation"]
    same_commit = all(
        item.get("git_commit") == commit for item in [manifest, builds, unpacked]
    )
    same_benchmark = manifest.get("benchmark_manifest_sha256") == actual_manifest
    if not same_commit or not same_benchmark:
        raise ValueError("Release source commit or benchmark identity mismatch")
    pending.remove("same commit and benchmark manifest binding")
    archive_hash = builds.get("archive_sha256")
    if (
        manifest.get("schema_version") == "licensed-benchmark-release-v1"
        and manifest.get("profile") == "successor"
        and builds.get("status") == "IDENTICAL"
        and unpacked.get("status") == "VALID"
        and isinstance(archive_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", archive_hash)
        and builds.get("second_archive_sha256") == archive_hash
        and unpacked.get("archive_sha256") == archive_hash
    ):
        pending.remove("completed licensed release validation")
    deployment = pinned["deployment_receipt"]
    # Standalone success cannot stand in for actual container execution or OS
    # isolation. Unknown states remain draft rather than inferred successful.
    deployment_ok = (
        deployment.get("status") == "PASS"
        and deployment.get("container_execution") == "PASS"
        and deployment.get("os_network_isolation") in {"verified", "PASS"}
    )
    if deployment.get("source_commit") != commit:
        raise ValueError("Deployment source commit mismatch")
    measured_pin = deployment.get("measured_receipt")
    measured = pinned_json(root, measured_pin) if isinstance(measured_pin, dict) else {}
    measured_ok = (measured.get("status") == "PASS"
                   and measured.get("container_execution") == "PASS"
                   and measured.get("os_network_isolation") in {"verified", "PASS"})
    archive_files = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    for pin in deployment.get("source_pins", []):
        source = (root / pin["path"]).resolve()
        if (
            not source.is_relative_to(root.resolve())
            or sha(source.read_bytes()) != pin["sha256"]
        ):
            raise ValueError("Deployment source pin mismatch")
        if (root / ".git").exists():
            git_result = subprocess.run(["git", "cat-file", "blob", f"{commit}:{pin['path']}"],
                                    cwd=root, capture_output=True, check=False)
            if git_result.returncode or sha(git_result.stdout) != pin["sha256"]:
                raise ValueError("Deployment source differs from archive source commit")
        elif archive_files.get(pin["path"]) != pin["sha256"]:
            raise ValueError("Deployment source lacks matching archive file pin")
    if deployment_ok and measured_ok and deployment.get("source_pins"):
        pending.remove("completed deployment validation")
    result.update(
        {
            "state": "SUBMISSION_READY"
            if not pending
            else "DRAFT_SUBMISSION_GATES_PENDING",
            "release_binding": {
                "source_commit": commit,
                "benchmark_manifest_sha256": actual_manifest,
                "release_manifest": binding["release_manifest"],
                "two_clean_builds": binding["release_two_builds"],
                "unpacked_validation": binding["release_unpacked_validation"],
                "deployment_receipt": binding["deployment_receipt"],
                "deployment_measured_receipt": measured_pin,
                "paper_artifact_relation": "Final generated paper artifacts follow the archive source revision; they are not claimed byte-identical to the paper packaged inside that archive.",
            },
            "migration_binding": binding["migration_report"],
            "gates_pending": pending,
            "finalization_binding_sha256": sha(binding_path.read_bytes()),
        }
    )
    return result


def outputs(root: Path, binding_path: Path | None = None) -> dict[str, bytes]:
    sources = dict(SOURCES)
    sections = dict(SECTIONS)
    if (root / "data/migration/report.json").is_file():
        sources["migration"] = "data/migration/report.json"
    documents = {
        key: json.loads((root / path).read_bytes()) for key, path in sources.items()
    }
    if "migration" in documents:
        sections["migration"] = [
            key for key, value in documents["migration"].items() if not private_entry(key, value)
        ]
    gate_result = finalization(root, binding_path, documents.get("migration"))
    hashes = {path: sha((root / path).read_bytes()) for path in sources.values()}
    for path in ["paper/manuscript.template.md", "paper/references.json"]:
        hashes[path] = sha((root / path).read_bytes())
    claims = {}

    def claim(source, pointer):
        value = resolve(documents[source], pointer)
        if not (
            isinstance(value, (int, float, bool))
            or value is None
            or (isinstance(value, str) and value in QUALIFIERS)
        ):
            raise ValueError(f"Non-numeric inline claim: {source}:{pointer}")
        ident = "c" + sha((source + ":" + pointer).encode())[:16]
        item = {
            "source": sources[source],
            "json_pointer": pointer,
            "source_sha256": hashes[sources[source]],
            "value": value,
            "rendered": display(value),
        }
        if ident in claims and claims[ident] != item:
            raise ValueError("Claim identifier collision")
        claims[ident] = item
        return ident, display(value)

    appendix = [
        "# Frozen numeric results",
        "",
        "Every cell is generated from a pinned JSON pointer. Values retain full precision;",
        "null denotes an unavailable or non-applicable value, not zero. Boolean gates",
        "retain their measured decisions. Original qualitative error logs are excluded.",
        "",
    ]
    for source, selected_sections in sections.items():
        appendix += [
            "## " + source,
            "",
            "| Claim | JSON pointer | Value |",
            "|---|---|---|",
        ]
        for section in selected_sections:
            for pointer, _ in leaves(documents[source][section], "/" + section):
                ident, rendered = claim(source, pointer)
                appendix.append(f"| {ident} | `{pointer}` | {rendered} |")
        appendix.append("")
    refs = json.loads((root / "paper/references.json").read_bytes())
    if refs["novelty_claim"] != "none":
        raise ValueError("This draft does not authorize a priority claim")
    related = "\n\n".join(
        f"**{r['cell']}.** {r['supported_claim']} [{r['title']}]({r['url']})"
        for r in refs["references"]
    )
    template = (root / "paper/manuscript.template.md").read_text(encoding="utf-8")
    # Empirical numbers must come through source tokens, never independent
    # prose literals. Alphanumeric protocol names such as M5 remain labels.
    without_tokens = TOKEN.sub("", template)
    if re.search(r"(?<![\w])[-+]?\d+(?:\.\d+)?(?![\w])", without_tokens):
        raise ValueError("Unbound quantitative literal in manuscript template")
    template = template.replace("{{related_work}}", related)
    inline_claims = []

    def replace(match):
        source, path = match.groups()
        ident, rendered = claim(source, "/" + path)
        inline_claims.append(ident)
        return rendered + f" ([{ident}](claim-map.json))"

    manuscript = TOKEN.sub(replace, template)
    if "{{" in manuscript:
        raise ValueError("Unresolved manuscript placeholder")
    if "migration" in documents:
        manuscript += (
            "\n## Migration measurements\n\n"
            "The source-bound numerical appendix includes the migration report's measured "
            "outcomes and mandatory-check counts. Detector-led results and oracle-assisted "
            "results remain separate; oracle-assisted fixtures do not establish general "
            "migration capability or legal correctness. Raw compiler logs and backend paths "
            "remain outside this anonymous paper.\n"
        )
        summary_paths = [
            "/tracks/oracle_assisted/evaluated",
            "/tracks/oracle_assisted/outcomes/pass",
            "/tracks/oracle_assisted/outcomes/fail",
            "/tracks/oracle_assisted/outcomes/abstention",
            "/distinct_oracle_source_bundles",
            "/tracks/detector_led/eligible",
        ]
        try:
            for pointer in summary_paths:
                resolve(documents["migration"], pointer)
        except (KeyError, IndexError, TypeError):
            pass
        else:
            rendered_summary = []
            for pointer in summary_paths:
                ident, rendered = claim("migration", pointer)
                inline_claims.append(ident)
                rendered_summary.append(rendered + f" ([{ident}](claim-map.json))")
            evaluated, passed, failed, abstained, bundles, detector_eligible = (
                rendered_summary
            )
            manuscript += (
                f"\nThe oracle-assisted track evaluated {evaluated} cases: {passed} passed, "
                f"{failed} failed, and {abstained} abstained, across {bundles} distinct source "
                f"bundles. The detector-led track has {detector_eligible} eligible cases and "
                "remains inactive because detector release provenance is not evaluable. "
                "Successful finite oracle-assisted validations do not establish end-to-end "
                "detector-led migration success.\n"
            )
    if gate_result["state"] == "SUBMISSION_READY":
        manuscript = manuscript.replace(
            "**Anonymous draft; submission gates pending.**",
            "**Anonymous submission package; audited artifact bindings recorded.**",
        )
        manuscript = manuscript.replace(
            "This draft does not\nclaim that those submission gates are complete.",
            "The final artifact bindings and passed submission gates are recorded in the claim map.",
        )
    # Explicit model identity without raw provider sessions or local paths.
    appendix += ["## Model identity and provenance", ""]
    for system, identity in documents["m5"]["system_identities"].items():
        provider = identity.get("provider_identity", {})
        safe = {
            k: v
            for k, v in provider.items()
            if any(
                t in k
                for t in ("model", "reasoning_effort", "prompt_version", "disclosure")
            )
        }
        appendix += [f"**{system}**: `{json.dumps(safe, ensure_ascii=False)}`", ""]
    appendix += [
        "The later repeated-roster configuration uses the model and reasoning effort",
        "recorded in its frozen identity; its status does not supersede historical decisions.",
        "",
    ]
    later = documents["m4"].get("freeze", {})
    appendix += [
        "`"
        + json.dumps(
            {
                k: later.get(k)
                for k in ("model_id", "reasoning_effort", "prompt_version")
            }
        )
        + "`",
        "",
    ]
    numbers = "\n".join(appendix)
    mapping = {
        "schema": "paper-numeric-claim-map-v1",
        "source_hashes": hashes,
        "claims": claims,
        "inline_claims": inline_claims,
        **gate_result,
    }
    result = {
        "manuscript.md": manuscript.encode(),
        "numbers.md": numbers.encode(),
        "manuscript.html": render_html(manuscript).encode(),
        "numbers.html": render_html(numbers).encode(),
        "claim-map.json": (
            json.dumps(mapping, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        ).encode(),
    }
    for name, raw in result.items():
        if FORBIDDEN.search(raw.decode()):
            raise ValueError(
                f"Anonymous artifact contains a private path or credential: {name}"
            )
    return result


def build(
    root: Path = ROOT, check: bool = False, binding_path: Path | None = None
) -> dict:
    generated = outputs(root, binding_path)
    for name, data in generated.items():
        path = root / "paper" / name
        if check:
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError(f"Stale or hand-edited paper artifact: {name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    mapping = json.loads(generated["claim-map.json"])
    return {
        "state": mapping["state"],
        "claims": len(mapping["claims"]),
        "artifacts": {name: sha(data) for name, data in generated.items()},
        "audit": "PASS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--binding",
        type=Path,
        help="Explicit external archive/source binding JSON, relative to checkout",
    )
    args = parser.parse_args()
    print(json.dumps(build(args.root.resolve(), args.check, args.binding), indent=2))


if __name__ == "__main__":
    main()
