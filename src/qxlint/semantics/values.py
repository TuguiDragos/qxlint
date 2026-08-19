"""The abstract value lattice.

Names bind to abstract values. Mutable objects are *not* stored in the binding:
a name binds to an :class:`ObjectRef`, and the facts live in the object store
under that identity. Two names holding the same ``ObjectRef`` are aliases, so a
mutation through either one updates the same facts.

Lattice shape, from bottom to top::

    Unbound
    ObjectRef | ImportedSymbol | Const* | Sequence | Mapping
    Union
    Unknown

``Unknown`` is top and absorbs everything. ``Union`` keeps alternatives apart so
a rule can stay silent when only some branches match, instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


class AbstractValue:
    """Base class for every abstract value."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Unknown(AbstractValue):
    """Top. Nothing is known, so no rule may fire on it."""

    def __repr__(self) -> str:
        return "Unknown"


@dataclass(frozen=True, slots=True)
class Unbound(AbstractValue):
    """The name is not bound on this path."""

    def __repr__(self) -> str:
        return "Unbound"


@dataclass(frozen=True, slots=True)
class ObjectRef(AbstractValue):
    """Stable identity of a mutable object. Facts live in the object store."""

    id: int

    def __repr__(self) -> str:
        return f"Obj({self.id})"


@dataclass(frozen=True, slots=True)
class ImportedSymbol(AbstractValue):
    """A module level symbol reached by import, before it is called.

    ``QuantumCircuit`` the class and ``qc`` the instance are different values,
    so the constructor and the instance need different representations.
    """

    qualified_name: str

    def __repr__(self) -> str:
        return f"Sym({self.qualified_name})"


@dataclass(frozen=True, slots=True)
class ConstStr(AbstractValue):
    value: str


@dataclass(frozen=True, slots=True)
class ConstInt(AbstractValue):
    value: int


@dataclass(frozen=True, slots=True)
class ConstBool(AbstractValue):
    value: bool


@dataclass(frozen=True, slots=True)
class ConstNone(AbstractValue):
    def __repr__(self) -> str:
        return "None"


@dataclass(frozen=True, slots=True)
class Sequence(AbstractValue):
    """A list or tuple whose contents may be tracked.

    ``elements`` is None when the contents are not known. ``local`` is True while
    the container itself has not been handed to unmodelled code; storing a value
    into a local container is not an escape.

    ``token`` identifies the literal the container came from, so ``append`` only
    updates the container it was called on. Two lists with equal contents are
    still two lists. A join of containers with different tokens drops it to None,
    which means the identity is no longer tracked.
    """

    elements: tuple[AbstractValue, ...] | None
    local: bool = True
    mutable: bool = True
    token: int | None = None

    def __repr__(self) -> str:
        inner = "?" if self.elements is None else ", ".join(repr(e) for e in self.elements)
        return f"Seq[{inner}]"


@dataclass(frozen=True, slots=True)
class Mapping(AbstractValue):
    """A dict literal whose values may be tracked.

    Only the values are kept. Iterating a dict yields its keys, so this is
    never treated as a sequence, and every method on it is unmodelled, so it
    escapes rather than being reasoned about.
    """

    values: tuple[AbstractValue, ...] | None
    local: bool = True
    token: int | None = None

    def __repr__(self) -> str:
        inner = "?" if self.values is None else ", ".join(repr(v) for v in self.values)
        return f"Map[{inner}]"


@dataclass(frozen=True, slots=True)
class Union(AbstractValue):
    """Two or more alternatives that a branch join could not reconcile."""

    options: frozenset[AbstractValue]

    def __repr__(self) -> str:
        return "Union{" + ", ".join(sorted(repr(o) for o in self.options)) + "}"


UNKNOWN: Final = Unknown()
UNBOUND: Final = Unbound()
NONE: Final = ConstNone()

MAX_UNION_WIDTH: Final = 8
MAX_SEQUENCE_WIDTH: Final = 64


