"""Jupyter notebook extraction and the IPython magic policy.

Blanking a magic line keeps the parser happy but lies to the analyser: ``%run``
can rebind any name, so a blanked ``%run`` would leave stale facts and produce a
false positive. Magics are therefore sorted into three groups.

* **Python body.** ``%%time``, ``%%capture``, ``%time``. The header is dropped
  and the body is analysed normally.
* **Namespace barrier.** ``%run``, ``%load``, ``%paste``, ``%pylab`` and every
  unrecognised magic. The line becomes a barrier call, which pushes every
  binding and every object fact to UNKNOWN.
* **Non Python body.** ``%%bash``, ``%%sql``, ``%%html`` and friends. The whole
  cell is dropped and replaced by a barrier, because the body is not Python.

Shell escapes (``!cmd``) cannot touch the Python namespace and are simply
dropped, except for the capture form ``out = !cmd`` which binds a name to an
unknown value.

Every replacement preserves the line count, so a reported line always matches
the line the user sees in the cell.

Automagic is handled only where it is decidable. ``pip install qiskit`` is not
valid Python, so a line naming a known magic that does not parse is read as the
magic IPython would run. A bare ``ls``, or ``cd /tmp``, is valid Python and is
left alone, which is the documented limit shared with nbqa.

Out of order interactive execution cannot be reconstructed. Analysis assumes
cells run top to bottom in textual order.
"""

from __future__ import annotations

import ast
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from qxlint.source import too_deep_to_parse

BARRIER_CALL = "__qxlint_barrier__()"
UNKNOWN_CALL = "__qxlint_unknown__()"

# A shell escape is `!` followed by a command, and a command is not an
# identifier: `!./run.sh`, `!/usr/bin/env python`, `!~/tool`, `!$HOME/tool` and
# `!"program name"` are all ordinary IPython. Requiring a letter after the `!`
# left those lines in place, and the cell was then reported as unparsable.
#
# `=` is excluded because a continuation line can legitimately start with `!=`:
#
#     if (a
#         != b):
#
# That only matters inside a cell that already fails to parse, since a cell that
# parses is never rewritten, but eating the line would hide the real error.
SHELL_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)!{1,2}[ \t]*[^\s=]")

# A magic name, unlike a shell command, really is an identifier.
MAGIC_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>%{1,2})(?P<name>[A-Za-z_]\w*)")
CAPTURE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<target>[A-Za-z_]\w*)\s*=\s*(!{1,2}|%)(?P<rest>.*)$"
)
HELP_RE = re.compile(r"^[ \t]*\??[\w.]+\?{1,2}[ \t]*$")

# Cell magics whose body is Python and can be analysed once the header is gone.
PYTHON_BODY_CELL_MAGICS = frozenset({"time", "capture", "prun", "debug"})

# Cell magics whose body is not Python at all.
NON_PYTHON_CELL_MAGICS = frozenset(
    {
        "bash",
        "sh",
        "script",
        "perl",
        "ruby",
        "js",
        "javascript",
        "html",
        "latex",
        "markdown",
        "md",
        "svg",
        "sql",
        "writefile",
        "file",
        "cython",
        "fortran",
        "pypy",
        "python2",
        "python3",
    }
)

# Line magics that only touch display or interpreter configuration.
SAFE_LINE_MAGICS = frozenset(
    {
        "matplotlib",
        "config",
        "colors",
        "xmode",
        "pprint",
        "precision",
        "autoreload",
        "load_ext",
        "reload_ext",
        "unload_ext",
        "env",
        "set_env",
        "cd",
        "pwd",
        "ls",
        "pip",
        "conda",
        "alias",
        "unalias",
        "bookmark",
        "history",
        "logstart",
        "logstop",
        "notebook",
        "gui",
        "pdb",
        "doctest_mode",
        "qtconsole",
        "connect_info",
        "lsmagic",
        "magic",
        "quickref",
        "who",
        "who_ls",
        "whos",
        "psource",
        "pfile",
        "pdef",
        "pdoc",
        "pinfo",
        "pinfo2",
    }
)

# Line magics that unwrap to a plain Python statement.
UNWRAP_LINE_MAGICS = frozenset({"time"})

