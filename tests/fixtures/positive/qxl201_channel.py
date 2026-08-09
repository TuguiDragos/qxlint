"""QXL201, reported only when the target version is known to have removed it."""

from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService(channel="ibm_quantum", token="redacted")

CHANNEL = "ibm_quantum"
also_service = QiskitRuntimeService(channel=CHANNEL)
