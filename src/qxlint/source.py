"""Source text handling and AST column conversion."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cached_property

from qxlint.diagnostics import NotebookLocation, SourceLocation


def too_deep_to_parse(filename: str) -> SyntaxError:
    """Turn a parser stack overflow into the same answer as any other bad file.

    The parser recurses once per nesting level, so a machine generated
    expression can exhaust the stack. Where that happens is an interpreter
    detail: a 40 KB chain of ``+`` raises on 3.11 to 3.13 and parses fine on
    3.14. Reporting it as unparsable keeps one commit producing one answer on
    every supported version, and keeps one unreadable file from ending the run.
    """
    error = SyntaxError("expression nests too deeply for this interpreter to parse")
    error.filename = filename
    error.lineno = 1
    error.offset = 1
    return error


def byte_offset_to_column(line_text: str, byte_offset: int) -> int:
    """Convert a 0-based UTF-8 byte offset into a 1-based character column.

    ``ast`` reports ``col_offset`` in UTF-8 bytes, so adding one is wrong for any
    line containing non-ASCII text.
    """
    if byte_offset <= 0:
        return 1
    encoded = line_text.encode("utf-8")
    if byte_offset >= len(encoded):
        return len(line_text) + 1
    return len(encoded[:byte_offset].decode("utf-8", errors="replace")) + 1


@dataclass(frozen=True)
class SourceFile:
    """A parsed unit of Python source.

    ``cell_index`` is set only for notebook cells. ``column_offset`` is a uniform
    leading indent that was removed to make the cell parseable, added back so a
    reported column still points at the original text.
    """

    path: str
    text: str
    cell_index: int | None = None
    physical_line_of: tuple[int | None, ...] = ()
    column_offset: int = 0

    @cached_property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    def line_text(self, line: int) -> str:
        if 1 <= line <= len(self.lines):
            return self.lines[line - 1]
        return ""

    def column_of(self, line: int, col_offset: int) -> int:
        """Character column, corrected for any indent stripped before parsing."""
        return byte_offset_to_column(self.line_text(line), col_offset) + self.column_offset

    def physical_line(self, line: int) -> int | None:
        if not self.physical_line_of:
            return None
        if 1 <= line <= len(self.physical_line_of):
            return self.physical_line_of[line - 1]
        return None

    def location(self, node: ast.AST) -> SourceLocation | NotebookLocation:
        """Build a user facing location from an AST node."""
        line = getattr(node, "lineno", 1)
        col = self.column_of(line, getattr(node, "col_offset", 0))
        end_line = getattr(node, "end_lineno", None)
        end_col_offset = getattr(node, "end_col_offset", None)
        end_col = (
            self.column_of(end_line, end_col_offset)
            if end_line is not None and end_col_offset is not None
            else None
        )
        if self.cell_index is None:
            return SourceLocation(self.path, line, col, end_line, end_col)
        return NotebookLocation(
            path=self.path,
            cell_index=self.cell_index,
            line=line,
            column=col,
            end_line=end_line,
            end_column=end_col,
            physical_line=self.physical_line(line),
        )
