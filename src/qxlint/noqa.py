"""`# noqa` suppression, read from real comment tokens.

``ast`` discards comments, so the map is built with ``tokenize``. Using tokens
rather than a line regex means a ``# noqa`` inside a string literal is ignored.

Accepted forms, matching flake8:

* ``# noqa`` suppresses every rule on the line.
* ``# noqa: QXL101`` or ``# noqa: QXL101, QXL103`` suppresses those codes only.
* a listed code is a **prefix**, so ``# noqa: QXL1`` covers QXL101 and QXL103.

The keyword is case insensitive and codes are normalised to upper case.
Separators may be commas, whitespace, or both. A ``noqa:`` with no readable code
after it falls back to a bare suppression, again matching flake8.

Prefix matching is what flake8 does, and it is what qxlint's own ``--select``
and ``--ignore`` already did. Exact matching here meant the same file with the
same comment was silent under ``flake8 --select=QXL`` and still reported by the
``qxlint`` command, which is the one thing two entry points to the same rules
must not do.
"""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass

NOQA_RE = re.compile(
    r"#\s*noqa(?::[\s]?(?P<codes>([A-Z][A-Z]*[0-9]+(?:[,\s]+)?)+))?",
    re.IGNORECASE,
)
CODE_SEP_RE = re.compile(r"[,\s]+")

ALL = "__all__"


@dataclass(frozen=True)
class NoqaMap:
    """Line number to suppressed codes. The sentinel ``ALL`` means every code."""

    lines: dict[int, frozenset[str]]

    def suppresses(self, line: int, code: str) -> bool:
        codes = self.lines.get(line)
        if codes is None:
            return False
        if ALL in codes:
            return True
        upper = code.upper()
        return any(upper.startswith(entry) for entry in codes)

    @property
    def is_empty(self) -> bool:
        return not self.lines


def parse_noqa(source: str) -> NoqaMap:
    """Build the suppression map for one unit of source text.

    A tokenize error means the file does not tokenize, in which case the parse
    step reports the syntax error and no suppression is available.
    """
    lines: dict[int, frozenset[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        comments = [tok for tok in tokens if tok.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return NoqaMap(lines=lines)

    for tok in comments:
        match = NOQA_RE.search(tok.string)
        if match is None:
            continue
        line = tok.start[0]
        raw = match.group("codes")
        codes = _split_codes(raw)
        existing = lines.get(line, frozenset())
        lines[line] = existing | codes
    return NoqaMap(lines=lines)


def _split_codes(raw: str | None) -> frozenset[str]:
    if raw is None:
        return frozenset({ALL})
    parts = {part.upper() for part in CODE_SEP_RE.split(raw.strip()) if part}
    if not parts:
        return frozenset({ALL})
    return frozenset(parts)
