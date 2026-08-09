"""Current QiskitRuntimeService usage. The channel argument is not needed."""

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler


def least_busy_sampler(token: str) -> Sampler:
    service = QiskitRuntimeService(token=token)
    return Sampler(mode=service.least_busy())


def explicit_platform(token: str) -> QiskitRuntimeService:
    return QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
