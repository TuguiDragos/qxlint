"""QXL105: a measured circuit handed to StatevectorEstimator."""

from __future__ import annotations

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorEstimator\n"


def test_positive() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\nqc.h(0)\nqc.measure_all()\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == ["QXL105"]


def test_negative_unmeasured_is_the_correct_input() -> None:
    source = HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nStatevectorEstimator().run([(qc, obs)])\n"
    assert codes(lint(source)) == []


def test_negative_after_measurements_are_removed() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\nqc.measure_all()\nqc.remove_final_measurements()\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_a_runtime_estimator() -> None:
    # What a Runtime EstimatorV2 does with a measured circuit is decided server
    # side and cannot be established offline, so the rule says nothing about it.
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime import EstimatorV2\n"
        "qc = QuantumCircuit(2)\nqc.measure_all()\n"
        "EstimatorV2(mode=backend).run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_a_backend_estimator() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import BackendEstimatorV2\n"
        "qc = QuantumCircuit(2)\nqc.measure_all()\n"
        "BackendEstimatorV2(backend=be).run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_a_sampler() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\nqc.measure_all()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_negative_when_the_measurement_is_only_on_one_path() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\nif cond:\n    qc.measure_all()\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_an_escaped_circuit_is_skipped_rather_than_reported() -> None:
    # The measurement is proven, but the circuit reached unmodelled code, so
    # nothing can be claimed about what it holds by the time it is run.
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "holder.circuit = qc\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_only_the_first_measured_circuit_in_a_run_is_reported() -> None:
    source = HEADER + (
        "a = QuantumCircuit(2)\n"
        "a.measure_all()\n"
        "b = QuantumCircuit(2)\n"
        "b.measure_all()\n"
        "StatevectorEstimator().run([(a, obs), (b, obs)])\n"
    )
    assert codes(lint(source)) == ["QXL105"]
