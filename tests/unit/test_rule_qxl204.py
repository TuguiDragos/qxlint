"""QXL204: a V2 primitive's run() called with the V1 argument grammar."""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorEstimator, StatevectorSampler\n"
    "from qiskit.quantum_info import SparsePauliOp\n"
    "qc = QuantumCircuit(2)\n"
    "qc.measure_all()\n"
    "obs = SparsePauliOp('ZZ')\n"
    "est = StatevectorEstimator()\n"
    "sam = StatevectorSampler()\n"
)


@pytest.mark.parametrize(
    "call",
    [
        # Each verified on Qiskit 2.5.2 to raise TypeError.
        "est.run([qc], [obs])",
        "est.run(circuits=[qc], observables=[obs])",
        "est.run([(qc, obs)], shots=100)",
        "sam.run(circuits=[qc])",
        "sam.run([qc], parameter_values=[])",
        "sam.run([qc], observables=[obs])",
    ],
)
def test_the_v1_grammar_is_reported(call: str) -> None:
    assert "QXL204" in codes(lint(HEADER + call + "\n"))


@pytest.mark.parametrize(
    "call",
    [
        # Each verified on Qiskit 2.5.2 to run.
        "sam.run([qc], shots=100)",
        "est.run([(qc, obs)], precision=0.1)",
        "sam.run([qc])",
        "est.run([(qc, obs)])",
    ],
)
def test_the_v2_grammar_is_not_reported(call: str) -> None:
    assert "QXL204" not in codes(lint(HEADER + call + "\n"))


def test_shots_is_only_wrong_on_an_estimator() -> None:
    assert "QXL204" in codes(lint(HEADER + "est.run([(qc, obs)], shots=1)\n"))
    assert "QXL204" not in codes(lint(HEADER + "sam.run([qc], shots=1)\n"))


def test_a_runtime_primitive_is_covered_too() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime import SamplerV2\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "SamplerV2(mode=backend).run(circuits=[qc])\n"
    )
    assert "QXL204" in codes(lint(source))


def test_an_unproven_receiver_is_not_reported() -> None:
    # The rule reads the receiver's kind, never the method name alone.
    assert codes(lint("thing.run(circuits=[1], observables=[2])\n")) == []


def test_a_v1_primitive_keeps_its_own_grammar() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime import Sampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        "Sampler().run(circuits=qc)\n"
    )
    assert codes(lint(source, runtime="0.27")) == []


def test_an_incomplete_argument_list_is_not_counted() -> None:
    # A dropped star argument shifts the count, so arity proves nothing.
    assert "QXL204" not in codes(lint(HEADER + "est.run(*pubs, extra)\n"))


def test_the_message_names_the_primitive_and_the_fix() -> None:
    finding = next(f for f in lint(HEADER + "est.run([qc], [obs])\n") if f.rule == "QXL204")
    assert "an EstimatorV2" in finding.message
    assert "raises TypeError" in finding.message
    assert finding.fix_hint == "pass one list of pubs"


def test_a_bare_circuit_is_reported() -> None:
    # Verified on Qiskit 2.5.2: run(qc) raises
    # ValueError: An invalid Sampler pub-like was given.
    findings = lint(HEADER + "sam.run(qc)\n")
    assert "QXL204" in codes(findings)
    finding = next(f for f in findings if f.rule == "QXL204")
    assert "not a circuit" in finding.message
    assert "raises ValueError" in finding.message
    assert finding.fix_hint == "wrap it in a list, run([circuit])"


def test_a_bare_circuit_to_an_estimator_is_reported() -> None:
    assert "QXL204" in codes(lint(HEADER + "est.run(qc)\n"))


def test_the_list_form_is_still_accepted() -> None:
    assert "QXL204" not in codes(lint(HEADER + "sam.run([qc])\n"))


def test_an_unproven_argument_is_not_called_a_circuit() -> None:
    assert "QXL204" not in codes(lint(HEADER + "sam.run(whatever)\n"))
