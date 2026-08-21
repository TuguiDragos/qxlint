"""Object identities and the facts attached to them.

Bindings live in the environment, facts live here. Aliasing therefore works:
``alias = qc`` copies an :class:`~qxlint.semantics.values.ObjectRef`, and
``alias.measure_all()`` updates the facts both names see.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace


class ObjectKind(enum.Enum):
    """What an object is. Rules fire on kinds, never on variable names."""

    CIRCUIT = "circuit"
    SAMPLER_V2 = "sampler_v2"
    ESTIMATOR_V2 = "estimator_v2"
    PRIMITIVE_JOB_V2 = "primitive_job_v2"
    PRIMITIVE_RESULT_V2 = "primitive_result_v2"
    SAMPLER_PUB_RESULT_V2 = "sampler_pub_result_v2"
    ESTIMATOR_PUB_RESULT_V2 = "estimator_pub_result_v2"
    PUB_RESULT_V2 = "pub_result_v2"
    DATA_BIN = "data_bin"
    BIT_ARRAY = "bit_array"
    NDARRAY = "ndarray"
    OBSERVABLE = "observable"
    TARGET = "target"
    LEGACY_SAMPLER_V1 = "legacy_sampler_v1"
    LEGACY_ESTIMATOR_V1 = "legacy_estimator_v1"
    LEGACY_PRIMITIVE_RESULT_V1 = "legacy_primitive_result_v1"
    LEGACY_BACKEND = "legacy_backend"
    LEGACY_JOB = "legacy_job"
    LEGACY_RESULT = "legacy_result"
    RUNTIME_SERVICE = "runtime_service"
    OPAQUE = "opaque"


PUB_RESULT_KINDS = frozenset(
    {
        ObjectKind.PUB_RESULT_V2,
        ObjectKind.SAMPLER_PUB_RESULT_V2,
        ObjectKind.ESTIMATOR_PUB_RESULT_V2,
    }
)


class TriState(enum.Enum):
    """A fact that a branch join can leave undecided.

    ``MAYBE_PRESENT`` is the reason rules do not fire after an ``if``: the fact
    holds on some paths only, which is neither proof nor absence of proof.
    """

    DEFINITELY_ABSENT = "absent"
    DEFINITELY_PRESENT = "present"
    MAYBE_PRESENT = "maybe"
    UNKNOWN = "unknown"

    @property
    def is_definite(self) -> bool:
        return self in (TriState.DEFINITELY_ABSENT, TriState.DEFINITELY_PRESENT)


def merge_tristate(left: TriState, right: TriState) -> TriState:
    """Branch join for a tri-state fact."""
    if left is TriState.UNKNOWN or right is TriState.UNKNOWN:
        return TriState.UNKNOWN
    if left is right:
        return left
    return TriState.MAYBE_PRESENT


class Escape(enum.Enum):
    """Whether unmodelled code can still reach and mutate the object."""

    LOCAL = "local"
    ESCAPED = "escaped"


def merge_escape(left: Escape, right: Escape) -> Escape:
    return Escape.ESCAPED if Escape.ESCAPED in (left, right) else Escape.LOCAL


class Provenance(enum.Enum):
    """Which primitive family produced a result object."""

    SAMPLER = "sampler"
    ESTIMATOR = "estimator"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


def merge_provenance(left: Provenance, right: Provenance) -> Provenance:
    return left if left is right else Provenance.UNKNOWN


@dataclass(frozen=True, slots=True)
class ObjectFacts:
    """Everything known about one abstract object.

    ``kind`` is immutable for the lifetime of the identity. The rest are mutable
    facts that unmodelled effects can push to ``UNKNOWN``.
    """

    kind: ObjectKind
    measurement: TriState = TriState.UNKNOWN
    # PRESENT only while every measurement recorded is still the last thing on
    # its qubits. `remove_final_measurements` clears exactly those.
    measurement_final: TriState = TriState.UNKNOWN
    control_flow: TriState = TriState.UNKNOWN
    escape: Escape = Escape.LOCAL
    provenance: Provenance = Provenance.UNKNOWN
    registers: frozenset[str] | None = None
    origin: str | None = None

    def invalidated(self) -> ObjectFacts:
        """Facts after an unmodelled effect. The kind survives, the rest does not."""
        return replace(
            self,
            measurement=TriState.UNKNOWN,
            measurement_final=TriState.UNKNOWN,
            control_flow=TriState.UNKNOWN,
            registers=None,
        )

    def escaped(self) -> ObjectFacts:
        return replace(self.invalidated(), escape=Escape.ESCAPED)

    def read_measurement(self) -> TriState:
        """Measurement fact as a rule sees it. An escaped object yields UNKNOWN."""
        if self.escape is Escape.ESCAPED:
            return TriState.UNKNOWN
        return self.measurement

    def read_measurement_final(self) -> TriState:
        if self.escape is Escape.ESCAPED:
            return TriState.UNKNOWN
        return self.measurement_final

    def read_control_flow(self) -> TriState:
        if self.escape is Escape.ESCAPED:
            return TriState.UNKNOWN
        return self.control_flow


def merge_facts(left: ObjectFacts, right: ObjectFacts) -> ObjectFacts:
    """Branch join for one object.

    A kind conflict means the identity was reused for something incompatible,
    which should not happen; treat it as opaque rather than pick a side.
    """
    kind = left.kind if left.kind is right.kind else ObjectKind.OPAQUE
    return ObjectFacts(
        kind=kind,
        measurement=merge_tristate(left.measurement, right.measurement),
        measurement_final=merge_tristate(left.measurement_final, right.measurement_final),
        control_flow=merge_tristate(left.control_flow, right.control_flow),
        escape=merge_escape(left.escape, right.escape),
        provenance=merge_provenance(left.provenance, right.provenance),
        registers=left.registers if left.registers == right.registers else None,
        origin=left.origin if left.origin == right.origin else None,
    )


class ObjectStore:
    """Mutable map of object identity to facts."""

    __slots__ = ("_facts", "_next_id")

    def __init__(self, facts: dict[int, ObjectFacts] | None = None, next_id: int = 1) -> None:
        self._facts: dict[int, ObjectFacts] = dict(facts or {})
        self._next_id = next_id

    def allocate(self, facts: ObjectFacts) -> int:
        object_id = self._next_id
        self._next_id += 1
        self._facts[object_id] = facts
        return object_id

    def get(self, object_id: int) -> ObjectFacts | None:
        return self._facts.get(object_id)

    def set(self, object_id: int, facts: ObjectFacts) -> None:
        self._facts[object_id] = facts

    def update(self, object_id: int, **changes: object) -> None:
        current = self._facts.get(object_id)
        if current is not None:
            self._facts[object_id] = replace(current, **changes)  # type: ignore[arg-type]

    def invalidate(self, object_id: int) -> None:
        current = self._facts.get(object_id)
        if current is not None:
            self._facts[object_id] = current.invalidated()

    def mark_escaped(self, object_id: int) -> None:
        current = self._facts.get(object_id)
        if current is not None:
            self._facts[object_id] = current.escaped()

    def copy(self) -> ObjectStore:
        return ObjectStore(self._facts, self._next_id)

    def ids(self) -> frozenset[int]:
        return frozenset(self._facts)

    def merge_from(self, other: ObjectStore) -> None:
        """Join another store into this one, in place."""
        for object_id, facts in other._facts.items():
            mine = self._facts.get(object_id)
            self._facts[object_id] = facts if mine is None else merge_facts(mine, facts)
        self._next_id = max(self._next_id, other._next_id)
