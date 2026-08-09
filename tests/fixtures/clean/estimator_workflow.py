"""Estimators take unmeasured circuits. Nothing here may be reported."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorEstimator
from qiskit.quantum_info import SparsePauliOp


def expectation() -> float:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)

    observable = SparsePauliOp("ZZ")
    result = StatevectorEstimator().run([(qc, observable)]).result()
    return float(result[0].data.evs)
