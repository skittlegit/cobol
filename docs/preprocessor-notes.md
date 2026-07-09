# Preprocessor notes — T1.1

Record of every preprocessor rule added beyond the T0.5 spike, per CLAUDE.md
rule 4 ("if the grammar cannot represent something, extend the preprocessor,
don't patch `vendor/`, and log the pattern here"). Each entry: the corpus
evidence, the rule, and its regression fixture.

## Rule: `NOT=` (no space) normalized to `NOT =`

**Evidence:** `CBACT04C.cbl:194` — `IF TRANCAT-ACCT-ID NOT= WS-LAST-ACCT-NUM`.
Valid COBOL (the space around a relational operator is optional), but the
pinned grammar (`e99dbdc3d800…`) cannot parse the glued form — it produces one
`ERROR` node that swallows the rest of the PROCEDURE DIVISION (lines 194–648
in the raw parse).

**Rule:** on any non-comment line, insert one space between `NOT` and a glued
`=`. A pure token-spacing fix — no lines are masked, no `MaskedSpan` is
recorded (nothing needs to reverse it; T1.2/T1.3 never need the original
spacing).

**Regression fixture:** `tests/test_cleaner.py::test_not_equal_glued_normalized`.

## Rule: continued alphanumeric literal (col 7 `-`) spliced to a placeholder

**Evidence:** `CBSTM03A.CBL:157-158` and 10 further sites — long HTML-template
`88`-level `VALUE` literals continued across a line via the standard COBOL
column-7 `-` continuation indicator, e.g.:

```
             88  HTML-L08 VALUE '<table  align="center" frame="box" styl
      -             'e="width:70%; font:12px Segoe UI,sans-serif;">'.
```

The pinned grammar's scanner cannot resume a string literal across a
continuation line — this produces one `ERROR` node per file that swallows the
rest of DATA DIVISION up to PROCEDURE DIVISION (harmless to paragraph spans,
but violates the "zero ERROR nodes" gate).

**Rule:** when a line's continuation (col 7 `-`) follows a `VALUE '...`/`VALUE
"..."` clause whose literal is not closed by end of line, splice the whole
continued literal to `<same prefix through the opening quote>X<quote>[.]` —
preserving the level number and data/condition name, closing the string with a
placeholder character, and blanking the continuation line(s) (same
interior-blank convention as `EXEC` masking). The literal's exact text is not
consumed by any T1.x tool (it is a DATA DIVISION display constant, not
procedure logic), so the placeholder is safe. Not recorded as a `MaskedSpan`
(closed to `exec_cics|exec_sql|exec_dli|copy_replacing` per the T1.1 work
order) — no downstream consumer needs the original literal text back.

**Regression fixture:** `tests/test_cleaner.py::test_continued_literal_spliced`.
