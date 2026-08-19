"""Aliasing, containers, escape and control flow, exercised through QXL103.

QXL103 fires only on a circuit proven to have no measurement on any path, so it
is a direct readout of whether the analyser reached the right conclusion.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"


def fires(body: str) -> bool:
    return "QXL103" in codes(lint(HEADER + body))


# Aliasing ---------------------------------------------------------------


def test_alias_shares_object_identity() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nalias = qc\nalias.measure_all()\nStatevectorSampler().run([qc])\n"
    )


def test_alias_chain_shares_identity() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\na = qc\nb = a\nb.measure_all()\nStatevectorSampler().run([qc])\n"
    )


def test_rebinding_an_alias_does_not_touch_the_original() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "alias = qc\n"
        "alias = QuantumCircuit(2)\n"
        "alias.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_copy_is_a_separate_object() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "other = qc.copy()\n"
        "other.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


# Containers -------------------------------------------------------------


def test_list_literal_is_not_an_escape() -> None:
    assert fires("qc = QuantumCircuit(1)\npubs = [qc]\nStatevectorSampler().run(pubs)\n")


def test_append_to_a_local_list_is_tracked() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "circuits = []\n"
        "circuits.append(qc)\n"
        "StatevectorSampler().run(circuits)\n"
    )


def test_extend_a_local_list_is_tracked() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "circuits = []\n"
        "circuits.extend([qc])\n"
        "StatevectorSampler().run(circuits)\n"
    )


def test_measuring_through_a_list_element_is_seen() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\npubs = [qc]\nqc.measure_all()\nStatevectorSampler().run(pubs)\n"
    )


def test_pub_tuple_form_is_understood() -> None:
    assert fires("qc = QuantumCircuit(1)\nStatevectorSampler().run([(qc, None)])\n")


def test_two_lists_with_equal_contents_are_not_confused() -> None:
    assert not fires(
        "measured = QuantumCircuit(1)\n"
        "measured.measure_all()\n"
        "a = [measured]\n"
        "b = [measured]\n"
        "b.append(QuantumCircuit(2))\n"
        "StatevectorSampler().run(a)\n"
    )


# Escape -----------------------------------------------------------------


def test_unmodelled_call_receiving_the_circuit_silences_the_rule() -> None:
    assert not fires("qc = QuantumCircuit(1)\nhelper(qc)\nStatevectorSampler().run([qc])\n")


def test_attribute_store_escapes() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nholder.circuit = qc\nStatevectorSampler().run([qc])\n"
    )


def test_call_without_access_to_the_name_has_no_effect() -> None:
    assert fires('qc = QuantumCircuit(1)\nhelper("unrelated")\nStatevectorSampler().run([qc])\n')


def test_pure_builtin_does_not_escape() -> None:
    assert fires("qc = QuantumCircuit(1)\nprint(qc)\nStatevectorSampler().run([qc])\n")


def test_calling_a_locally_defined_function_invalidates_everything() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "def build():\n"
        "    qc.measure_all()\n"
        "build()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_global_declaration_escapes() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\ndef f():\n    global qc\nf()\nStatevectorSampler().run([qc])\n"
    )


def test_a_local_dict_is_not_an_escape() -> None:
    # The same rule a local list gets: nothing outside can be holding it.
    assert fires('qc = QuantumCircuit(1)\nstore = {"a": qc}\nStatevectorSampler().run([qc])\n')


def test_a_dict_handed_to_unmodelled_code_escapes_its_values() -> None:
    assert not fires(
        'qc = QuantumCircuit(1)\nstore = {"a": qc}\nsend(store)\nStatevectorSampler().run([qc])\n'
    )


def test_a_dict_method_escapes_its_values() -> None:
    assert not fires(
        'qc = QuantumCircuit(1)\nstore = {"a": qc}\n'
        "store.update(other)\nStatevectorSampler().run([qc])\n"
    )


def test_a_dict_spread_into_a_call_escapes_its_values() -> None:
    assert not fires(
        'qc = QuantumCircuit(1)\nstore = {"a": qc}\nsend(**store)\nStatevectorSampler().run([qc])\n'
    )


def test_a_value_read_back_out_of_a_local_dict_is_still_tracked() -> None:
    assert fires(
        'qc = QuantumCircuit(1)\nstore = {"a": qc}\nStatevectorSampler().run([store["a"]])\n'
    )


def test_unmodelled_method_on_the_circuit_invalidates_but_keeps_the_kind() -> None:
    # The rule stays silent, and a later modelled mutation is still understood.
    assert not fires("qc = QuantumCircuit(1)\nqc.mystery()\nStatevectorSampler().run([qc])\n")


def test_read_only_circuit_method_keeps_facts() -> None:
    assert fires("qc = QuantumCircuit(1)\nqc.draw()\nStatevectorSampler().run([qc])\n")


# Control flow -----------------------------------------------------------


def test_if_join_produces_maybe() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nif cond:\n    qc.measure_all()\nStatevectorSampler().run([qc])\n"
    )


def test_measurement_on_both_branches_is_definite() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "if cond:\n"
        "    qc.measure_all()\n"
        "else:\n"
        "    qc.measure(0, 0)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_absence_on_both_branches_still_fires() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "if cond:\n"
        "    qc.h(0)\n"
        "else:\n"
        "    qc.x(0)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_for_loop_body_yields_maybe() -> None:
    assert not fires(
        "qc = QuantumCircuit(3)\n"
        "for q in range(3):\n"
        "    qc.measure(q, q)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_while_loop_body_yields_maybe() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "while cond:\n"
        "    qc.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_try_handler_starts_from_the_join() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "try:\n"
        "    qc.measure_all()\n"
        "except Exception:\n"
        "    pass\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_finally_applies_to_every_path() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "try:\n"
        "    pass\n"
        "finally:\n"
        "    qc.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_match_without_a_wildcard_keeps_the_no_match_path() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "match value:\n"
        "    case 1:\n"
        "        qc.measure_all()\n"
        "    case 2:\n"
        "        qc.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_match_with_a_wildcard_covering_every_case_is_definite() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "match value:\n"
        "    case 1:\n"
        "        qc.measure_all()\n"
        "    case _:\n"
        "        qc.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_with_body_runs_unconditionally() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nwith ctx:\n    qc.measure_all()\nStatevectorSampler().run([qc])\n"
    )


def test_conditional_expression_joins_both_sides() -> None:
    assert not fires(
        "measured = QuantumCircuit(1)\n"
        "measured.measure_all()\n"
        "qc = measured if cond else QuantumCircuit(2)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_return_makes_the_rest_unreachable() -> None:
    assert not fires(
        "def f():\n    qc = QuantumCircuit(1)\n    return qc\n    StatevectorSampler().run([qc])\n"
    )


def test_findings_inside_a_function_body_are_reported() -> None:
    assert fires(
        "def f():\n    qc = QuantumCircuit(1)\n    qc.h(0)\n    StatevectorSampler().run([qc])\n"
    )


def test_module_data_bindings_do_not_leak_into_a_function() -> None:
    # `qc` is module level, so inside `f` it is unknown and nothing may fire.
    assert not fires("qc = QuantumCircuit(1)\ndef f():\n    StatevectorSampler().run([qc])\n")


# Imports and provenance -------------------------------------------------


@pytest.mark.parametrize(
    "importer",
    [
        "from qiskit.primitives import StatevectorSampler as S\nrunner = S()",
        "import qiskit.primitives as P\nrunner = P.StatevectorSampler()",
        "from qiskit_ibm_runtime import SamplerV2 as S\nrunner = S(mode=backend)",
        "from qiskit_ibm_runtime import Sampler as S\nrunner = S(mode=backend)",
    ],
)
def test_sampler_is_recognised_through_aliases(importer: str) -> None:
    source = (
        f"from qiskit import QuantumCircuit\n{importer}\nqc = QuantumCircuit(1)\nrunner.run([qc])\n"
    )
    assert "QXL103" in codes(lint(source))


def test_estimator_is_never_flagged_for_a_missing_measurement() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorEstimator\n"
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_runtime_submodule_sampler_is_not_the_v2_class() -> None:
    # `qiskit_ibm_runtime.sampler.Sampler` is an empty version 0 marker class,
    # unlike the package level name, so it must not be treated as a SamplerV2.
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime.sampler import Sampler\n"
        "qc = QuantumCircuit(1)\n"
        "Sampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_a_conditional_import_is_still_the_import_at_the_call() -> None:
    # try/except ImportError with a handler that does not rebind the name. The
    # name is either the import or unbound, and unbound cannot be called.
    assert fires(
        "try:\n"
        "    from qiskit.primitives import StatevectorSampler\n"
        "except ImportError:\n"
        "    pass\n"
        "qc = QuantumCircuit(1)\n"
        "qc.h(0)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_a_conditional_import_whose_handler_rebinds_stays_silent() -> None:
    # Here the name is bound to something on both paths, and one of them is not
    # a primitive, so the rule cannot prove what is being called.
    assert not fires(
        "try:\n"
        "    from qiskit.primitives import StatevectorSampler\n"
        "except ImportError:\n"
        "    StatevectorSampler = None\n"
        "qc = QuantumCircuit(1)\n"
        "qc.h(0)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_a_circuit_bound_on_only_one_branch_is_still_that_circuit() -> None:
    assert fires(
        "if cond:\n    qc = QuantumCircuit(1)\n    qc.h(0)\nStatevectorSampler().run([qc])\n"
    )
