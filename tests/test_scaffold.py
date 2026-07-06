"""T1.0 gate: package imports, pinned grammar parses, corpus checkout present."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAMMAR_PIN = "e99dbdc3d800d5fa2796476efd60af91f6b43d93"


def test_package_importable():
    import cobol_archaeologist  # noqa: F401


def test_grammar_smoke_parse():
    from tree_sitter import Parser

    from cobol_archaeologist.parser._grammar import get_language

    language = get_language()
    parser = Parser()
    parser.set_language(language)
    tree = parser.parse(b"       IDENTIFICATION DIVISION.")
    assert tree.root_node is not None


def test_vendored_grammar_pin():
    pinned_file = REPO_ROOT / "vendor" / "tree-sitter-cobol" / "PINNED"
    assert pinned_file.read_text(encoding="ascii").strip() == GRAMMAR_PIN


@pytest.mark.skipif(
    not (REPO_ROOT / "data" / "corpora").is_dir(),
    reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)
def test_carddemo_checkout_contains_cbtrn02c():
    carddemo = REPO_ROOT / "data" / "corpora" / "carddemo"
    assert (carddemo / "app" / "cbl" / "CBTRN02C.cbl").is_file()