def join(left: AbstractValue, right: AbstractValue) -> AbstractValue:
    """Least upper bound of two abstract values."""
    if left == right:
        return left
    if isinstance(left, Unknown) or isinstance(right, Unknown):
        return UNKNOWN
    # Unbound is the bottom of this lattice and a join absorbs it. Using an
    # unbound name raises NameError, so any execution that reaches a use of the
    # name took the branch that bound it, and that value is what the use sees.
    # This is what makes the common conditional import readable:
    #
    #     try:
    #         from qiskit_ibm_runtime import QiskitRuntimeService
    #     except ImportError:
    #         pass
    #
    # An except branch that rebinds the name, to None for instance, is a
    # different case and still joins to a Union, because there the name is bound
    # to something the rule cannot reason about.
    if isinstance(left, Unbound):
        return right
    if isinstance(right, Unbound):
        return left

    options: set[AbstractValue] = set()
    for value in (left, right):
        if isinstance(value, Union):
            options.update(value.options)
        else:
            options.add(value)

    merged = _merge_mappings(_merge_sequences(options))
    if len(merged) == 1:
        return next(iter(merged))
    if len(merged) > MAX_UNION_WIDTH:
        return UNKNOWN
    return Union(frozenset(merged))


def _merge_sequences(options: set[AbstractValue]) -> set[AbstractValue]:
    """Collapse sequences elementwise so unions do not explode on list joins."""
    seqs = [o for o in options if isinstance(o, Sequence)]
    if len(seqs) < 2:
        return options
    rest = {o for o in options if not isinstance(o, Sequence)}
    acc = seqs[0]
    for other in seqs[1:]:
        acc = _join_sequence(acc, other)
    rest.add(acc)
    return rest


def _join_sequence(left: Sequence, right: Sequence) -> Sequence:
    local = left.local and right.local
    mutable = left.mutable or right.mutable
    token = left.token if left.token == right.token else None
    if left.elements is None or right.elements is None:
        return Sequence(None, local, mutable, token)
    if len(left.elements) != len(right.elements):
        return Sequence(None, local, mutable, token)
    elements = tuple(join(a, b) for a, b in zip(left.elements, right.elements, strict=True))
    return Sequence(elements, local, mutable, token)


def _merge_mappings(options: set[AbstractValue]) -> set[AbstractValue]:
    """Collapse mappings the same way sequences are collapsed."""
    maps = [o for o in options if isinstance(o, Mapping)]
    if len(maps) < 2:
        return options
    rest = {o for o in options if not isinstance(o, Mapping)}
    acc = maps[0]
    for other in maps[1:]:
        acc = _join_mapping(acc, other)
    rest.add(acc)
    return rest


def _join_mapping(left: Mapping, right: Mapping) -> Mapping:
    local = left.local and right.local
    token = left.token if left.token == right.token else None
    if left.values is None or right.values is None:
        return Mapping(None, local, token)
    if len(left.values) != len(right.values):
        return Mapping(None, local, token)
    values = tuple(join(a, b) for a, b in zip(left.values, right.values, strict=True))
    return Mapping(values, local, token)


def iter_options(value: AbstractValue) -> tuple[AbstractValue, ...]:
    """Flatten a value into the alternatives it may take."""
    if isinstance(value, Union):
        return tuple(value.options)
    return (value,)


def object_refs(value: AbstractValue) -> tuple[ObjectRef, ...]:
    """Every object identity reachable from a value, containers included."""
    seen: list[ObjectRef] = []
    _collect_refs(value, seen, depth=0)
    return tuple(seen)


def _collect_refs(value: AbstractValue, out: list[ObjectRef], depth: int) -> None:
    if depth > 6:
        return
    if isinstance(value, ObjectRef):
        if value not in out:
            out.append(value)
    elif isinstance(value, Union):
        for option in value.options:
            _collect_refs(option, out, depth + 1)
    elif isinstance(value, Sequence) and value.elements is not None:
        for element in value.elements:
            _collect_refs(element, out, depth + 1)
    elif isinstance(value, Mapping) and value.values is not None:
        for element in value.values:
            _collect_refs(element, out, depth + 1)


def is_definite(value: AbstractValue) -> bool:
    """True when the value is a single alternative that is not top or unbound."""
    return not isinstance(value, Unknown | Unbound | Union)
