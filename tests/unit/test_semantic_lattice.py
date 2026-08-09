"""The abstract value lattice and the fact merge table.

The merge table is enumerated cell by cell: it is the part of the analyser a
regression would silently turn into false positives.
"""

from __future__ import annotations

import pytest

from qxlint.semantics.objects import (
    Escape,
    ObjectFacts,
    ObjectKind,
    ObjectStore,
    Provenance,
    TriState,
    merge_escape,
    merge_facts,
    merge_provenance,
    merge_tristate,
)
from qxlint.semantics.values import (
    UNBOUND,
    UNKNOWN,
    ConstInt,
    ConstStr,
    ImportedSymbol,
    ObjectRef,
    Sequence,
    Union,
    is_definite,
    join,
    object_refs,
)

ABSENT = TriState.DEFINITELY_ABSENT
PRESENT = TriState.DEFINITELY_PRESENT
MAYBE = TriState.MAYBE_PRESENT
UNK = TriState.UNKNOWN


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (ABSENT, ABSENT, ABSENT),
        (PRESENT, PRESENT, PRESENT),
        (ABSENT, PRESENT, MAYBE),
        (PRESENT, ABSENT, MAYBE),
        (MAYBE, ABSENT, MAYBE),
        (MAYBE, PRESENT, MAYBE),
        (MAYBE, MAYBE, MAYBE),
        (ABSENT, MAYBE, MAYBE),
        (PRESENT, MAYBE, MAYBE),
        (UNK, ABSENT, UNK),
        (UNK, PRESENT, UNK),
        (UNK, MAYBE, UNK),
        (UNK, UNK, UNK),
        (ABSENT, UNK, UNK),
        (PRESENT, UNK, UNK),
        (MAYBE, UNK, UNK),
    ],
)
def test_merge_tristate_every_cell(left: TriState, right: TriState, expected: TriState) -> None:
    assert merge_tristate(left, right) is expected
    assert merge_tristate(right, left) is expected


def test_only_definite_states_are_definite() -> None:
    assert ABSENT.is_definite and PRESENT.is_definite
    assert not MAYBE.is_definite
    assert not UNK.is_definite


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (Escape.LOCAL, Escape.LOCAL, Escape.LOCAL),
        (Escape.LOCAL, Escape.ESCAPED, Escape.ESCAPED),
        (Escape.ESCAPED, Escape.ESCAPED, Escape.ESCAPED),
    ],
)
def test_merge_escape(left: Escape, right: Escape, expected: Escape) -> None:
    assert merge_escape(left, right) is expected
    assert merge_escape(right, left) is expected


def test_merge_provenance_disagreement_is_unknown() -> None:
    assert merge_provenance(Provenance.SAMPLER, Provenance.SAMPLER) is Provenance.SAMPLER
    assert merge_provenance(Provenance.SAMPLER, Provenance.ESTIMATOR) is Provenance.UNKNOWN


def test_merge_facts_keeps_kind_and_joins_the_rest() -> None:
    left = ObjectFacts(ObjectKind.CIRCUIT, measurement=ABSENT, registers=frozenset({"c"}))
    right = ObjectFacts(ObjectKind.CIRCUIT, measurement=PRESENT, registers=frozenset({"meas"}))
    merged = merge_facts(left, right)
    assert merged.kind is ObjectKind.CIRCUIT
    assert merged.measurement is MAYBE
    assert merged.registers is None


def test_merge_facts_kind_conflict_is_opaque() -> None:
    left = ObjectFacts(ObjectKind.CIRCUIT)
    right = ObjectFacts(ObjectKind.BIT_ARRAY)
    assert merge_facts(left, right).kind is ObjectKind.OPAQUE


def test_escaped_facts_read_as_unknown() -> None:
    facts = ObjectFacts(ObjectKind.CIRCUIT, measurement=ABSENT, escape=Escape.ESCAPED)
    assert facts.measurement is ABSENT
    assert facts.read_measurement() is UNK


def test_invalidated_keeps_kind() -> None:
    facts = ObjectFacts(ObjectKind.CIRCUIT, measurement=PRESENT, control_flow=PRESENT)
    invalid = facts.invalidated()
    assert invalid.kind is ObjectKind.CIRCUIT
    assert invalid.measurement is UNK
    assert invalid.control_flow is UNK
    assert invalid.escape is Escape.LOCAL


def test_join_identical_values() -> None:
    assert join(ConstStr("a"), ConstStr("a")) == ConstStr("a")


