"""Parse and apply modification-only unified diffs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_HUNK_RE = re.compile(
    r"@@ -(?P<old>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new>\d+)(?:,(?P<new_count>\d+))? @@.*"
)


class PatchError(ValueError):
    """The patch is malformed, unsafe, or does not apply."""


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    body: tuple[str, ...]


@dataclass(frozen=True)
class FilePatch:
    path: str
    hunks: tuple[Hunk, ...]


def _path(raw: str, prefix: str) -> str:
    value = raw[len(prefix) :].split("\t", 1)[0].strip()
    if value == "/dev/null":
        raise PatchError("creating or deleting files is not allowed")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value or not value:
        raise PatchError(f"unsafe patch path {value!r}")
    return pure.as_posix()


def parse(text: str) -> tuple[FilePatch, ...]:
    lines = text.splitlines()
    patches: list[FilePatch] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith(("diff --git ", "index ")):
            index += 1
            continue
        if line.startswith(
            ("new file mode ", "deleted file mode ", "rename ", "Binary ")
        ):
            raise PatchError("a patch may only modify existing text files")
        if not line.startswith("--- "):
            raise PatchError(f"unexpected patch line: {line!r}")
        old = _path(line, "--- ")
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchError("missing +++ header")
        if _path(lines[index], "+++ ") != old:
            raise PatchError("renames are not allowed")
        index += 1
        hunks: list[Hunk] = []
        while index < len(lines) and lines[index].startswith("@@ "):
            match = _HUNK_RE.fullmatch(lines[index])
            if match is None:
                raise PatchError(f"invalid hunk header: {lines[index]!r}")
            old_count = int(match.group("old_count") or "1")
            new_count = int(match.group("new_count") or "1")
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].startswith(
                ("@@ ", "--- ", "diff --git ")
            ):
                row = lines[index]
                index += 1
                if row == r"\ No newline at end of file":
                    continue
                if not row.startswith((" ", "+", "-")):
                    raise PatchError(f"invalid hunk line: {row!r}")
                body.append(row)
            if (
                sum(r[0] in " -" for r in body) != old_count
                or sum(r[0] in " +" for r in body) != new_count
            ):
                raise PatchError("hunk line counts do not match its header")
            hunks.append(Hunk(int(match.group("old")), old_count, tuple(body)))
        if not hunks:
            raise PatchError(f"no hunks for {old!r}")
        patches.append(FilePatch(old, tuple(hunks)))
    if not patches:
        raise PatchError("the patch changes nothing")
    if len({p.path for p in patches}) != len(patches):
        raise PatchError("a file appears in more than one section")
    return tuple(patches)


def _apply_one(source: str, patch: FilePatch) -> tuple[str, set[int]]:
    original = source.splitlines()
    output: list[str] = []
    cursor = 0
    changed: set[int] = set()
    for hunk in patch.hunks:
        start = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if start < cursor or start > len(original):
            raise PatchError(f"overlapping or out-of-range hunk in {patch.path}")
        output.extend(original[cursor:start])
        cursor = start
        line_no = hunk.old_start
        last_removed: int | None = None
        for row in hunk.body:
            marker, content = row[0], row[1:]
            if marker in " -":
                if cursor >= len(original) or original[cursor] != content:
                    raise PatchError(f"context does not match {patch.path}:{line_no}")
                if marker == " ":
                    output.append(content)
                    last_removed = None
                else:
                    changed.add(line_no)
                    last_removed = line_no
                cursor += 1
                line_no += 1
            else:
                output.append(content)
                changed.add(last_removed or min(max(line_no, 1), max(len(original), 1)))
    output.extend(original[cursor:])
    rendered = "\n".join(output) + ("\n" if source.endswith("\n") else "")
    return rendered, changed


def apply(
    files: dict[str, str], text: str
) -> tuple[dict[str, str], dict[str, set[int]]]:
    """Return the patched files and the original line numbers each change touches."""

    patched = dict(files)
    changed: dict[str, set[int]] = {}
    for file_patch in parse(text):
        if file_patch.path not in files:
            raise PatchError(f"patch targets an unknown file {file_patch.path!r}")
        patched[file_patch.path], changed[file_patch.path] = _apply_one(
            files[file_patch.path], file_patch
        )
    if patched == files:
        raise PatchError("the patch does not change any line")
    return patched, changed