# IPython rewrites `pip install qiskit` to `%pip install qiskit` when automagic
# is on, which it is by default. Only these two policies are recognised without
# the marker: both drop the line, so reading an ordinary syntax error as one of
# them cannot invent a fact. A line that parses as Python is never touched.
AUTOMAGIC_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<name>[A-Za-z_]\w*)(?P<rest>[ \t]+\S.*)$")
AUTOMAGIC_NAMES = SAFE_LINE_MAGICS | UNWRAP_LINE_MAGICS


LEADING_INDENT_RE = re.compile(r"^[ \t]+")


@dataclass(frozen=True, slots=True)
class PreparedCell:
    """One code cell, rewritten into parseable Python.

    ``index`` is 1-based and counts code cells only, matching nbqa.
    ``column_offset`` is the uniform leading indent that was stripped, added back
    to every reported column so it still points at the original text.
    """

    index: int
    text: str
    original: str
    transformed: bool
    column_offset: int = 0


@dataclass(frozen=True, slots=True)
class Notebook:
    path: str
    cells: tuple[PreparedCell, ...]


class NotebookError(Exception):
    """The file is not a readable notebook."""


def read_notebook(path: Path) -> Notebook:
    """Load a notebook and prepare every code cell for parsing.

    Every failure here is a NotebookError, which the engine turns into QXL000.
    Nothing may escape as an internal error: one unreadable notebook must not
    end the run for the rest of the tree.

    The encoding is UTF-8 only, matching nbformat, which is what actually opens
    these files. Verified against nbformat 5.11.0: a notebook written as
    cp1252, as UTF-16, or with a UTF-8 BOM is rejected there too. Accepting one
    here would mean reporting on a file Jupyter cannot load.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise NotebookError(f"cannot read notebook: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise NotebookError(f"notebook is not valid UTF-8: {exc}") from exc
    return parse_notebook_text(str(path), raw)


def parse_notebook_text(path: str, raw: str) -> Notebook:
    """Same as read_notebook for a notebook already in memory, such as a buffer."""
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NotebookError(f"invalid notebook JSON: {exc}") from exc
    except RecursionError as exc:
        raise NotebookError(f"notebook JSON nests too deeply to parse: {exc}") from exc
    return parse_notebook(path, document)


def parse_notebook(path: str, document: object) -> Notebook:
    if not isinstance(document, dict):
        raise NotebookError("notebook root is not an object")
    cells = document.get("cells")
    if not isinstance(cells, list):
        raise NotebookError("notebook has no cells array")

    prepared: list[PreparedCell] = []
    index = 0
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        index += 1
        source = _cell_source(cell.get("source"))
        text, offset, transformed = prepare_cell(source)
        prepared.append(
            PreparedCell(
                index=index,
                text=text,
                original=source,
                transformed=transformed,
                column_offset=offset,
            )
        )
    return Notebook(path=path, cells=tuple(prepared))


def _cell_source(source: object) -> str:
    """nbformat stores source as a string or as a list of lines with newlines kept."""
    if isinstance(source, str):
        return source
    if isinstance(source, list):
        return "".join(item for item in source if isinstance(item, str))
    return ""


def prepare_cell_source(source: str) -> tuple[str, bool]:
    """Return parseable Python for a cell, and whether anything was rewritten.

    A cell that already parses is left untouched, which keeps valid Python such
    as a continuation line starting with ``%`` safe from the magic rewriter.
    """
    text, _, transformed = prepare_cell(source)
    return text, transformed


def prepare_cell(source: str) -> tuple[str, int, bool]:
    """Parseable Python, the stripped leading indent, and whether it changed."""
    if _parses(source):
        return source, 0, False
    rewritten, offset = _neutralise(source)
    return rewritten, offset, rewritten != source


def _parses(source: str) -> bool:
    # parse_cell already turns a stack overflow into a SyntaxError, so a cell
    # that is too deep takes the same path as any other cell that does not parse.
    try:
        parse_cell(source)
    except (SyntaxError, ValueError):
        return False
    return True


def parse_cell(source: str, filename: str = "<cell>") -> ast.Module:
    """Parse a cell, allowing the top level ``await`` that notebooks permit.

    Warnings are suppressed because ``compile`` reports things like an invalid
    escape sequence as a SyntaxWarning on stderr, which would leak into the
    linter's own output for a file it is only reading.

    A cell that overflows the parser stack is reported as unparsable, the same
    as any other cell the parser cannot finish.
    """
    flags = ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            tree = compile(source, filename, "exec", flags, dont_inherit=True)
        except RecursionError as exc:
            raise too_deep_to_parse(filename) from exc
    assert isinstance(tree, ast.Module)
    return tree


def _neutralise(source: str) -> tuple[str, int]:
    lines = source.splitlines()
    if not lines:  # pragma: no cover
        # Unreachable: this runs only when the cell failed to parse, and the
        # only source with no lines is the empty string, which parses.
        return source, 0

    lines, offset = _strip_leading_indent(lines)

    cell_magic = _cell_magic_name(lines)
    if cell_magic is not None:
        if cell_magic in NON_PYTHON_CELL_MAGICS:
            return _blank_cell(lines), offset
        if cell_magic in PYTHON_BODY_CELL_MAGICS:
            lines = ["", *lines[1:]]
        else:
            return _blank_cell(lines), offset

    out = _neutralise_lines(lines)
    return "\n".join(out) + ("\n" if source.endswith("\n") else ""), offset


def _strip_leading_indent(lines: list[str]) -> tuple[list[str], int]:
    """Remove a uniform indent shared by the whole cell.

    IPython does this before executing, so a cell pasted with a leading space is
    valid there. Line count is preserved and the removed width is reported so
    columns can be corrected.
    """
    first = next((line for line in lines if line.strip()), None)
    if first is None:
        return lines, 0
    match = LEADING_INDENT_RE.match(first)
    if match is None:
        return lines, 0
    prefix = match.group(0)
    width = len(prefix)
    return [line[width:] if line.startswith(prefix) else line for line in lines], width


def _neutralise_lines(lines: list[str]) -> list[str]:
    """Rewrite magic and shell lines, following backslash continuations.

    A magic can span several lines with a trailing backslash. Dropping only the
    first line leaves the continuation behind as stray indented text, which is
    what made real notebooks fail to parse.
    """
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        replacement = _neutralise_line(line)
        out.append(replacement)
        if replacement != line and line.rstrip().endswith("\\"):
            index += 1
            while index < len(lines):
                out.append("")
                if not lines[index].rstrip().endswith("\\"):
                    break
                index += 1
        index += 1
    return out


def _cell_magic_name(lines: list[str]) -> str | None:
    for line in lines:
        if not line.strip():
            continue
        match = MAGIC_LINE_RE.match(line)
        if match is not None and match.group("marker") == "%%":
            return match.group("name").lower()
        return None
    return None


def _blank_cell(lines: list[str]) -> str:
    body = [BARRIER_CALL] + [""] * (len(lines) - 1)
    return "\n".join(body)


def _neutralise_line(line: str) -> str:
    if not line.strip():
        return line

    capture = CAPTURE_RE.match(line)
    if capture is not None and not _parses(line):
        return f"{capture.group('indent')}{capture.group('target')} = {UNKNOWN_CALL}"

    if HELP_RE.match(line) and not _parses(line):
        return _dropped("")

    shell = SHELL_LINE_RE.match(line)
    if shell is not None:
        return _dropped(shell.group("indent"))

    match = MAGIC_LINE_RE.match(line)
    if match is None:
        return _neutralise_automagic(line)

    indent = match.group("indent")
    marker = match.group("marker")
    name = match.group("name").lower()

    if marker == "%%":
        return f"{indent}{BARRIER_CALL}"
    if name in UNWRAP_LINE_MAGICS:
        rest = line[match.end() :].strip()
        return f"{indent}{rest}" if rest else _dropped(indent)
    if name in SAFE_LINE_MAGICS:
        return _dropped(indent)
    return f"{indent}{BARRIER_CALL}"


def _neutralise_automagic(line: str) -> str:
    automagic = AUTOMAGIC_LINE_RE.match(line)
    if automagic is None:
        return line
    name = automagic.group("name").lower()
    if name not in AUTOMAGIC_NAMES or _parses(line):
        return line
    indent = automagic.group("indent")
    if name in UNWRAP_LINE_MAGICS:
        return f"{indent}{automagic.group('rest').strip()}"
    return _dropped(indent)


def _dropped(indent: str) -> str:
    """A line that is removed entirely.

    An indented line becomes ``pass`` rather than a blank, because a magic can be
    the only statement in a block and a blank line would leave that block empty.
    """
    return f"{indent}pass" if indent else ""
