"""QXL105: a measured circuit handed to StatevectorEstimator."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import PrimitiveRunEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import Escape, TriState

# Deliberately narrow. StatevectorEstimator raises; what a Runtime EstimatorV2
# does cannot be established without contacting the service, so it is excluded.
STATEVECTOR_ESTIMATOR = "qiskit.primitives.StatevectorEstimator"


@register
class MeasuredCircuitToStatevectorEstimator(Rule):
    meta = RuleMeta(
        code="QXL105",
        name="measured-circuit-to-statevector-estimator",
        summary="circuit with measurements passed to a StatevectorEstimator",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "An Estimator computes expectation values from the statevector and "
            "has no use for classical bits. StatevectorEstimator refuses them "
            "outright: verified on Qiskit 2.5.2, it raises "
            "QiskitError('Cannot apply instruction with classical bits: "
            "measure'). This usually appears when a circuit written for a "
            "Sampler is reused for an Estimator without removing the "
            "measurements."
        ),
        when_legitimate=(
            "Never for StatevectorEstimator, which is the only implementation "
            "this rule looks at. Other estimators are excluded on purpose: what "
            "a Runtime EstimatorV2 does with a measured circuit is decided "
            "server side and cannot be established offline, so qxlint says "
            "nothing about it rather than guessing. BackendEstimatorV2 is "
            "excluded for the same reason."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorEstimator\n"
            "from qiskit.quantum_info import SparsePauliOp\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.h(0)\n"
            "qc.measure_all()\n"
            "StatevectorEstimator().run([(qc, SparsePauliOp('ZZ'))])\n"
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
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.StatevectorEstimator",
        ),
    )

    def on_primitive_run(self, event: PrimitiveRunEvent, ctx: RuleContext) -> None:
        if event.primitive_facts.origin != STATEVECTOR_ESTIMATOR:
            return
        for pub in event.pubs:
            facts = pub.facts
            if facts is None or facts.escape is not Escape.LOCAL:
                continue
            if facts.read_measurement() is not TriState.DEFINITELY_PRESENT:
                continue
            ctx.emit(
                Finding(
                    rule=self.meta.code,
                    message=(
                        "circuit has measurements but is passed to a "
                        "StatevectorEstimator, which raises on classical bits"
                    ),
                    location=ctx.source.location(event.node),
                    severity=self.meta.severity,
                    tier=self.meta.tier,
                    fix_hint="drop the measurements, or use qc.remove_final_measurements()",
                    context={"estimator": STATEVECTOR_ESTIMATOR},
                )
            )
            # One finding per run call. The location is the call, so a second
            # defective pub would repeat the same diagnostic at the same place.
            return
