"""QXL204: a V2 primitive's run() called with the V1 argument grammar."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import MethodCallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import ObjectKind

SAMPLERS = frozenset({ObjectKind.SAMPLER_V2})
ESTIMATORS = frozenset({ObjectKind.ESTIMATOR_V2})

# Verified on Qiskit 2.5.2 and qiskit-ibm-runtime 0.49.0: all four V2 primitives
# declare run(pubs, *, shots) or run(pubs, *, precision). None accepts these.
V1_KEYWORDS = ("circuits", "observables", "parameter_values")

READABLE = {ObjectKind.SAMPLER_V2: "a SamplerV2", ObjectKind.ESTIMATOR_V2: "an EstimatorV2"}


@register
class V1RunSignature(Rule):
    meta = RuleMeta(
        code="QXL204",
        name="v1-run-signature",
        summary="a V2 primitive's run() called the way V1 took its arguments",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "The V1 primitives took parallel lists: "
            "`estimator.run(circuits, observables, parameter_values)`. Every V2 "
            "primitive takes one argument, a list of pubs, plus a keyword only "
            "`shots` for a sampler or `precision` for an estimator. Verified on "
            "Qiskit 2.5.2 and qiskit-ibm-runtime 0.49.0: a second positional "
            "argument, any of the three V1 keywords, and `shots` on an estimator "
            "each raise TypeError. Changing the import without changing the call "
            "is the defining break of Primitives V2."
        ),
        when_legitimate=(
            "Never on a proven V2 primitive, because the call cannot execute. "
            "The rule reads the receiver's kind rather than the method name, so "
            "a V1 primitive keeps its own grammar and is not flagged, and so is "
            "any object whose type could not be proven. `shots` is only wrong on "
            "an estimator, and is left alone on a sampler where it is the "
            "documented keyword."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorEstimator\n"
            "from qiskit.quantum_info import SparsePauliOp\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.h(0)\n"
            "StatevectorEstimator().run([qc], [SparsePauliOp('ZZ')])\n"
        ),
        good_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorEstimator\n"
            "from qiskit.quantum_info import SparsePauliOp\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.h(0)\n"
            "StatevectorEstimator().run([(qc, SparsePauliOp('ZZ'))])\n"
        ),
        references=(
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.BaseEstimatorV2",
        ),
    )

    def on_method_call(self, event: MethodCallEvent, ctx: RuleContext) -> None:
        if event.method != "run":
            return
        facts = event.receiver_facts
        if facts is None:
            return
        is_sampler = facts.kind in SAMPLERS
        if not (is_sampler or facts.kind in ESTIMATORS):
            return

        name = READABLE[facts.kind]
        reason: str | None = None
        fix = "pass one list of pubs"

        if event.args_complete and len(event.args) > 1:
            reason = (
                f"run() on {name} takes one argument, a list of pubs; "
                "the V1 form took parallel lists"
            )
        else:
            passed = next((word for word in V1_KEYWORDS if word in event.kwargs), None)
            if passed is not None:
                reason = f"run() on {name} has no {passed} argument; it takes a list of pubs"
            elif not is_sampler and "shots" in event.kwargs:
                reason = f"run() on {name} has no shots argument"
                fix = "use precision=, or set shots in the pub"

        if reason is None:
            return
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=f"{reason}, so this call raises TypeError",
                location=ctx.source.location(event.node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint=fix,
                context={"receiverKind": facts.kind.value},
            )
        )
