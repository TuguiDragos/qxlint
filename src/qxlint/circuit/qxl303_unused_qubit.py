"""QXL303 (preview): a qubit that no instruction ever touches."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qxlint.circuit.walker import circuit_name, walk
from qxlint.diagnostics import CircuitLocation, Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import Rule, RuleMeta

IGNORED_OPERATIONS = frozenset({"barrier", "delay", "id"})


@register
class UnusedQubit(Rule):
    meta = RuleMeta(
        code="QXL303",
        name="unused-qubit",
        summary="a qubit is declared but never operated on",
        tier=Tier.PREVIEW,
        severity=Severity.INFO,
        rationale=(
            "A qubit with no operation on it contributes nothing to the result but "
            "still widens the circuit, which can force a larger layout and a worse "
            "transpilation. Barriers, delays and identity gates do not count as "
            "use."
        ),
        when_legitimate=(
            "Often, which is why this is preview and informational. A transpiled "
            "circuit is skipped outright, since it carries a `layout` and its "
            "width is the device's rather than the author's. Ancillas reserved "
            "for a later step, fixed width protocol circuits, templates and "
            "circuits built to a register size all legitimately carry unused "
            "qubits, and those are still reported."
        ),
        examples_checkable=False,
        bad_example="qc = QuantumCircuit(3)\nqc.h(0)\nqc.cx(0, 1)\n",
        good_example="qc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\n",
    )

    def check(self, circuit: Any) -> Iterator[Finding]:
        if getattr(circuit, "layout", None) is not None:
            # Transpiled to a target, so the width is the device's and idle
            # physical qubits are the expected outcome rather than a mistake.
            # Measured on FakeSherbrooke: a 2 qubit circuit becomes 127 wide and
            # this rule fired 125 times, which is noise on the one circuit shape
            # QXL301 is meaningful on. `layout` is set by transpilation and by
            # nothing else, so it separates the two cases exactly.
            return
        name = circuit_name(circuit)
        used: set[int] = set()
        for visited in walk(circuit):
            if visited.name in IGNORED_OPERATIONS:
                continue
            used.update(index for index in visited.qubits if index >= 0)

        for index in range(circuit.num_qubits):
            if index in used:
                continue
            yield Finding(
                rule=self.meta.code,
                message=f"qubit {index} is declared but never operated on",
                # No instruction to point at: the finding is about the circuit
                # itself. An empty path renders as the circuit name alone,
                # rather than a fabricated index like [-1].
                location=CircuitLocation(circuit_name=name, path=(), qubits=(index,)),
                severity=self.meta.severity,
                tier=self.meta.tier,
                context={"qubit": str(index)},
            )
