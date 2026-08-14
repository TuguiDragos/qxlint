"""QXL300: control flow nested deeper than the walker descends.

The circuit walker stops at a fixed depth so a pathological circuit cannot
exhaust the interpreter stack. Stopping silently is the problem: every circuit
rule then returns nothing for the part it never looked at, and no findings reads
as a clean circuit. This rule turns that silence into an answer.

It is the Engine B counterpart of QXL000. Both report that qxlint could not
finish looking, rather than that the code is fine.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from qxlint.circuit.walker import MAX_DEPTH, circuit_name, walk
from qxlint.diagnostics import CircuitLocation, Finding, InstructionStep, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import Rule, RuleMeta


@register
class IncompleteCircuitAnalysis(Rule):
    meta = RuleMeta(
        code="QXL300",
        name="analysis-incomplete",
        summary=f"control flow nests deeper than the {MAX_DEPTH} levels qxlint walks",
        tier=Tier.DEFAULT,
        severity=Severity.WARNING,
        rationale=(
            "The circuit rules descend into control flow blocks to a fixed "
            f"depth of {MAX_DEPTH}, which bounds the work a circuit can ask for. "
            "Anything below that depth is never visited, so an unsupported "
            "operation there produces no finding. Without this rule the result "
            "is indistinguishable from a circuit that really is compatible, and "
            "a caller would read the empty list as an answer it is not."
        ),
        when_legitimate=(
            "Never a defect in the circuit itself: it reports a limit of "
            "qxlint, not a mistake in the code. It is still worth acting on, "
            "because the checks that ran cover only part of the circuit. "
            "Flattening the nesting, or checking the inner blocks as circuits "
            "of their own, gives a complete answer."
        ),
        examples_checkable=False,
        bad_example=(
            "# thirteen nested if_else blocks; the innermost is never visited\n"
            "qxlint.check_target(deeply_nested, backend.target)\n"
        ),
        good_example=(
            "# the inner block checked as a circuit in its own right\n"
            "qxlint.check_target(inner_block, backend.target)\n"
        ),
        references=("https://quantum.cloud.ibm.com/docs/api/qiskit/circuit_classical",),
    )

    def check(self, circuit: Any) -> Iterator[Finding]:
        name = circuit_name(circuit)
        truncated: list[tuple[InstructionStep, ...]] = []
        for _ in walk(circuit, truncated=truncated):
            pass

        for path in truncated:
            yield Finding(
                rule=self.meta.code,
                message=(
                    f"control flow nested deeper than {MAX_DEPTH} levels was not "
                    "analysed; findings for this circuit are incomplete"
                ),
                location=CircuitLocation(circuit_name=name, path=path),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint="check the inner block as a circuit of its own",
                context={"maxDepth": str(MAX_DEPTH)},
            )
