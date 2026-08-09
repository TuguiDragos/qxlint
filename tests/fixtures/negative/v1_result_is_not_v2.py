"""quasi_dists is a real V1 field. QXL102 must not fire on it."""

from qiskit.primitives import SamplerResult

result = SamplerResult(quasi_dists=[{0: 0.5, 3: 0.5}], metadata=[{}])
dists = result.quasi_dists
