"""The transpile then sample pipeline stays analysable and stays clean."""

from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
from qiskit.transpiler import generate_preset_pass_manager


def run(backend: object) -> dict[str, int]:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()

    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
    isa = pm.run([qc])

    result = StatevectorSampler().run(isa).result()
    return result[0].data.meas.get_counts()
