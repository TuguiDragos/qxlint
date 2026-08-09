"""QXL101 on all three wrong receivers."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

qc = QuantumCircuit(2)
qc.measure_all()
result = StatevectorSampler().run([qc]).result()

on_result = result.get_counts()
on_pub = result[0].get_counts()
on_data_bin = result[0].data.get_counts()
