"""QXL104: a circuit method whose result is discarded.

The negative cases here are not hypothetical. The first corpus scan of this rule
produced 57 findings, and 50 of them were calls inside `assertRaises`, where
discarding the result is the entire point.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nother = QuantumCircuit(2)\n"


def fires(body: str) -> bool:
    return "QXL104" in codes(lint(HEADER + body))


# Positives --------------------------------------------------------------


def test_compose_defaults_to_a_copy() -> None:
    assert fires("qc.compose(other)\n")


def test_tensor_defaults_to_a_copy() -> None:
    assert fires("qc.tensor(other)\n")


def test_assign_parameters_defaults_to_a_copy() -> None:
    assert fires("qc.assign_parameters({})\n")


def test_measure_all_not_in_place() -> None:
    assert fires("qc.measure_all(inplace=False)\n")


def test_remove_final_measurements_not_in_place() -> None:
    assert fires("qc.remove_final_measurements(inplace=False)\n")


@pytest.mark.parametrize(
    "method", ["copy", "copy_empty_like", "decompose", "inverse", "reverse_ops", "reverse_bits"]
)
def test_methods_that_always_return_a_new_circuit(method: str) -> None:
    assert fires(f"qc.{method}()\n")


def test_the_real_world_case_from_the_corpus() -> None:
    # Qiskit's own test_sabre_swap.py: the comment states the intent, and the
    # default inplace=False means it never happens.
    source = (
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(3, 1)\n"
        "qc.compose(other_definition, [0, 1, 2], [])  # Unroll CCX to 2q operations.\n"
        "qc.h(0)\n"
    )
    assert "QXL104" in codes(lint(source))


# Negatives --------------------------------------------------------------


def test_inplace_true_really_mutates() -> None:
    assert not fires("qc.compose(other, inplace=True)\n")


def test_measure_all_defaults_to_in_place() -> None:
    assert not fires("qc.measure_all()\n")


def test_remove_final_measurements_defaults_to_in_place() -> None:
    assert not fires("qc.remove_final_measurements()\n")


def test_assigning_the_result_is_correct() -> None:
    assert not fires("combined = qc.compose(other)\n")


def test_returning_the_result_is_correct() -> None:
    source = (
        "from qiskit import QuantumCircuit\ndef build(qc, other):\n    return qc.compose(other)\n"
    )
    assert codes(lint(source)) == []


def test_chaining_the_result_is_correct() -> None:
    assert not fires("qc.compose(other).measure_all()\n")


def test_gate_methods_are_not_reported() -> None:
    assert not fires("qc.h(0)\nqc.measure_all()\n")


def test_unknown_receiver_is_not_reported() -> None:
    assert codes(lint("thing.compose(other)\n")) == []


def test_inside_assert_raises_the_discard_is_the_point() -> None:
    source = (
        HEADER + "with self.assertRaises(CircuitError):\n    qc.compose(other, [1, 1], [0, 1])\n"
    )
    assert codes(lint(source)) == []


def test_inside_assert_raises_regex() -> None:
    source = (
        HEADER + 'with self.assertRaisesRegex(CircuitError, "Duplicate"):\n    qc.compose(other)\n'
    )
    assert codes(lint(source)) == []


def test_inside_pytest_raises() -> None:
    source = HEADER + "with pytest.raises(TypeError):\n    qc.copy([1, 2])\n"
    assert codes(lint(source)) == []


def test_inside_a_guarded_try_block() -> None:
    source = HEADER + "try:\n    qc.decompose()\nexcept TypeError:\n    pass\n"
    assert codes(lint(source)) == []


def test_a_try_without_handlers_still_reports() -> None:
    # `try/finally` guards cleanup, not an exception, so a no-op is still a no-op.
    source = HEADER + "try:\n    qc.compose(other)\nfinally:\n    cleanup()\n"
    assert "QXL104" in codes(lint(source))


def test_nesting_restores_reporting_after_the_block() -> None:
    source = (
        HEADER + "with self.assertRaises(CircuitError):\n    qc.compose(other)\nqc.tensor(other)\n"
    )
    assert codes(lint(source)) == ["QXL104"]


# An inplace argument these methods do not have ---------------------------
#
# None of the always copying methods takes `inplace`. Verified on Qiskit 2.5.2:
# all eight raise TypeError on the unexpected keyword. Saying the statement does
# nothing would describe an outcome the call never reaches.


@pytest.mark.parametrize(
    "method", ["copy", "copy_empty_like", "decompose", "inverse", "reverse_ops", "reverse_bits"]
)
def test_an_inplace_argument_these_methods_lack_is_reported_as_a_raise(method: str) -> None:
    source = (
        f"from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.{method}(inplace=True)\n"
    )
    findings = lint(source)
    assert codes(findings) == ["QXL104"]
    assert (
        findings[0].message
        == f"this statement raises TypeError: {method}() has no inplace argument"
    )
    assert findings[0].fix_hint == "drop the inplace argument and assign the result"


def test_without_that_argument_the_message_is_still_the_no_op_one() -> None:
    source = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.decompose()\n"
    findings = lint(source)
    assert codes(findings) == ["QXL104"]
    assert "does nothing" in findings[0].message


def test_a_method_that_really_takes_inplace_is_still_silent() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(2)\n"
        "other = QuantumCircuit(2)\n"
        "qc.compose(other, inplace=True)\n"
    )
    assert codes(lint(source)) == []
