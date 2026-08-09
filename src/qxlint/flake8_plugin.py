"""flake8 plugin.

flake8 owns selection, suppression and output, so this plugin only yields
findings. Two deliberate differences from the standalone CLI:

* flake8 adds one to the column itself, and its columns are byte based like the
  rest of flake8. The plugin therefore yields the raw ``col_offset`` semantics
  flake8 expects, while the CLI and SARIF emit character columns.
* ``# noqa`` is handled by flake8, so the plugin does not filter it again.

Notebooks are not reachable through flake8; use the qxlint CLI or nbqa for those.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from qxlint import __version__
from qxlint.config import ConfigCache, ConfigError, resolve_profile
from qxlint.diagnostics import Finding, SourceLocation
from qxlint.engine import analyse_text
from qxlint.registry import tiers
from qxlint.source import byte_offset_to_column

NAME = "qxlint"


class QxlintFlake8Plugin:
    """flake8 entry point registered under the ``QXL`` prefix."""

    name = NAME
    version = __version__

    def __init__(self, tree: ast.AST, filename: str, lines: list[str] | None = None) -> None:
        self._tree = tree
        self._filename = filename
        self._lines = lines

    def run(self) -> Iterator[tuple[int, int, str, type[Any]]]:
        text = "".join(self._lines) if self._lines else _read(self._filename)
        if text is None:
            return

        path = Path(self._filename)
        cache = ConfigCache()
        try:
            config = cache.for_path(path)
        except ConfigError:
            return
        profile = resolve_profile(config)
        enabled = config.enabled_codes(tiers())

        for finding in analyse_text(
            text, display_path=self._filename, profile=profile, enabled=enabled
        ):
            yield _to_flake8(finding, text)


def _read(filename: str) -> str | None:
    import tokenize

    try:
        with tokenize.open(filename) as handle:
            return handle.read()
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _to_flake8(finding: Finding, text: str) -> tuple[int, int, str, type[Any]]:
    location = finding.location
    line = getattr(location, "line", 1)
    column = getattr(location, "column", 1)
    if isinstance(location, SourceLocation):
        column = _to_byte_column(text, line, column)
    return line, max(column - 1, 0), f"{finding.rule} {finding.message}", QxlintFlake8Plugin


def _to_byte_column(text: str, line: int, column: int) -> int:
    """Convert a character column back to the byte column flake8 reports."""
    lines = text.splitlines()
    if not 1 <= line <= len(lines):
        return column
    prefix = lines[line - 1][: column - 1]
    return len(prefix.encode("utf-8")) + 1


__all__ = ["QxlintFlake8Plugin", "byte_offset_to_column"]
