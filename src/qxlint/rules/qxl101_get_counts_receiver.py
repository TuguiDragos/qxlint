"""QXL101: get_counts() called on a V2 container instead of the BitArray."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import MethodCallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.objects import ObjectKind

# Receivers where get_counts() does not exist. Verified on Qiskit 2.5.2: each of
# these raises AttributeError.
WRONG_RECEIVERS = frozenset(
    {
        ObjectKind.PRIMITIVE_RESULT_V2,
        ObjectKind.PUB_RESULT_V2,
        ObjectKind.SAMPLER_PUB_RESULT_V2,
        ObjectKind.ESTIMATOR_PUB_RESULT_V2,
        ObjectKind.DATA_BIN,
    }
)

SHAPE = "PrimitiveResult -> PubResult -> .data (DataBin) -> <classical register> (BitArray)"


@register
class GetCountsOnWrongReceiver(Rule):
    meta = RuleMeta(
        code="QXL101",
        name="get-counts-on-wrong-receiver",
        summary="get_counts() called on a container that does not have it",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "In the Primitives V2 result shape, counts live on a BitArray, not on "
            "the result, the pub result, or the data bin. Calling get_counts() on "
            "any of those raises AttributeError at runtime. The shape is "
            f"{SHAPE}. "
            "The register is named by the circuit, so it is not always `meas`."
        ),
        when_legitimate=(
            "Never on these receivers. get_counts() is correct and common on a "
            "BitArray, and on a legacy `backend.run(...).result()`, and this rule "
            "fires on neither. It also stays silent whenever the receiver type "
            "cannot be proven."
        ),
        bad_example=(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n\n"
            "qc = QuantumCircuit(2)\n"
            "qc.measure_all()\n"
            "result = StatevectorSampler().run([qc]).result()\n"
            "counts = result.get_counts()\n"
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
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.BitArray",
            "https://quantum.cloud.ibm.com/docs/api/qiskit/qiskit.primitives.DataBin",
        ),
    )

    def on_method_call(self, event: MethodCallEvent, ctx: RuleContext) -> None:
        if event.method != "get_counts":
            return
        facts = event.receiver_facts
        if facts is None or facts.kind not in WRONG_RECEIVERS:
            return

        kind = facts.kind
        if kind is ObjectKind.PRIMITIVE_RESULT_V2:
            detail = "a PrimitiveResult"
            fix = "index a pub first, then read the register: result[0].data.<register>"
        elif kind is ObjectKind.DATA_BIN:
            detail = "a DataBin"
            fix = "read the classical register field: <data>.<register>.get_counts()"
        else:
            detail = "a PubResult"
            fix = "read the data bin and its register: <pub>.data.<register>.get_counts()"

        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=(f"get_counts() on {detail}; counts live on the BitArray in {SHAPE}"),
                location=ctx.source.location(event.attribute_node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint=fix,
                context={"receiverKind": kind.value},
            )
        )
