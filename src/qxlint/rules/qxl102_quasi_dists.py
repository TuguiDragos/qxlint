"""QXL102: a V1 result field read from a V2 result."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import AttributeEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import ObjectKind

# Fields of the V1 result classes, with what replaces each one in V2. Verified
# on Qiskit 2.5.2: both raise AttributeError on a PrimitiveResult, from either
# primitive, while `metadata` exists on V2 and is deliberately absent here.
# field -> (what the message names, what the fix hint offers)
V1_RESULT_FIELDS = {
    "quasi_dists": (
        "result[i].data.<register>.get_counts()",
        "result[0].data.<register>.get_counts()",
    ),
    "values": ("result[i].data.evs", "result[0].data.evs"),
}


@register
class V1ResultFieldOnV2Result(Rule):
    meta = RuleMeta(
        code="QXL102",
        name="v1-result-field-on-v2-result",
        summary="a V1 result field read from a Primitives V2 result",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "quasi_dists is a field of the V1 SamplerResult and values is a field "
            "of the V1 EstimatorResult. A V2 PrimitiveResult has neither and "
            "raises AttributeError, verified on Qiskit 2.5.2 for both primitives. "
            "V2 exposes counts through the data bin as "
            "result[i].data.<register>.get_counts(), and expectation values as "
            "result[i].data.evs."
        ),
        when_legitimate=(
            "Reading quasi_dists from a V1 `qiskit.primitives.SamplerResult`, or "
            "values from a V1 `EstimatorResult`, is still valid, and this rule "
            "does not fire there. The same holds for "
            "a Runtime V1 result: `qiskit_ibm_runtime.Sampler` was SamplerV1 "
            "until 0.28, so on a target proven to predate that release its "
            "result is not a V2 one and nothing is reported. It also stays silent "
            "on any object whose type cannot be proven, so a helper that returns "
            "an unannotated result is never flagged on the strength of the "
            "attribute name alone."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.measure_all()\n"
            "result = StatevectorSampler().run([qc]).result()\n"
            "dists = result.quasi_dists\n"
        ),
        good_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.measure_all()\n"
            "result = StatevectorSampler().run([qc]).result()\n"
            "counts = result[0].data.meas.get_counts()\n"
        ),
        references=(
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.SamplerResult",
        ),
    )

    def on_attribute(self, event: AttributeEvent, ctx: RuleContext) -> None:
        entry = V1_RESULT_FIELDS.get(event.attribute)
        if entry is None:
            return
        described, hint = entry
        facts = event.receiver_facts
        if facts is None or facts.kind is not ObjectKind.PRIMITIVE_RESULT_V2:
            return
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=(
                    f"{event.attribute} does not exist on a V2 PrimitiveResult; "
                    f"read {described} instead"
                ),
                location=ctx.source.location(event.node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint=hint,
                context={"receiverKind": facts.kind.value, "field": event.attribute},
            )
        )
