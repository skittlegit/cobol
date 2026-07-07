"""Gate for tool_types.py (CONTRACT.md Part 1 normative form)."""
from cobol_archaeologist import tool_types as tt


def test_roundtrip_slice():
    s = tt.Slice(
        variable="WS-YEARS-SINCE-KYC",
        scoped_program=None,
        statements=[tt.SliceStatement(
            ref=tt.SourceRef(program="KYCUPD", paragraph="3000-CHECK-KYC-AGE",
                             line_start=148, line_end=148),
            text="IF WS-YEARS-SINCE-KYC > 5")],
        paragraphs=[tt.NodeRef(program="KYCUPD", paragraph="3000-CHECK-KYC-AGE")],
        is_interprocedural=False,
    )
    assert tt.Slice.model_validate_json(s.model_dump_json()) == s


def test_protocol_is_runtime_checkable():
    class _Fake:
        def read_paragraph(self, program, name): ...
        def read_program(self, program): ...
        def find_callers(self, program, para): ...
        def find_callees(self, program, para): ...
        def trace_variable(self, var, program=None): ...
        def slice_on(self, var, program=None): ...
        def resolve_copybook(self, name): ...
        def get_data_layout(self, record): ...
        def grep(self, pattern): ...
        def run_cobol(self, snippet, inputs=None): ...
        def search_regulations(self, query): ...

    assert isinstance(_Fake(), tt.ToolLayer)


def test_field_layout_recursion():
    leaf = tt.FieldLayout(name="ACCT-ID", level=5, pic="9(11)")
    root = tt.FieldLayout(name="ACCOUNT-RECORD", level=1, children=[leaf])
    assert tt.FieldLayout.model_validate(root.model_dump()).children[0].pic == "9(11)"
