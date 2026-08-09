"""QXL102 on a V2 result."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

qc = QuantumCircuit(2)
qc.measure_all()
result = StatevectorSampler().run([qc]).result()

dists = result.quasi_dists
