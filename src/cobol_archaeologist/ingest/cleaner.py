"""Line-count-preserving preprocessor: EXEC-block masking and COPY REPLACING (Track A, T1.1).

Pipeline stage, not a workaround: raw CardDemo CICS/SQL/DLI source is
unparseable by every tree-sitter COBOL grammar without this pass (CLAUDE.md
locked decision #2). Ported from ``docs/reference/spike_parser.py``
(T0.5-validated preprocessing rules).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_EXEC_KIND = re.compile(r"\bEXEC\s+(CICS|SQL|DLI)\b", re.IGNORECASE)
_COPY_REPLACING = re.compile(r"\bCOPY\s+\S+\s+REPLACING\b", re.IGNORECASE)
_NOT_GLUED = re.compile(r"\bNOT=", re.IGNORECASE)
_VALUE_OPEN_QUOTE = re.compile(r"VALUE\s+(['\"])", re.IGNORECASE)

_KIND_BY_LANGUAGE = {"CICS": "exec_cics", "SQL": "exec_sql", "DLI": "exec_dli"}

_CONTINUE = "           CONTINUE"


class PreprocessError(ValueError):
    """An ``EXEC … END-EXEC`` or ``COPY … REPLACING`` block that never
    terminates before EOF.

    Masking such a block would emit blanked lines with no MaskedSpan recorded —
    silently losing source the AST and the LINK/XCTL side-channel both need, in
    violation of the line-fidelity invariant (CLAUDE.md rule 4). Malformed
    input is reported, never quietly mangled (review 2026-07-12, F6).
    """

    def __init__(self, kind: str, start_line: int) -> None:
        self.kind = kind
        self.start_line = start_line
        super().__init__(
            f"unterminated {kind} block opened at line {start_line}: "
            f"reached EOF without {'END-EXEC' if kind.startswith('exec') else 'a terminating period'}"
        )


class MaskedSpan(BaseModel):
    """A masked region of source; ``original_text`` is verbatim (T1.2 LINK/XCTL reads it)."""

    kind: str = Field(pattern="^(exec_cics|exec_sql|exec_dli|copy_replacing)$")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    original_text: str


class PreprocessResult(BaseModel):
    text: str
    masked_spans: list[MaskedSpan]


def _is_comment(line: str) -> bool:
    return len(line) > 6 and line[6] in ("*", "/")


def _is_continuation(line: str) -> bool:
    return len(line) > 6 and line[6] == "-"


def _body(line: str) -> str:
    return line[7:72] if len(line) > 7 else ""


def _fix_glued_not(line: str) -> str:
    """Normalize ``NOT=`` (no space) to ``NOT =``.

    DECISION: the vendored grammar (pinned, never patched) fails to parse the
    relational operator when glued to NOT (see docs/tasks/T1.1-work-order.md,
    CBACT04C.cbl:194). This is a one-space insertion, not a masking op — the
    line count and semantics are unchanged, so it is not tracked as a
    MaskedSpan (no downstream consumer needs the original spacing back).
    """
    if _is_comment(line) or not _NOT_GLUED.search(_body(line)):
        return line
    content_end = min(len(line), 72)
    fixed_body = _NOT_GLUED.sub("NOT =", line[7:content_end])
    return line[:7] + fixed_body + line[content_end:]


def preprocess(source: str) -> PreprocessResult:
    lines = source.splitlines()
    out: list[str] = []
    masked_spans: list[MaskedSpan] = []

    in_exec = False
    in_copy = False
    span_kind = ""
    span_start = 0
    span_lines: list[str] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        idx = i + 1  # 1-indexed original line number
        body = _body(line)
        comment = _is_comment(line)
        upper = body.upper()

        if in_exec:
            span_lines.append(line)
            if "END-EXEC" in upper:
                in_exec = False
                terminal = upper.rstrip().endswith(".")
                out.append(_CONTINUE + "." if terminal else "")
                masked_spans.append(
                    MaskedSpan(
                        kind=span_kind,
                        start_line=span_start,
                        end_line=idx,
                        original_text="\n".join(span_lines),
                    )
                )
            else:
                out.append("")
            i += 1
            continue

        if in_copy:
            span_lines.append(line)
            if body.rstrip().endswith("."):
                in_copy = False
                out.append(_CONTINUE + ".")
                masked_spans.append(
                    MaskedSpan(
                        kind="copy_replacing",
                        start_line=span_start,
                        end_line=idx,
                        original_text="\n".join(span_lines),
                    )
                )
            else:
                out.append("")
            i += 1
            continue

        if not comment:
            # DECISION: a genuine COBOL alphanumeric-literal continuation (col 7
            # '-') defeats this grammar even on valid syntax (see
            # docs/tasks/T1.1-work-order.md, CBSTM03A.CBL:157-158) — the grammar's
            # scanner cannot resume a literal across a continuation line. The
            # DATA DIVISION literal's exact text is not consumed downstream by
            # any T1.x tool, so splice the continued literal into a short
            # placeholder that preserves the level number / data-name and just
            # closes the string, and blank the continuation line(s).
            if i + 1 < n and _is_continuation(lines[i + 1]):
                j = i + 1
                while j < n and _is_continuation(lines[j]):
                    j += 1
                open_match = _VALUE_OPEN_QUOTE.search(body)
                if open_match:
                    quote_char = open_match.group(1)
                    prefix = line[:7] + body[: open_match.end()]
                    last_body = _body(lines[j - 1])
                    terminal = last_body.rstrip().endswith(".")
                    out.append(prefix + "X" + quote_char + ("." if terminal else ""))
                    for _ in range(i + 1, j):
                        out.append("")
                    i = j
                    continue

            m = _EXEC_KIND.search(body)
            if m:
                kind = _KIND_BY_LANGUAGE[m.group(1).upper()]
                if "END-EXEC" in upper:
                    terminal = upper.rstrip().endswith(".")
                    out.append(_CONTINUE + "." if terminal else _CONTINUE)
                    masked_spans.append(
                        MaskedSpan(
                            kind=kind,
                            start_line=idx,
                            end_line=idx,
                            original_text=line,
                        )
                    )
                else:
                    in_exec = True
                    span_kind = kind
                    span_start = idx
                    span_lines = [line]
                    out.append(_CONTINUE)
                i += 1
                continue

            if _COPY_REPLACING.search(body):
                if body.rstrip().endswith("."):
                    out.append(_CONTINUE + ".")
                    masked_spans.append(
                        MaskedSpan(
                            kind="copy_replacing",
                            start_line=idx,
                            end_line=idx,
                            original_text=line,
                        )
                    )
                else:
                    in_copy = True
                    span_start = idx
                    span_lines = [line]
                    out.append("")
                i += 1
                continue

        out.append(_fix_glued_not(line))
        i += 1

    if in_exec:
        raise PreprocessError(span_kind, span_start)
    if in_copy:
        raise PreprocessError("copy_replacing", span_start)

    text = "\n".join(out) + "\n"
    assert len(text.splitlines()) == len(lines), (
        f"line count invariant violated: {len(text.splitlines())} != {len(lines)}"
    )
    return PreprocessResult(text=text, masked_spans=masked_spans)
