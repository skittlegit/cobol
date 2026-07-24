"""T3.5 StubToolLayer gates: structural and semantic ToolLayer parity."""

from pathlib import Path

import pytest

from cobol_archaeologist.agent.stub_tools import StubToolLayer
from cobol_archaeologist.tool_types import (
    CODE_CAP_LINES,
    CopybookExpansion,
    DataLayout,
    GrepResult,
    NodeRef,
    ParagraphView,
    ProgramView,
    RegSearchHit,
    RunResult,
    Slice,
    ToolLayer,
    VariableTrace,
)
from cobol_archaeologist.tools import ToolLookupError

FIX = Path(__file__).resolve().parent / "fixtures" / "agent"


@pytest.fixture()
def stub() -> StubToolLayer:
    return StubToolLayer(FIX / "corpus")


def test_stub_is_runtime_tool_layer(stub):
    assert isinstance(stub, ToolLayer)
    assert isinstance(StubToolLayer(), ToolLayer)


def test_every_method_returns_normative_models(stub):
    assert isinstance(stub.read_paragraph("LATEFEE1", "2000-ASSESS"), ParagraphView)
    assert isinstance(stub.read_program("LATEFEE1"), ProgramView)
    assert all(isinstance(x, NodeRef) for x in stub.find_callers("LATEFEE1", "2000-ASSESS"))
    assert all(isinstance(x, NodeRef) for x in stub.find_callees("LATEFEE1", "1000-MAIN"))
    assert isinstance(stub.trace_variable("WS-TOTAL-AMT-DUE"), VariableTrace)
    assert isinstance(stub.slice_on("WS-TOTAL-AMT-DUE"), Slice)
    assert isinstance(stub.resolve_copybook("LATECFG"), CopybookExpansion)
    assert isinstance(stub.get_data_layout("WS-STMT-REC"), DataLayout)
    assert isinstance(stub.grep("late"), GrepResult)
    assert isinstance(stub.run_cobol("DISPLAY 'OK'"), RunResult)
    assert all(isinstance(x, RegSearchHit) for x in stub.search_regulations("late charge"))


def test_original_source_paragraph_cap_and_refetch_pointer(stub):
    view = stub.read_paragraph("LONGREAD", "2000-LONG")
    assert view.truncated is True
    assert len(view.code.splitlines()) == CODE_CAP_LINES
    assert view.ref.line_end - view.ref.line_start + 1 > CODE_CAP_LINES
    # The paragraph header itself is source line 1 of the 60-line cap.
    assert "LINE-59" in view.code
    assert "LINE-60" not in view.code


def test_copybook_cap_and_line_map_keep_full_source_pointer(stub):
    expansion = stub.resolve_copybook("latecfg")
    assert expansion.truncated is True
    assert len(expansion.text.splitlines()) == CODE_CAP_LINES
    assert expansion.line_map[-1].expanded_end == 65
    assert expansion.line_map[-1].source_file.endswith("LATECFG.cpy")


def test_lookup_error_and_leaf_sentinels_match_real_layer(stub):
    with pytest.raises(ToolLookupError):
        stub.read_program("DOES-NOT-EXIST")
    with pytest.raises(ToolLookupError):
        stub.read_paragraph("LATEFEE1", "DOES-NOT-EXIST")
    assert stub.find_callers("LATEFEE1", "DOES-NOT-EXIST") == []
    assert stub.find_callees("LATEFEE1", "DOES-NOT-EXIST") == []
    with pytest.raises(ToolLookupError):
        stub.find_callers("DOES-NOT-EXIST", "1000-MAIN")


def test_external_program_entry_uses_empty_paragraph_sentinel(stub):
    assert stub.find_callees("CALLHOST", "1000-MAIN") == [
        NodeRef(program="EXTBANK", paragraph="")
    ]


def test_tier1_unavailable_is_a_result_not_an_exception(stub):
    result = stub.run_cobol("EXEC CICS SEND MAP('X') END-EXEC")
    assert result.compiled_ok is False
    assert result.exit_code is None
    assert "unavailable" in result.stderr.lower()


def test_case_insensitive_original_source_search_and_scope(stub):
    grep = stub.grep("ws-total-amt-due")
    assert grep.matches
    assert all(m.program == "LATEFEE1" for m in grep.matches)
    scoped = stub.trace_variable("ws-total-amt-due", program="latefee1")
    assert scoped.scoped_program == "LATEFEE1"
    assert scoped.sites


def test_unknown_trace_scope_and_fixture_misses_raise(stub):
    with pytest.raises(ToolLookupError):
        stub.trace_variable("WS-X", program="MISSING")
    with pytest.raises(ToolLookupError):
        stub.resolve_copybook("MISSING")
    with pytest.raises(ToolLookupError):
        stub.get_data_layout("MISSING")
