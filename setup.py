"""Setuptools hooks for runtime assets that remain canonical outside src/."""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).parent
ASSET_COPIES = (
    (
        ROOT / "vendor" / "tree-sitter-cobol",
        Path("cobol_archaeologist/_assets/tree-sitter-cobol"),
    ),
    (
        ROOT / "data" / "regulations" / "sources",
        Path("cobol_archaeologist/_assets/regulations/sources"),
    ),
)


class build_py(_build_py):
    """Copy canonical runtime assets into the built import package."""

    def run(self) -> None:
        super().run()
        build_root = Path(self.build_lib)
        for source, relative_target in ASSET_COPIES:
            shutil.copytree(source, build_root / relative_target, dirs_exist_ok=True)
        regulations = build_root / "cobol_archaeologist/_assets/regulations"
        regulations.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "data/regulations/clauses.jsonl", regulations)


setup(cmdclass={"build_py": build_py})
