"""QXL103: a circuit with no measurements handed to a Sampler."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import PrimitiveRunEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.model import SAMPLER_KINDS
from qxlint.semantics.objects import Escape, TriState


@register
class UnmeasuredCircuitToSampler(Rule):
    meta = RuleMeta(
        code="QXL103",
        name="unmeasured-circuit-to-sampler",
        summary="circuit with no measurement instructions passed to a SamplerV2",
        tier=Tier.DEFAULT,
        severity=Severity.WARNING,
        rationale=(
            "A Sampler reports classical bits. A circuit with no measurement "
            "instruction produces nothing useful, and the failure is quiet. With "
            "no classical register, Qiskit 2.5.2 emits only a UserWarning and "
            "returns an empty data bin. With a classical register but no measure "
            "instruction, there is no warning at all and every shot reads as "
            "zeros, which looks like a physics result rather than a mistake."
        ),
        when_legitimate=(
            "Never for a Sampler, which is why the rule is limited to one. An "
            "unmeasured circuit is the correct and normal input to an Estimator, "
            "and this rule never looks at Estimators. It also requires proof: it "
            "fires only when the circuit was built and mutated in view, never "
            "reached unmodelled code, and has no measurement on any path."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.h(0)\n"
            "qc.cx(0, 1)\n"
            "StatevectorSampler().run([qc])\n"
        ),
        good_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.h(0)\n"
            "qc.cx(0, 1)\n"
            "qc.measure_all()\n"
            "StatevectorSampler().run([qc])\n"
        ),
        references=(
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.StatevectorSampler",
        ),
    )

    def on_primitive_run(self, event: PrimitiveRunEvent, ctx: RuleContext) -> None:
        if event.primitive_facts.kind not in SAMPLER_KINDS:
            return
        for pub in event.pubs:
            facts = pub.facts
            if facts is None or facts.escape is not Escape.LOCAL:
                continue
            if facts.read_measurement() is not TriState.DEFINITELY_ABSENT:
                continue
            ctx.emit(
                Finding(
                    rule=self.meta.code,
                    message=(
                        "circuit has no measurement instructions but is passed to "
                        "a SamplerV2; the result carries no counts"
                    ),
                    location=ctx.source.location(event.node),
                    severity=self.meta.severity,
                    tier=self.meta.tier,
                    fix_hint=(
                        "add measure_all(), or call qxlint.assert_sampler_ready(pubs) "
                        "before run() to decide it on the real circuit"
                    ),
                    context={"primitiveKind": event.primitive_facts.kind.value},
                )
            )
            # One finding per run call. The location is the call, so a second
            # defective pub would repeat the same diagnostic at the same place.
            return
