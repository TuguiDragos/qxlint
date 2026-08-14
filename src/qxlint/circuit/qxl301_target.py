"""QXL301: circuit against a Target.

Contract, stated because the two are not the same thing: this checks **generic
compatibility with a Qiskit Target**, not IBM Runtime acceptance. It mirrors the
structure of the client side check in qiskit-ibm-runtime 0.48.0
(``utils/utils.py::is_isa_circuit``) but deliberately stops there:

* qubit count is compared with ``>``, exactly as upstream does, so a narrower
  circuit passes;
* every instruction is checked with ``Target.instruction_supported(name, qargs)``,
  the control flow operation itself included. Upstream checks it before it
  recurses, so a target without ``if_else`` rejects the circuit even when every
  instruction inside the block is supported;
* control flow blocks are recursed into with qubit indices remapped;
* ``barrier`` and ``store`` are excepted. Upstream added ``store`` to that set in
  0.47.0, so a project on 0.46 or earlier can still be rejected for it;
* layout is **not** checked. Upstream's docstring claims it is, but the code
  never reads ``circuit.layout``;
* ``rzz`` angle bounds and other IBM specific validation are **not** checked.

Nothing here asserts what the IBM service will do server side.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qxlint.circuit.walker import circuit_name, walk
from qxlint.diagnostics import CircuitLocation, Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import Rule, RuleMeta

EXEMPT_OPERATIONS = frozenset({"barrier", "store"})


@register
class TargetCompatibility(Rule):
    meta = RuleMeta(
        code="QXL301",
        name="target-compatibility",
        summary="circuit uses an operation or qubit the target does not support",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "A backend accepts only the operations in its Target, on the qubit "
            "pairs its coupling map allows. Submitting anything else fails after "
            "the job is queued. This is a target compatibility check, not a "
            "hardware readiness check: readiness also involves layout, observable "
            "handling, option combinations and target freshness, none of which "
            "this rule looks at."
        ),
        when_legitimate=(
            "When the circuit is meant to be transpiled later. Running "
            "generate_preset_pass_manager(backend=...).run(qc) before submission "
            "is the normal fix, and an untranspiled circuit is not a defect on its "
            "own. This rule is only meaningful on a circuit you believe is already "
            "ISA compliant, which is why it is a library call rather than a "
            "file linting rule."
        ),
        examples_checkable=False,
        bad_example=(
            "qc = QuantumCircuit(2)\n"
            "qc.cx(0, 1)\n"
            "qxlint.check_target(qc, backend.target)  # cx is not native on Heron\n"
        ),
        good_example=(
            "pm = generate_preset_pass_manager(optimization_level=1, backend=backend)\n"
            "qxlint.check_target(pm.run(qc), backend.target)\n"
        ),
        references=(
            "https://github.com/Qiskit/qiskit-ibm-runtime/blob/main/qiskit_ibm_runtime/utils/utils.py",
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.transpiler.Target",
        ),
    )

    def check(self, circuit: Any, target: Any) -> Iterator[Finding]:
        name = circuit_name(circuit)

        target_qubits = getattr(target, "num_qubits", None)
        if target_qubits is not None and circuit.num_qubits > target_qubits:
            yield Finding(
                rule=self.meta.code,
                message=(
                    f"circuit has {circuit.num_qubits} qubits but the target "
                    f"provides {target_qubits}"
                ),
                # The width mismatch is about the circuit, not an instruction.
                location=CircuitLocation(circuit_name=name, path=()),
                severity=self.meta.severity,
                tier=self.meta.tier,
                context={"circuitQubits": str(circuit.num_qubits)},
            )
            return

        for visited in walk(circuit):
            operation = visited.name
            if operation in EXEMPT_OPERATIONS:
                continue
            if -1 in visited.qubits:
                continue
            if target.instruction_supported(operation, visited.qubits):
                continue
            yield Finding(
                rule=self.meta.code,
                message=(
                    f"operation '{operation}' on qubits {list(visited.qubits)} is "
                    "not supported by the target"
                ),
                location=CircuitLocation(
                    circuit_name=name,
                    path=visited.path,
                    operation=operation,
                    qubits=visited.qubits,
                    clbits=visited.clbits,
                ),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint="transpile against this backend before submitting",
                context={"operation": operation},
            )
