"""The canonical Primitives V2 Sampler workflow. Must report nothing."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler


def bell_counts(shots: int = 1024) -> dict[str, int]:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()

    result = StatevectorSampler().run([qc], shots=shots).result()
    return result[0].data.meas.get_counts()


def named_register_counts() -> dict[str, int]:
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    result = StatevectorSampler().run([qc]).result()
    return result[0].data.c.get_counts()
