"""Public release wrappers preserve measured numbers and exclude host details."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import Path

import pytest

from scripts.prepare_public_release import build, public_markdown, sanitize
from scripts.release_bundle import (
    ABSOLUTE_HOST_PATH,
    FIXED_PATHS,
    PUBLIC_SUMMARIES,
    validate_public_summaries,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "migration-report.json": "data/migration/report.json",
    "m4-report.json": "data/eval/m4/report.json",
    "detector-decision.json": "data/eval/m4/detector-decision.json",
    "m5-report.json": "data/eval/m5/report.json",
    "paper-numbers.json": "paper/claim-map.json",
    "migration-report.md": "data/migration/report.md",
    "paper.md": "paper/manuscript.md",
}


def measured_numbers(value, prefix=()):
    """Ignore only explicitly non-public host/capture containers, not results."""
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key not in {"backend", "log", "raw_transcript", "host_events"}:
                result.update(measured_numbers(child, (*prefix, key)))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            result.update(measured_numbers(child, (*prefix, index)))
        return result
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {prefix: value}
    return {}


@pytest.fixture
def canonical_copy(tmp_path):
    for source in SOURCES.values():
        destination = tmp_path / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / source).read_bytes())
    return tmp_path


def test_actual_canonical_numbers_and_source_hashes_survive_public_build(
    canonical_copy,
):
    receipt = build(canonical_copy)
    validate_public_summaries(canonical_copy)
    for name, source in SOURCES.items():
        canonical = (canonical_copy / source).read_bytes()
        public = (canonical_copy / "release/public" / name).read_bytes()
        source_hash = hashlib.sha256(canonical).hexdigest()
        assert receipt["artifacts"][name]["source_sha256"] == source_hash
        assert (
            receipt["artifacts"][name]["public_sha256"]
            == hashlib.sha256(public).hexdigest()
        )
        assert not ABSOLUTE_HOST_PATH.search(public.decode())
        if name.endswith(".json"):
            wrapper = json.loads(public)
            assert wrapper["source_sha256"] == source_hash
            assert measured_numbers(wrapper["content"]) == measured_numbers(
                json.loads(canonical)
            )
        else:
            assert (
                public
                == f"schema_version: public-release-summary-v1\nsource_sha256: {source_hash}\n\n".encode()
                + public_markdown(name, canonical)
            )
    migration = json.loads(
        (canonical_copy / "release/public/migration-report.json").read_bytes()
    )["content"]
    assert migration["tracks"]["detector_led"]["evaluated"] == 0
    assert migration["tracks"]["oracle_assisted"]["evaluated"] == 4
    assert migration["tracks"]["oracle_assisted"]["outcomes"] == {
        "pass": 4,
        "fail": 0,
        "abstention": 0,
    }
    assert migration["detector_decision"] == "NOT_EVALUABLE"
    assert migration["end_to_end_migration_claim_supported"] is False
    assert migration["provider_usage"] == "not_recorded"
    assert migration["distinct_oracle_source_bundles"] == 3


def test_public_preparation_is_deterministic_and_detectably_refreshes_sources(
    canonical_copy,
):
    first = build(canonical_copy)
    original = {
        name: (canonical_copy / "release/public" / name).read_bytes()
        for name in SOURCES
    }
    assert build(canonical_copy) == first
    source = canonical_copy / SOURCES["migration-report.json"]
    data = json.loads(source.read_bytes())
    data["test_only_refresh_marker"] = 0.125
    source.write_text(json.dumps(data))
    refreshed = build(canonical_copy)
    assert (
        refreshed["artifacts"]["migration-report.json"]["source_sha256"]
        != first["artifacts"]["migration-report.json"]["source_sha256"]
    )
    public = json.loads(
        (canonical_copy / "release/public/migration-report.json").read_bytes()
    )
    assert public["content"]["test_only_refresh_marker"] == 0.125
    assert all(
        (canonical_copy / "release/public" / name).read_bytes() == raw
        for name, raw in original.items()
        if name != "migration-report.json"
    )


def test_pending_migration_cannot_be_published(canonical_copy):
    source = canonical_copy / SOURCES["migration-report.json"]
    source.write_text('{"status":"PENDING"}')
    with pytest.raises(ValueError, match="terminal"):
        build(canonical_copy)


def test_private_logs_are_removed_while_failures_rates_and_usage_remain():
    content = {
        "outcome": "fail",
        "pass_rate": 0.25,
        "provider_usage": "not_recorded",
        "backend": {"compiler": "C:/Users/private/compiler.exe"},
        "checks": [{"status": "unavailable", "log": "/mnt/private/log", "attempts": 1}],
        "location": "C:/Users/private/source.cbl",
    }
    result = sanitize(content)
    assert result["outcome"] == "fail" and result["pass_rate"] == 0.25
    assert result["provider_usage"] == "not_recorded"
    assert result["checks"] == [{"status": "unavailable", "attempts": 1}]
    assert "backend" not in result
    assert result["location"] == "host-specific value omitted from public summary"


def test_public_paper_links_resolve_inside_exact_successor_archive_layout(
    canonical_copy,
):
    build(canonical_copy)
    public = (canonical_copy / "release/public/paper.md").read_text(encoding="utf-8")
    allowed = set(FIXED_PATHS) | set(PUBLIC_SUMMARIES)
    local_links = []
    for target in re.findall(r"\]\(([^)]+)\)", public):
        if target.startswith(("https://", "http://", "#")):
            continue
        destination = posixpath.normpath("release/public/" + target.split("#")[0])
        assert not destination.startswith("../")
        assert destination in allowed, (
            f"public link escapes or is missing from archive: {target}"
        )
        local_links.append(destination)
    assert "release/public/paper-numbers.json" in local_links
    assert {"LICENSE", "DATASHEET.md", "ANNOTATION.md"}.issubset(local_links)
    assert "](claim-map.json)" not in public and "](numbers.md)" not in public


def test_public_markdown_relocation_preserves_numeric_text():
    raw = b"Rate 0.25, n=4; [claims](claim-map.json) [numbers](numbers.md) [license](../LICENSE)"
    transformed = public_markdown("paper.md", raw)
    assert b"Rate 0.25, n=4;" in transformed
    assert transformed.count(b"](paper-numbers.json)") == 2
    assert b"](../../LICENSE)" in transformed
    assert public_markdown("migration-report.md", raw) == raw
