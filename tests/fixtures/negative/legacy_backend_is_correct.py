"""Legacy backend results still have get_counts(). QXL101 must not fire."""

from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService()
backend = service.backend("some-backend")

counts = backend.run(circuit).result().get_counts()
