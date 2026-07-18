"""Checkout-aware access to runtime assets bundled in distributions."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path, PurePosixPath


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)


def asset_directory(checkout_relative: str, package_relative: str) -> Path:
    """Resolve an asset directory from a checkout or an installed wheel.

    Editable installs keep using the canonical repository copy. Built
    distributions carry the same assets under ``cobol_archaeologist/_assets``.
    ``as_file`` also makes this work for non-filesystem importers by retaining
    the extracted directory until process exit.
    """
    checkout = _REPO_ROOT.joinpath(*PurePosixPath(checkout_relative).parts)
    if checkout.is_dir():
        return checkout

    resource = files("cobol_archaeologist").joinpath(
        *PurePosixPath(package_relative).parts
    )
    if not resource.is_dir():
        raise FileNotFoundError(
            f"required cobol-archaeologist asset directory is missing: {package_relative}"
        )
    return Path(_RESOURCE_STACK.enter_context(as_file(resource)))
