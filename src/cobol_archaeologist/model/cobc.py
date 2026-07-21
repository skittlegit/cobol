"""GnuCOBOL discovery, compatibility checks, and evidence metadata.

BL-9 establishes GnuCOBOL 3.2.0 as the version of record while retaining a
portable compatibility floor for supported Ubuntu LTS environments.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache


MIN_SUPPORTED = (3, 1, 2)
MAX_MAJOR_EXCLUSIVE = 4
VERSION_OF_RECORD = "3.2.0"
SUPPORTED_RANGE = ">=3.1.2,<4"

_VERSION_RE = re.compile(r"\b(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?")


class CobcVersionError(RuntimeError):
    """Raised when ``cobc`` cannot provide a supported version."""


@dataclass(frozen=True)
class CobcInfo:
    """Observed compiler identity suitable for reproducibility evidence."""

    binary: str
    banner: str
    version: tuple[int, int, int]

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)


def find_cobc() -> str | None:
    """Return the configured compiler, preferring the explicit override."""

    return os.environ.get("COBC") or shutil.which("cobc")


def parse_cobc_version(banner: str) -> tuple[int, int, int]:
    """Extract a normalized three-part version from the first banner line."""

    if "gnucobol" not in banner.casefold():
        raise CobcVersionError(f"compiler banner is not GnuCOBOL: {banner!r}")
    match = _VERSION_RE.search(banner)
    if match is None:
        raise CobcVersionError(f"could not parse the GnuCOBOL version from {banner!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch") or 0),
    )


def require_supported_cobc(
    version: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Fail closed unless ``version`` satisfies the locked BL-9 policy."""

    if not (MIN_SUPPORTED <= version < (MAX_MAJOR_EXCLUSIVE, 0, 0)):
        actual = ".".join(str(part) for part in version)
        raise CobcVersionError(
            f"unsupported GnuCOBOL {actual}; required {SUPPORTED_RANGE} "
            f"(version of record: {VERSION_OF_RECORD})"
        )
    return version


@lru_cache(maxsize=None)
def inspect_cobc(binary: str) -> CobcInfo:
    """Run and validate ``cobc --version`` once for each compiler path."""

    try:
        completed = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CobcVersionError(f"could not inspect GnuCOBOL at {binary!r}: {exc}") from exc

    output = (completed.stdout or "") + (completed.stderr or "")
    banner = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if completed.returncode != 0 or not banner:
        raise CobcVersionError(
            f"{binary!r} --version failed with exit code {completed.returncode}"
        )
    version = require_supported_cobc(parse_cobc_version(banner))
    return CobcInfo(binary=binary, banner=banner, version=version)


def compiler_manifest() -> dict[str, object]:
    """Describe the actual compiler available to a benchmark build."""

    binary = find_cobc()
    common: dict[str, object] = {
        "name": "GnuCOBOL cobc",
        "supported_range": SUPPORTED_RANGE,
        "version_of_record": VERSION_OF_RECORD,
    }
    if binary is None:
        return {
            **common,
            "banner": None,
            "version": None,
            "provenance": "unavailable",
        }
    info = inspect_cobc(binary)
    return {
        **common,
        "banner": info.banner,
        "version": info.version_text,
        "provenance": "observed_by_cobc_version",
    }