def test_join_unknown_absorbs() -> None:
    assert join(UNKNOWN, ConstInt(1)) is UNKNOWN
    assert join(ConstInt(1), UNKNOWN) is UNKNOWN


def test_join_makes_a_union() -> None:
    merged = join(ConstStr("a"), ConstStr("b"))
    assert isinstance(merged, Union)
    assert merged.options == frozenset({ConstStr("a"), ConstStr("b")})


def test_join_flattens_nested_unions() -> None:
    merged = join(join(ConstInt(1), ConstInt(2)), ConstInt(3))
    assert isinstance(merged, Union)
    assert len(merged.options) == 3


def test_join_absorbs_unbound_because_an_unbound_name_cannot_be_used() -> None:
    # A path where the name is unbound raises NameError at the use, so any
    # execution that reaches the use took the path that bound it.
    assert join(UNBOUND, ObjectRef(1)) == ObjectRef(1)
    assert join(ObjectRef(1), UNBOUND) == ObjectRef(1)
    assert is_definite(join(UNBOUND, ObjectRef(1)))


def test_join_of_two_unbound_paths_is_still_unbound() -> None:
    assert join(UNBOUND, UNBOUND) is UNBOUND


def test_join_sequences_elementwise() -> None:
    left = Sequence((ObjectRef(1),), token=1)
    right = Sequence((ObjectRef(2),), token=1)
    merged = join(left, right)
    assert isinstance(merged, Sequence)
    assert merged.token == 1
    assert isinstance(merged.elements[0], Union)


def test_join_sequences_of_different_length_loses_contents() -> None:
    merged = join(Sequence((ObjectRef(1),)), Sequence((ObjectRef(1), ObjectRef(2))))
    assert isinstance(merged, Sequence)
    assert merged.elements is None


def test_join_sequences_with_different_tokens_loses_identity() -> None:
    merged = join(Sequence((), token=1), Sequence((), token=2))
    assert isinstance(merged, Sequence)
    assert merged.token is None


def test_wide_union_collapses_to_unknown() -> None:
    merged = ConstInt(0)
    for value in range(1, 20):
        merged = join(merged, ConstInt(value))
    assert merged is UNKNOWN


def test_object_refs_reaches_through_containers_and_unions() -> None:
    value = Sequence((ObjectRef(1), Union(frozenset({ObjectRef(2), ConstInt(3)}))))
    assert {ref.id for ref in object_refs(value)} == {1, 2}


def test_imported_symbol_is_not_an_instance() -> None:
    assert is_definite(ImportedSymbol("qiskit.QuantumCircuit"))
    assert not isinstance(ImportedSymbol("x"), ObjectRef)


def test_store_merge_joins_shared_ids() -> None:
    left = ObjectStore()
    object_id = left.allocate(ObjectFacts(ObjectKind.CIRCUIT, measurement=ABSENT))
    right = left.copy()
    right.update(object_id, measurement=PRESENT)
    left.merge_from(right)
    facts = left.get(object_id)
    assert facts is not None
    assert facts.measurement is MAYBE


def test_store_copy_is_independent() -> None:
    store = ObjectStore()
    object_id = store.allocate(ObjectFacts(ObjectKind.CIRCUIT, measurement=ABSENT))
    clone = store.copy()
    clone.update(object_id, measurement=PRESENT)
    original = store.get(object_id)
    assert original is not None
    assert original.measurement is ABSENT


# Library circuit table ----------------------------------------------------


def test_every_library_circuit_is_modelled_as_a_measurement_free_circuit() -> None:
    """The table is what makes an ansatz visible to the rules.

    An entry with the wrong kind makes the rules silent; one with the wrong
    measurement fact makes QXL103 wrong. scripts/verify_model.py checks the
    same claim against a real Qiskit; this checks the table itself.
    """
    from qxlint.semantics.model import CONSTRUCTORS, LIBRARY_CIRCUITS

    for name in LIBRARY_CIRCUITS:
        spec = CONSTRUCTORS[f"qiskit.circuit.library.{name}"]
        assert spec.kind is ObjectKind.CIRCUIT, name
        assert spec.measurement is TriState.DEFINITELY_ABSENT, name
        assert spec.control_flow is TriState.DEFINITELY_ABSENT, name


def test_random_circuit_asserts_only_its_kind() -> None:
    from qxlint.semantics.model import CONSTRUCTORS

    spec = CONSTRUCTORS["qiskit.circuit.random.random_circuit"]
    assert spec.kind is ObjectKind.CIRCUIT
    assert spec.measurement is TriState.UNKNOWN
    assert spec.control_flow is TriState.UNKNOWN
