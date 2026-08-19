"""Modelled call effects, exercised through the rules that read them out.

QXL103 fires only on a circuit proven to have no measurement, so it says whether
an effect preserved, invalidated or escaped the facts. QXL104 fires only on a
receiver proven to be a circuit, so it says what a call returned. QXL101 and
QXL102 read out the result object chain.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

SAMPLER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"
PASS_MANAGER = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "from qiskit.transpiler import generate_preset_pass_manager\n"
    "pm = generate_preset_pass_manager(optimization_level=1, backend=backend)\n"
)


def fires(body: str) -> bool:
    return "QXL103" in codes(lint(SAMPLER + body))


# Argument shapes --------------------------------------------------------


def test_a_starred_argument_with_known_contents_is_unpacked() -> None:
    assert fires("qc = QuantumCircuit(1)\nStatevectorSampler().run(*[[qc]])\n")


def test_a_starred_argument_with_unknown_contents_loses_the_operand() -> None:
    # `qc.append(*ops)` cannot be shown to append a plain gate, so the
    # measurement fact dies rather than being assumed intact.
    assert not fires("qc = QuantumCircuit(1)\nqc.append(*ops)\nStatevectorSampler().run([qc])\n")


def test_double_star_kwargs_leave_the_append_operand_unproven() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.circuit.library import XGate\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.append(XGate(), [0], **extra)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


# The callee -------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "expected"),
    [("handlers[0](qc)", []), ("handlers[0]()", ["QXL103"])],
)
def test_calling_a_value_that_is_neither_a_name_nor_an_attribute(
    call: str, expected: list[str]
) -> None:
    source = SAMPLER + f"qc = QuantumCircuit(1)\n{call}\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == expected


def test_a_shadowed_pure_builtin_is_no_longer_trusted() -> None:
    # `print` is only safe while it is the builtin; a rebound name is not.
    source = (
        SAMPLER + "qc = QuantumCircuit(1)\nprint = make_logger()\nprint(qc)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


@pytest.mark.parametrize(
    ("signature", "call", "expected"),
    [("circuit", "build(qc)", []), ("", "build()", ["QXL103"])],
)
def test_a_locally_defined_function_escapes_only_the_arguments_it_receives(
    signature: str, call: str, expected: list[str]
) -> None:
    # Both forms invalidate every fact, but only the escaped circuit refuses the
    # later modelled mutation, so only it stays unprovable.
    source = (
        SAMPLER + "qc = QuantumCircuit(1)\n"
        f"def build({signature}):\n    pass\n"
        f"{call}\n"
        "qc.remove_final_measurements()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == expected


# Constructing a circuit -------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        "",
        "QuantumRegister(2)",
        "QuantumRegister(2), ClassicalRegister(2)",
        "2, ClassicalRegister(2)",
    ],
)
def test_a_circuit_built_without_plain_integers_is_still_proven_unmeasured(
    arguments: str,
) -> None:
    source = (
        "from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister\n"
        "from qiskit.primitives import StatevectorSampler\n"
        f"qc = QuantumCircuit({arguments})\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


# Derived circuits -------------------------------------------------------


def test_transpile_returns_a_circuit_so_a_discarded_compose_is_reported() -> None:
    source = (
        "from qiskit import QuantumCircuit, transpile\n"
        "qc = QuantumCircuit(2)\n"
        "transpile(qc, backend).compose(other)\n"
    )
    assert codes(lint(source)) == ["QXL104"]


def test_transpile_of_an_unproven_value_returns_nothing_provable() -> None:
    source = "from qiskit import transpile\ntranspile(loaded, backend).compose(other)\n"
    assert codes(lint(source)) == []


def test_a_pass_manager_given_a_single_circuit_returns_a_single_circuit() -> None:
    source = (
        PASS_MANAGER + "qc = QuantumCircuit(2)\nqc.h(0)\nStatevectorSampler().run([pm.run(qc)])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_appending_to_a_pass_manager_result_is_dropped_rather_than_invented() -> None:
    # The derived list has no literal identity behind it, so the append cannot be
    # attached to it. Losing the new circuit is the safe direction.
    source = (
        PASS_MANAGER + "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "batch = pm.run([qc])\n"
        "batch.append(QuantumCircuit(2))\n"
        "StatevectorSampler().run(batch)\n"
    )
    assert codes(lint(source)) == []


# Container methods ------------------------------------------------------


@pytest.mark.parametrize(
    "call", ["clear()", "pop()", "remove(qc)", "insert(0, qc)", "sort()", "reverse()"]
)
def test_a_reordering_list_method_makes_the_contents_unknown(call: str) -> None:
    assert not fires(
        f"qc = QuantumCircuit(1)\ncircuits = [qc]\ncircuits.{call}\n"
        "StatevectorSampler().run(circuits)\n"
    )


@pytest.mark.parametrize(
    ("call", "expected"),
    [("circuits.index(qc)", []), ("circuits.index(0)", ["QXL103"])],
)
def test_an_unmodelled_list_method_escapes_only_the_arguments_it_receives(
    call: str, expected: list[str]
) -> None:
    source = (
        SAMPLER + f"qc = QuantumCircuit(1)\ncircuits = [qc]\n{call}\n"
        "StatevectorSampler().run(circuits)\n"
    )
    assert codes(lint(source)) == expected


def test_appending_to_a_fresh_local_list_does_not_escape_the_circuit() -> None:
    # A comprehension always builds a new list, whatever it iterated over, so
    # nothing outside can be holding it and the append cannot leak the circuit.
    assert fires(
        "qc = QuantumCircuit(1)\n"
        "circuits = [item for item in existing]\n"
        "circuits.append(qc)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_appending_to_a_container_from_unmodelled_code_escapes_the_circuit() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "circuits = make_them()\n"
        "circuits.append(qc)\n"
        "StatevectorSampler().run([qc])\n"
    )


# Method effects on a tracked object -------------------------------------


@pytest.mark.parametrize(
    ("call", "expected"),
    [("holder.mystery(qc)", []), ("holder.mystery(0)", ["QXL103"])],
)
def test_an_unmodelled_method_escapes_only_the_arguments_it_receives(
    call: str, expected: list[str]
) -> None:
    source = (
        SAMPLER + f"qc = QuantumCircuit(1)\nholder = QuantumCircuit(1)\n{call}\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == expected


@pytest.mark.parametrize(
    "builder", ["if_test", "if_else", "for_loop", "while_loop", "switch", "box"]
)
def test_a_control_flow_builder_keeps_the_measurement_fact(builder: str) -> None:
    assert fires(f"qc = QuantumCircuit(1)\nqc.{builder}(cond)\nStatevectorSampler().run([qc])\n")


def test_compose_without_inplace_leaves_the_receiver_alone() -> None:
    # The combined circuit is measured and `qc` is not, and QXL103 reports the
    # first pub it can prove, which is `qc`.
    source = (
        SAMPLER + "qc = QuantumCircuit(2)\n"
        "other = QuantumCircuit(2)\n"
        "other.measure_all()\n"
        "combined = qc.compose(other)\n"
        "StatevectorSampler().run([combined, qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_tensor_with_inplace_true_mutates_the_receiver() -> None:
    assert not fires(
        "qc = QuantumCircuit(2)\n"
        "other = QuantumCircuit(2)\n"
        "other.measure_all()\n"
        "qc.tensor(other, inplace=True)\n"
        "StatevectorSampler().run([qc])\n"
    )


def test_composing_with_an_unproven_operand_gives_an_unprovable_result() -> None:
    assert not fires(
        "qc = QuantumCircuit(2)\ncombined = qc.compose(loaded)\n"
        "StatevectorSampler().run([combined])\n"
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("Measure", []), ("XGate", ["QXL103"])],
)
def test_appending_the_operation_class_itself_is_understood(
    operation: str, expected: list[str]
) -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.circuit import Measure\n"
        "from qiskit.circuit.library import XGate\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2, 2)\n"
        f"qc.append({operation}, [0], [0])\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == expected


# Result chains ----------------------------------------------------------


def test_least_busy_returns_a_legacy_backend() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService()\n"
        "counts = service.least_busy().run(qc).result().get_counts()\n"
    )
    assert codes(lint(source)) == []


def test_an_empty_pub_tuple_is_skipped_and_the_remaining_pub_still_analysed() -> None:
    assert fires("qc = QuantumCircuit(1)\nStatevectorSampler().run([(), (qc, None)])\n")


@pytest.mark.parametrize(
    ("statement", "expected"),
    [("dists = result.quasi_dists", ["QXL102"]), ("del result.quasi_dists", [])],
)
def test_quasi_dists_is_reported_when_read_and_not_when_deleted(
    statement: str, expected: list[str]
) -> None:
    source = (
        SAMPLER + "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        f"{statement}\n"
    )
    assert codes(lint(source)) == expected


# Notebook rewriting markers ---------------------------------------------


@pytest.mark.parametrize(
    ("statement", "expected"),
    [("out = __qxlint_unknown__()", ["QXL103"]), ("__qxlint_barrier__()", [])],
)
def test_the_notebook_markers_differ_in_whether_they_void_the_namespace(
    statement: str, expected: list[str]
) -> None:
    source = SAMPLER + f"qc = QuantumCircuit(1)\n{statement}\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == expected


# IPython magic call forms -----------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        'get_ipython().run_line_magic("run", "setup.py")',
        'get_ipython().run_line_magic("%RESET", "")',
        'get_ipython().run_cell_magic("bash", "", "ls")',
    ],
)
def test_a_namespace_mutating_magic_is_a_barrier(call: str) -> None:
    assert not fires(f"qc = QuantumCircuit(1)\n{call}\nStatevectorSampler().run([qc])\n")


@pytest.mark.parametrize(
    "call",
    [
        'get_ipython().run_line_magic("matplotlib", "inline")',
        'get_ipython().run_line_magic(chosen, "")',
        'get_ipython().system("ls")',
        'get_ipython().getoutput("ls")',
    ],
)
def test_a_magic_that_cannot_rebind_a_name_keeps_the_facts(call: str) -> None:
    assert fires(f"qc = QuantumCircuit(1)\n{call}\nStatevectorSampler().run([qc])\n")


@pytest.mark.parametrize(
    "call",
    ['shell.run_line_magic("run", "setup.py")', 'make_shell().run_line_magic("run", "setup.py")'],
)
def test_only_the_get_ipython_receiver_makes_a_magic_call(call: str) -> None:
    assert fires(f"qc = QuantumCircuit(1)\n{call}\nStatevectorSampler().run([qc])\n")


def test_appending_to_a_list_that_forgot_its_contents_escapes_the_circuit() -> None:
    assert not fires(
        "qc = QuantumCircuit(1)\n"
        "circuits = [*load()]\n"
        "circuits.append(qc)\n"
        "StatevectorSampler().run([qc])\n"
    )
