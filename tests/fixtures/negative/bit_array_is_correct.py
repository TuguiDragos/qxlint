"""The realistic case where get_counts() is right. QXL101 must not fire."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

qc = QuantumCircuit(2)
qc.measure_all()
result = StatevectorSampler().run([qc]).result()

bit_array = result[0].data.meas
counts = bit_array.get_counts()

joined = result[0].join_data().get_counts()
