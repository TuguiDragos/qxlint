"""Aliasing, branches and loops. All of this is correct code."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

sampler = StatevectorSampler()

aliased = QuantumCircuit(1)
alias = aliased
alias.measure_all()
sampler.run([aliased])

conditional = QuantumCircuit(1)
if want_measurements():
    conditional.measure_all()
sampler.run([conditional])

looped = QuantumCircuit(3, 3)
for qubit in range(3):
    looped.measure(qubit, qubit)
sampler.run([looped])

handed_off = QuantumCircuit(2)
prepare(handed_off)
sampler.run([handed_off])
