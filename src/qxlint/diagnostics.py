"""Finding and location model shared by both engines.

Coordinate contract, applied everywhere outside the AST adapter:

* ``line`` is 1-based.
* ``column`` is a 1-based character column, not a byte offset.
* ``end_line`` / ``end_column`` are 1-based and the end column is exclusive.

``ast`` reports 0-based UTF-8 byte offsets, so every AST column passes through
:func:`qxlint.source.byte_offset_to_column` before it reaches a Finding.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal


class Severity(enum.Enum):
    """User facing severity, mapped to SARIF levels on export."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "note"


class Tier(enum.Enum):
    """Whether a rule runs unless disabled, or only when opted in."""

    DEFAULT = "default"
    PREVIEW = "preview"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Position inside a ``.py`` file."""

    path: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class NotebookLocation:
    """Position inside a ``.ipynb`` code cell.

    ``cell_index`` is 1-based and counts code cells only, matching nbqa.
    ``line`` is 1-based within that cell. ``physical_line`` is the line in the
    notebook JSON when it can be recovered, otherwise None.
    """

    path: str
    cell_index: int
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None
    physical_line: int | None = None
    physical_column: int | None = None

    def render(self) -> str:
        return f"{self.path}:cell{self.cell_index}:{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class InstructionStep:
    """One hop in a circuit instruction path.

    ``index`` is the position in the enclosing ``circuit.data``. ``block`` is the
    index of the control flow block entered from that instruction, or None when
    the step is the final instruction.
    """

    index: int
    block: int | None = None

    def render(self) -> str:
        return f"[{self.index}]" if self.block is None else f"[{self.index}].block[{self.block}]"


@dataclass(frozen=True, slots=True)
class CircuitLocation:
    """Position inside an in-memory circuit.

    Engine B has no source file, so findings are addressed by a path of
    instruction indices. A flat index cannot identify an instruction nested in a
    control flow block, which is why this is a tuple.
    """

    circuit_name: str
    path: tuple[InstructionStep, ...]
    operation: str | None = None
    qubits: tuple[int, ...] = ()
    clbits: tuple[int, ...] = ()

    def render(self) -> str:
        steps = "".join(step.render() for step in self.path)
        return f"{self.circuit_name}{steps}"


Location = SourceLocation | NotebookLocation | CircuitLocation


@dataclass(frozen=True, slots=True)
class Finding:
    """A single reported problem."""

    rule: str
    message: str
    location: Location
    severity: Severity = Severity.WARNING
    tier: Tier = Tier.DEFAULT
    fix_hint: str | None = None
    context: dict[str, str] = field(default_factory=dict)

    @property
    def engine(self) -> Literal["A", "B"]:
        return "B" if isinstance(self.location, CircuitLocation) else "A"

    def sort_key(self) -> tuple[object, ...]:
        loc = self.location
        if isinstance(loc, SourceLocation):
            return (0, loc.path, loc.line, loc.column, self.rule)
        if isinstance(loc, NotebookLocation):
            return (0, loc.path, loc.cell_index, loc.line, loc.column, self.rule)
        return (1, loc.circuit_name, tuple(s.index for s in loc.path), self.rule)

    def render_text(self) -> str:
        return f"{self.location.render()}: {self.rule} {self.message}"


def location_path(location: Location) -> str | None:
    """File path of a location, or None for Engine B findings."""
    if isinstance(location, SourceLocation | NotebookLocation):
        return location.path
    return None


def as_uri_path(path: str) -> str:
    """Repo relative path in the forward slash form SARIF expects."""
    return str(PurePosixPath(*PurePosixPath(path.replace("\\", "/")).parts))
