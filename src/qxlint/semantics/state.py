"""Abstract state: name bindings plus the object store, and how they join."""

from __future__ import annotations

from dataclasses import dataclass, field

from qxlint.semantics.objects import ObjectFacts, ObjectStore
from qxlint.semantics.values import (
    UNBOUND,
    UNKNOWN,
    AbstractValue,
    ImportedSymbol,
    ObjectRef,
    join,
    object_refs,
)


@dataclass
class State:
    """One analysis path.

    ``reachable`` is False after ``return``, ``break``, ``continue`` or ``raise``.
    An unreachable path contributes nothing to a join.
    """

    env: dict[str, AbstractValue] = field(default_factory=dict)
    store: ObjectStore = field(default_factory=ObjectStore)
    reachable: bool = True

    def copy(self) -> State:
        return State(env=dict(self.env), store=self.store.copy(), reachable=self.reachable)

    def lookup(self, name: str) -> AbstractValue:
        return self.env.get(name, UNBOUND)

    def bind(self, name: str, value: AbstractValue) -> None:
        self.env[name] = value

    def unbind(self, name: str) -> None:
        self.env[name] = UNBOUND

    def facts(self, value: AbstractValue) -> ObjectFacts | None:
        """Facts for a value that is a single object reference."""
        if isinstance(value, ObjectRef):
            return self.store.get(value.id)
        return None

    def allocate(self, facts: ObjectFacts) -> ObjectRef:
        return ObjectRef(self.store.allocate(facts))

    def invalidate_reachable(self, value: AbstractValue) -> None:
        """Push mutable facts to UNKNOWN for every object reachable from a value."""
        for ref in object_refs(value):
            self.store.invalidate(ref.id)

    def escape_reachable(self, value: AbstractValue) -> None:
        """Mark every object reachable from a value as escaped."""
        for ref in object_refs(value):
            self.store.mark_escaped(ref.id)

    def merge_from(self, other: State) -> None:
        """Join another path into this one, in place."""
        if not other.reachable:
            return
        if not self.reachable:
            self.env = dict(other.env)
            self.store = other.store.copy()
            self.reachable = True
            return

        self.store.merge_from(other.store)
        names = set(self.env) | set(other.env)
        merged: dict[str, AbstractValue] = {}
        for name in names:
            merged[name] = join(self.env.get(name, UNBOUND), other.env.get(name, UNBOUND))
        self.env = merged

    def widen_all(self) -> None:
        """Drop every mutable fact. Used where control flow is not modelled."""
        for object_id in self.store.ids():
            self.store.invalidate(object_id)


def merge_states(states: list[State]) -> State:
    """Join a list of paths. Unreachable paths are ignored."""
    live = [state for state in states if state.reachable]
    if not live:
        dead = State(reachable=False)
        if states:
            dead.store = states[0].store.copy()
        return dead
    result = live[0].copy()
    for state in live[1:]:
        result.merge_from(state)
    return result


def import_only_env(env: dict[str, AbstractValue]) -> dict[str, AbstractValue]:
    """Bindings a nested function may safely inherit.

    v0.1 has no interprocedural analysis. Module level data bindings are not
    carried into a function body because the call order is unknown, but import
    bindings are, since rebinding an imported name is rare and modelled.
    """
    return {name: value for name, value in env.items() if isinstance(value, ImportedSymbol)} | {
        name: UNKNOWN for name, value in env.items() if not isinstance(value, ImportedSymbol)
    }
