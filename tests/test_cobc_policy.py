"""BL-9 gate: one enforced, provenance-aware GnuCOBOL version policy."""

from __future__ import annotations

from pathlib import Path

import pytest

import cobol_archaeologist.model.cobc as cobc_policy
from cobol_archaeologist.model.cobc import (
    SUPPORTED_RANGE,
    VERSION_OF_RECORD,
    CobcInfo,
    CobcVersionError,
    parse_cobc_version,
    require_supported_cobc,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("banner", "expected"),
    [
        ("cobc (GnuCOBOL) 3.1.2.0", (3, 1, 2)),
        ("cobc (GnuCOBOL) 3.2.0", (3, 2, 0)),
        ("GnuCOBOL compiler 3.9", (3, 9, 0)),
    ],
)
def test_parse_cobc_version(banner, expected):
    assert parse_cobc_version(banner) == expected


def test_parse_cobc_version_rejects_another_compiler_banner():
    with pytest.raises(CobcVersionError, match="not GnuCOBOL"):
        parse_cobc_version("unrelated compiler 3.2.0")


@pytest.mark.parametrize("version", [(3, 1, 2), (3, 2, 0), (3, 99, 0)])
def test_supported_cobc_three_series(version):
    assert require_supported_cobc(version) == version


@pytest.mark.parametrize("version", [(3, 1, 1), (2, 2, 0), (4, 0, 0)])
def test_unsupported_cobc_versions_fail_closed(version):
    with pytest.raises(CobcVersionError, match=SUPPORTED_RANGE):
        require_supported_cobc(version)


def test_setup_script_cannot_drift_from_runtime_policy():
    script = (ROOT / "scripts" / "setup_cobc.sh").read_text(encoding="utf-8")

    assert f'MIN_SUPPORTED="{SUPPORTED_RANGE.split(",")[0][2:]}"' in script
    assert f'VERSION_OF_RECORD="{VERSION_OF_RECORD}"' in script
    assert 'MAX_MAJOR_EXCLUSIVE="4"' in script
    assert "sudo apt-get install -y gnucobol\n" in script
    assert "gnucobol3" not in script


def test_compiler_manifest_records_observed_version(monkeypatch):
    monkeypatch.setattr(cobc_policy, "find_cobc", lambda: "/tools/cobc")
    monkeypatch.setattr(
        cobc_policy,
        "inspect_cobc",
        lambda _binary: CobcInfo(
            binary="/tools/cobc",
            banner="cobc (GnuCOBOL) 3.2.0",
            version=(3, 2, 0),
        ),
    )

    assert cobc_policy.compiler_manifest() == {
        "name": "GnuCOBOL cobc",
        "supported_range": SUPPORTED_RANGE,
        "version_of_record": VERSION_OF_RECORD,
        "banner": "cobc (GnuCOBOL) 3.2.0",
        "version": "3.2.0",
        "provenance": "observed_by_cobc_version",
    }
