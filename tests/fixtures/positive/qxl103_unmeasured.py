"""QXL103 in the three shapes a Sampler call usually takes."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

sampler = StatevectorSampler()

direct = QuantumCircuit(2)
direct.h(0)
sampler.run([direct])

in_a_list = QuantumCircuit(2)
in_a_list.h(0)
pubs = [in_a_list]
sampler.run(pubs)

appended = QuantumCircuit(2, 2)
appended.h(0)
circuits = []
circuits.append(appended)
sampler.run(circuits)
