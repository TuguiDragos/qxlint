"""QXL302 (preview): two adjacent identical self inverse gates that cancel."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qxlint.circuit.walker import VisitedInstruction, circuit_name, walk
from qxlint.diagnostics import CircuitLocation, Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import Rule, RuleMeta
from qxlint.semantics.model import SELF_INVERSE_GATES


@register
class RedundantSelfInversePair(Rule):
    meta = RuleMeta(
        code="QXL302",
        name="redundant-self-inverse-pair",
        summary="two adjacent identical self inverse gates cancel out",
        tier=Tier.PREVIEW,
        severity=Severity.INFO,
        rationale=(
            "A gate that is exactly its own inverse, applied twice in a row to the "
            "same ordered qubits, is the identity. The allow list is explicit and "
            "was built by squaring each operator matrix and comparing with the "
            "identity, not by guessing from the class name: iSwap, S, T, SX and DCX "
            "look similar and are not self inverse, so they are absent. Qubit order "
            "matters, so cx(0, 1) followed by cx(1, 0) does not cancel."
        ),
        when_legitimate=(
            "Benchmarking, noise characterisation, randomised benchmarking and "
            "calibration sequences deliberately apply cancelling pairs to build a "
            "known identity circuit. Dynamical decoupling sequences do the same. "
            "This is why the rule is preview and informational rather than default "
            "on. It also only looks at immediately adjacent instructions, because "
            "allowing anything in between requires commutativity analysis."
        ),
        examples_checkable=False,
        bad_example="qc.h(0)\nqc.h(0)\n",
        good_example="qc.h(0)\nqc.x(0)\nqc.h(0)\n",
    )

    def check(self, circuit: Any) -> Iterator[Finding]:
        name = circuit_name(circuit)
        by_scope: dict[tuple[object, ...], VisitedInstruction | None] = {}

        for visited in walk(circuit):
            scope = visited.path[:-1]
            previous = by_scope.get(scope)
            by_scope[scope] = visited

            if previous is None or not _cancels(previous, visited):
                continue
            # Both instructions are used up by this pair, so the next one starts
            # a fresh pair. Without this, three h in a row reported two
            # overlapping pairs for a circuit that contains one cancellation,
            # and four reported three.
            by_scope[scope] = None
            yield Finding(
                rule=self.meta.code,
                message=(
                    f"'{visited.name}' applied twice in a row on qubits "
                    f"{list(visited.qubits)}; the pair is the identity"
                ),
                location=CircuitLocation(
                    circuit_name=name,
                    path=visited.path,
                    operation=visited.name,
                    qubits=visited.qubits,
                    clbits=visited.clbits,
                ),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint="remove both instructions unless the identity is intentional",
                context={"previousIndex": str(previous.path[-1].index)},
            )


def _cancels(first: VisitedInstruction, second: VisitedInstruction) -> bool:
    """Both instructions must be the same parameterless self inverse gate."""
    if first.name != second.name or first.name not in SELF_INVERSE_GATES:
        return False
    if first.qubits != second.qubits or first.clbits or second.clbits:
        return False
    if _params(first) or _params(second):
        return False
    return _base_class(first) is _base_class(second)


def _params(visited: VisitedInstruction) -> Any:
    return getattr(visited.instruction.operation, "params", ())


def _base_class(visited: VisitedInstruction) -> Any:
    operation = visited.instruction.operation
    return getattr(operation, "base_class", type(operation))
