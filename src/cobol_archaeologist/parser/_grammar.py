"""Pinned tree-sitter COBOL grammar: build from vendor/, cache, load (Track A, T1.0)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from distutils.errors import CCompilerError, DistutilsError
from tree_sitter import Language

from cobol_archaeologist._resources import asset_directory

_CHECKOUT_ROOT = Path(__file__).resolve().parents[3]
_VENDOR_DIR = asset_directory(
    "vendor/tree-sitter-cobol",
    "_assets/tree-sitter-cobol",
)
if _VENDOR_DIR == _CHECKOUT_ROOT / "vendor" / "tree-sitter-cobol":
    _BUILD_DIR = _CHECKOUT_ROOT / "build"
else:
    _pin = (_VENDOR_DIR / "PINNED").read_text(encoding="ascii").strip()[:12]
    _cache_tag = sys.implementation.cache_tag or "python"
    _platform_tag = f"{sys.platform}-{platform.machine().lower()}"
    _BUILD_DIR = (
        Path(tempfile.gettempdir())
        / "cobol-archaeologist"
        / "grammar"
        / f"{_pin}-{_cache_tag}-{_platform_tag}"
    )
_LIB_NAME = (
    "tree_sitter_cobol.windows.so" if os.name == "nt" else "tree_sitter_cobol.so"
)
_LIB_PATH = _BUILD_DIR / _LIB_NAME

# The grammar's name in vendor/tree-sitter-cobol/src/grammar.json; the shared
# object exports the symbol tree_sitter_COBOL.
_LANGUAGE_NAME = "COBOL"


def _build_with_cc(lib_path: Path) -> None:
    # DECISION: fallback for hosts without MSVC. Language.build_library selects
    # its compiler via distutils, which on Windows only finds MSVC; the grammar
    # is plain C with no Python API, so any C compiler can produce the shared
    # object. Primary path stays Language.build_library per the work order.
    src_dir = _VENDOR_DIR / "src"
    sources = [src_dir / "parser.c"]
    if (src_dir / "scanner.c").exists():
        sources.append(src_dir / "scanner.c")
    cc = next(
        (found for name in ("cc", "gcc", "clang") if (found := shutil.which(name))),
        None,
    )
    if cc is None:
        raise RuntimeError(
            "cannot build the COBOL grammar: Language.build_library failed and "
            "no C compiler (cc/gcc/clang) is on PATH"
        )
    subprocess.run(
        [
            cc,
            "-shared",
            "-fPIC",
            "-O2",
            f"-I{src_dir}",
            *map(str, sources),
            "-o",
            str(lib_path),
        ],
        check=True,
        capture_output=True,
    )


def get_language() -> Language:
    """Return the pinned COBOL grammar, building it into build/ on first use.

    Idempotent: rebuilds only if the cached shared object is missing.
    """
    if not _LIB_PATH.exists():
        _BUILD_DIR.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            try:
                Language.build_library(str(_LIB_PATH), [str(_VENDOR_DIR)])
            except (
                CCompilerError,
                DistutilsError,
                OSError,
                RuntimeError,
                ValueError,
            ):
                _LIB_PATH.unlink(missing_ok=True)
                _build_with_cc(_LIB_PATH)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return Language(str(_LIB_PATH), _LANGUAGE_NAME)
