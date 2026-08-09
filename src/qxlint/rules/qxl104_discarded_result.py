"""QXL104: a circuit method whose result is thrown away, making it a no-op."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import MethodCallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import ObjectKind
from qxlint.semantics.values import ConstBool

# Methods that return a new circuit unless told otherwise. The default for each
# was read from the signature on Qiskit 2.5.1 and the no-op confirmed by running
# it: `qc.compose(other)` as a statement leaves qc with zero instructions.
DEFAULT_COPYING = {
    "compose": "inplace",
    "tensor": "inplace",
    "assign_parameters": "inplace",
}

# Methods that mutate by default, so only an explicit inplace=False is a no-op.
DEFAULT_INPLACE = {
    "measure_all": "inplace",
    "measure_active": "inplace",
    "remove_final_measurements": "inplace",
}

# Methods that always return a new circuit and never mutate.
ALWAYS_COPYING = frozenset(
    {
        "copy",
        "copy_empty_like",
        "decompose",
        "inverse",
        "power",
        "repeat",
        "reverse_ops",
        "reverse_bits",
    }
)


@register
class DiscardedCircuitResult(Rule):
    meta = RuleMeta(
        code="QXL104",
        name="discarded-circuit-result",
        summary="a circuit method that returns a new circuit is called and its result dropped",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "Several QuantumCircuit methods return a new circuit rather than "
            "mutating the receiver, and `compose`, `tensor` and "
            "`assign_parameters` default to `inplace=False`. Written as a bare "
            "statement the call does nothing at all, and nothing reports it: "
            "verified on Qiskit 2.5.1, `qc.compose(other)` as a statement leaves "
            "`qc` with zero instructions, and `qc.assign_parameters({t: 1.0})` "
            "leaves the parameter unbound. The circuit then runs, and the result "
            "is wrong rather than missing."
        ),
        when_legitimate=(
            "When the method really does mutate, which is why the rule reads the "
            "`inplace` argument instead of the method name alone: "
            "`qc.compose(other, inplace=True)` and `qc.measure_all()` are both "
            "correct and neither is flagged. It also only fires on a bare "
            "expression statement, so assigning or returning the result is never "
            "flagged, and only on a receiver proven to be a circuit."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n\n"
            "qc = QuantumCircuit(2)\n"
            "other = QuantumCircuit(2)\n"
            "other.h(0)\n"
            "qc.compose(other)\n"
        ),
        good_example=(
            "from qiskit import QuantumCircuit\n\n"
            "qc = QuantumCircuit(2)\n"
            "other = QuantumCircuit(2)\n"
            "other.h(0)\n"
            "qc = qc.compose(other)\n"
        ),
        references=("https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.circuit.QuantumCircuit",),
    )

    def on_method_call(self, event: MethodCallEvent, ctx: RuleContext) -> None:
        if not event.result_discarded:
            return
        facts = event.receiver_facts
        if facts is None or facts.kind is not ObjectKind.CIRCUIT:
            return

        method = event.method
        reason: str | None = None

        if method in ALWAYS_COPYING:
            reason = f"{method}() always returns a new circuit"
        elif method in DEFAULT_COPYING:
            inplace = event.kwargs.get(DEFAULT_COPYING[method])
            if not (isinstance(inplace, ConstBool) and inplace.value is True):
                reason = f"{method}() defaults to inplace=False"
        elif method in DEFAULT_INPLACE:
            inplace = event.kwargs.get(DEFAULT_INPLACE[method])
            if isinstance(inplace, ConstBool) and inplace.value is False:
                reason = f"{method}(inplace=False) returns a new circuit"

        if reason is None:
            return

        fix = (
            "assign the result, or pass inplace=True"
            if method in DEFAULT_COPYING
            else "assign the result"
        )
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=f"this statement does nothing: {reason} and the result is discarded",
                location=ctx.source.location(event.attribute_node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint=fix,
                context={"method": method},
            )
        )
