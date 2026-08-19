"""Expression handlers of the analyser, read out through QXL103 and QXL101.

QXL103 fires only on a circuit proven to carry no measurement, and QXL101 fires
only on a proven V2 container, so each is a direct readout of what an expression
handler concluded.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"


def fires(body: str) -> bool:
    return "QXL103" in codes(lint(HEADER + body))


def nest(inner: str, levels: int) -> str:
    for _ in range(levels):
        inner = f"(flag or {inner})"
    return inner


# Unpacking targets ------------------------------------------------------


def test_tuple_unpacking_binds_every_target_to_the_element() -> None:
    assert fires("qc = QuantumCircuit(1)\na, b = [qc, qc]\nStatevectorSampler().run([a])\n")


def test_a_mutation_through_one_unpacked_name_is_seen_through_the_other() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\na, b = [qc, qc]\nb.measure_all()\nStatevectorSampler().run([a])\n"
    )


def test_a_starred_unpacking_target_holds_an_untracked_sequence() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nfirst, *rest = [qc, qc]\nStatevectorSampler().run(rest)\n"
    )


def test_a_plain_target_beside_a_starred_one_still_holds_the_element() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\nfirst, *rest = [qc, qc]\nStatevectorSampler().run([first])\n"
    )


@pytest.mark.parametrize("iterable", ["[]", "load()", "[*load()]"])
def test_unpacking_something_without_known_elements_binds_unknown(iterable: str) -> None:
    assert not fires(f"a, b = {iterable}\nStatevectorSampler().run([a])\n")


def test_a_list_unpacking_target_behaves_like_a_tuple_one() -> None:
    assert fires("qc = QuantumCircuit(1)\n[a, b] = [qc, qc]\nStatevectorSampler().run([a])\n")


# Subscript assignment ---------------------------------------------------


def test_storing_into_a_tracked_list_escapes_the_stored_circuit() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\nslots = [None]\nslots[0] = qc\nStatevectorSampler().run([qc])\n"
    )


def test_storing_into_an_unknown_container_escapes_the_stored_circuit() -> None:
    assert not fires("qc = QuantumCircuit(1)\nholder[0] = qc\nStatevectorSampler().run([qc])\n")


# Depth guard ------------------------------------------------------------


def test_a_shallow_boolean_chain_still_reaches_the_measurement() -> None:
    body = "qc = QuantumCircuit(1)\n" + nest("qc.measure_all()", 3)
    assert not fires(body + "\nStatevectorSampler().run([qc])\n")


def test_an_expression_nested_past_the_depth_limit_is_not_walked() -> None:
    # The guard stops the walk, so the buried measurement is never applied.
    body = "qc = QuantumCircuit(1)\n" + nest("qc.measure_all()", 80)
    assert fires(body + "\nStatevectorSampler().run([qc])\n")


# Fallback and walrus ----------------------------------------------------


def test_an_expression_without_a_handler_still_walks_its_children() -> None:
    # `is None` has no handler of its own, yet the walrus inside it must bind.
    assert fires("check = (qc := QuantumCircuit(1)) is None\nStatevectorSampler().run([qc])\n")


def test_a_walrus_yields_the_object_it_just_bound() -> None:
    assert fires("StatevectorSampler().run([(qc := QuantumCircuit(1))])\n")


def test_a_name_bound_by_a_walrus_is_usable_afterwards() -> None:
    assert not fires("(qc := QuantumCircuit(1)).measure_all()\nStatevectorSampler().run([qc])\n")


# Set and dict literals --------------------------------------------------


def test_a_set_literal_escapes_its_elements() -> None:
    assert not fires("qc = QuantumCircuit(1)\nseen = {qc}\nStatevectorSampler().run([qc])\n")


def test_a_starred_element_of_a_set_literal_escapes_the_whole_container() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\npubs = [qc]\nseen = {*pubs}\nStatevectorSampler().run(pubs)\n"
    )


def test_a_dict_with_double_star_unpacking_still_escapes_its_written_values() -> None:
    # `**base` contributes a None key, which the walker has to tolerate.
    assert not fires(
        'qc = QuantumCircuit(1)\nstore = {**base, "qc": qc}\nStatevectorSampler().run([qc])\n'
    )


# Sequence literals ------------------------------------------------------


def test_a_starred_list_element_is_flattened_into_the_literal() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\ninner = [qc]\npubs = [*inner]\nStatevectorSampler().run(pubs)\n"
    )


def test_a_starred_element_of_unknown_length_makes_the_literal_opaque() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\npubs = [qc, *load()]\nStatevectorSampler().run(pubs)\n"
    )


def test_a_literal_at_the_tracking_limit_is_still_tracked() -> None:
    elements = ", ".join(["qc"] * 64)
    assert fires(f"qc = QuantumCircuit(1)\npubs = [{elements}]\nStatevectorSampler().run(pubs)\n")


def test_a_literal_past_the_tracking_limit_becomes_opaque() -> None:
    elements = ", ".join(["qc"] * 65)
    assert not fires(
        f"qc = QuantumCircuit(1)\npubs = [{elements}]\nStatevectorSampler().run(pubs)\n"
    )


# Boolean operators ------------------------------------------------------


def test_a_boolean_operator_over_one_object_yields_that_object() -> None:
    assert fires("qc = QuantumCircuit(1)\nchosen = qc or qc\nStatevectorSampler().run([chosen])\n")


def test_a_boolean_operator_does_not_pick_a_side() -> None:
    assert not fires(
        "measured = QuantumCircuit(1)\n"
        "measured.measure_all()\n"
        "chosen = measured or QuantumCircuit(2)\n"
        "StatevectorSampler().run([chosen])\n"
    )


# Await ------------------------------------------------------------------


def test_an_awaited_call_is_analysed_like_any_other() -> None:
    assert fires(
        "async def main():\n    qc = QuantumCircuit(1)\n    await StatevectorSampler().run([qc])\n"
    )


def test_awaiting_a_circuit_preserving_call_loses_the_circuit() -> None:
    source = (
        "from qiskit import QuantumCircuit, transpile\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "async def main():\n"
        "    qc = QuantumCircuit(1)\n"
        "    StatevectorSampler().run([await transpile(qc, backend)])\n"
    )
    assert codes(lint(source)) == []


# Lambda -----------------------------------------------------------------


def test_a_rule_fires_inside_a_lambda_body() -> None:
    assert fires("run_it = lambda: StatevectorSampler().run([QuantumCircuit(1)])\n")


def test_a_lambda_parameter_is_unknown_inside_the_body() -> None:
    assert not fires("run_it = lambda circuit: StatevectorSampler().run([circuit])\n")


def test_a_lambda_body_cannot_change_an_outer_circuit() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\nfix = lambda: qc.measure_all()\nStatevectorSampler().run([qc])\n"
    )


# Comprehensions ---------------------------------------------------------


@pytest.mark.parametrize("expression", ["[p for p in pubs]", "(p for p in pubs)"])
def test_a_list_or_generator_comprehension_carries_its_element(expression: str) -> None:
    # Every iteration builds the same kind of thing, so the element stands for
    # the whole sequence and the circuit inside it stays reachable.
    assert fires(f"qc = QuantumCircuit(1)\npubs = [qc]\nStatevectorSampler().run({expression})\n")


@pytest.mark.parametrize("expression", ["{p for p in pubs}", "{i: p for i, p in enumerate(pubs)}"])
def test_a_set_or_dict_comprehension_is_not_a_tracked_pub_list(expression: str) -> None:
    assert not fires(
        f"qc = QuantumCircuit(1)\npubs = [qc]\nStatevectorSampler().run({expression})\n"
    )


def test_a_comprehension_target_binds_the_element_of_the_iterable() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n[c.measure_all() for c in [qc]]\nStatevectorSampler().run([qc])\n"
    )


def test_a_comprehension_over_an_unknown_iterable_binds_nothing() -> None:
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "[c.measure_all() for c in load()]\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_a_comprehension_condition_can_escape_the_circuit() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n[c for c in [qc] if keep(qc)]\nStatevectorSampler().run([qc])\n"
    )


# Indexing ---------------------------------------------------------------


PAIR = (
    "measured = QuantumCircuit(1)\nmeasured.measure_all()\n"
    "plain = QuantumCircuit(2)\npubs = [measured, plain]\n"
)


def test_a_constant_index_picks_exactly_that_element() -> None:
    assert not fires(PAIR + "StatevectorSampler().run([pubs[0]])\n")


def test_a_constant_index_does_not_pick_a_neighbouring_element() -> None:
    assert fires(PAIR + "StatevectorSampler().run([pubs[1]])\n")


def test_an_out_of_range_constant_index_falls_back_to_the_joined_element() -> None:
    assert fires("qc = QuantumCircuit(1)\npubs = [qc]\nStatevectorSampler().run([pubs[3]])\n")


def test_a_non_constant_index_yields_the_join_of_the_elements() -> None:
    assert fires("qc = QuantumCircuit(1)\npubs = [qc, qc]\nStatevectorSampler().run([pubs[i]])\n")


def test_indexing_a_list_with_unknown_contents_yields_nothing() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\npubs = [qc, *load()]\nStatevectorSampler().run([pubs[0]])\n"
    )


def test_indexing_a_job_instead_of_a_result_proves_no_receiver() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2, 2)\n"
        "qc.measure_all()\n"
        "counts = StatevectorSampler().run([qc])[0].get_counts()\n"
    )
    assert codes(lint(source)) == []


def test_a_result_that_may_be_none_is_not_a_proven_receiver() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2, 2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result() if cond else None\n"
        "counts = result[0].get_counts()\n"
    )
    assert codes(lint(source)) == []


# Attribute access -------------------------------------------------------


def test_an_imported_symbol_reached_by_attribute_is_still_the_class() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "import qiskit.primitives as primitives\n"
        "sampler_class = primitives.StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "sampler_class().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_an_attribute_chain_reports_the_receiver_kind_it_resolved() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2, 2)\n"
        "qc.measure_all()\n"
        "bin_ = StatevectorSampler().run([qc]).result()[0].data\n"
        "counts = bin_.get_counts()\n"
    )
    assert [finding.context["receiverKind"] for finding in lint(source)] == ["data_bin"]


# Containers that used to lose what they held ------------------------------


def test_a_comprehension_built_list_can_be_indexed() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        "sampler = StatevectorSampler()\n"
        "results = [sampler.run([qc]).result() for _ in range(3)]\n"
        "counts = results[0].get_counts()\n"
    )
    assert codes(lint(source)) == ["QXL101"]


def test_iterating_a_primitive_result_yields_pub_results() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "for pub in result:\n"
        "    pub.get_counts()\n"
    )
    findings = lint(source)
    assert codes(findings) == ["QXL101"]
    assert "PubResult" in findings[0].message


def test_unpacking_a_primitive_result_yields_pub_results() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "only, = result\n"
        "counts = only.get_counts()\n"
    )
    assert codes(lint(source)) == ["QXL101"]


def test_a_value_read_out_of_a_dict_literal_is_tracked() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        'results = {"first": StatevectorSampler().run([qc]).result()}\n'
        'counts = results["first"].get_counts()\n'
    )
    assert codes(lint(source)) == ["QXL101"]


def test_a_list_literal_with_a_spread_escapes_what_it_names() -> None:
    # The contents are forgotten at that point, so the circuit has to escape
    # with them; otherwise handing the list on leaves it looking untouched.
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "pubs = [qc, *other]\n"
        "send(pubs)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_subscripting_an_empty_dict_literal_is_unknown() -> None:
    assert not fires('qc = QuantumCircuit(1)\nStatevectorSampler().run([{}["missing"]])\n')


def test_subscripting_a_dict_joins_every_value_it_holds() -> None:
    # Any key can reach any value, so a dict holding one measured and one
    # unmeasured circuit answers MAYBE and the rule stays silent.
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "other = QuantumCircuit(1)\n"
        "other.measure_all()\n"
        'store = {"a": qc, "b": other}\n'
        'StatevectorSampler().run([store["a"]])\n'
    )
