"""QXL102: quasi_dists read from a V2 result."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import AttributeEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import ObjectKind


@register
class QuasiDistsOnV2Result(Rule):
    meta = RuleMeta(
        code="QXL102",
        name="quasi-dists-on-v2-result",
        summary="quasi_dists read from a Primitives V2 result",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "quasi_dists is a field of the V1 SamplerResult. A V2 PrimitiveResult "
            "has no such attribute and raises AttributeError. V2 exposes counts "
            "through the data bin: result[i].data.<register>.get_counts()."
        ),
        when_legitimate=(
            "Reading quasi_dists from a V1 `qiskit.primitives.SamplerResult` is "
            "still valid, and this rule does not fire there. The same holds for "
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
        if event.attribute != "quasi_dists":
            return
        facts = event.receiver_facts
        if facts is None or facts.kind is not ObjectKind.PRIMITIVE_RESULT_V2:
            return
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=(
                    "quasi_dists does not exist on a V2 PrimitiveResult; read "
                    "result[i].data.<register>.get_counts() instead"
                ),
                location=ctx.source.location(event.node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint="result[0].data.<register>.get_counts()",
                context={"receiverKind": facts.kind.value},
            )
        )
