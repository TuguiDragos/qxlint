"""QXL202: a Runtime primitive constructed the V1 way."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import CallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.model import canonical

# Verified against qiskit-ibm-runtime 0.49.0: both raise TypeError.
RUNTIME_PRIMITIVES = frozenset({"qiskit_ibm_runtime.SamplerV2", "qiskit_ibm_runtime.EstimatorV2"})
REMOVED_ARGUMENTS = ("backend", "session")


@register
class RuntimePrimitiveTakesMode(Rule):
    meta = RuleMeta(
        code="QXL202",
        name="runtime-primitive-takes-mode",
        summary="Runtime SamplerV2 or EstimatorV2 given backend= or session= instead of mode=",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "The V1 Runtime primitives took `backend=` and `session=`. The V2 "
            "primitives replaced both with a single `mode=`, which accepts a "
            "backend, a Session or a Batch. Passing the old name raises "
            "TypeError immediately: verified on qiskit-ibm-runtime 0.49.0, "
            "`SamplerV2(backend=...)` fails with `unexpected keyword argument "
            "'backend'`. This is one of the most common leftovers of a V1 to V2 "
            "migration, because the call still reads as if it should work."
        ),
        when_legitimate=(
            "Never on a V2 Runtime primitive. It is very much legitimate on "
            "`Session` and `Batch`, which really do take `backend=`, and this "
            "rule never looks at those. It also stays silent unless the "
            "constructor is proven to be a Runtime SamplerV2 or EstimatorV2, so "
            "a local class of the same name is not flagged. The bare names "
            "`Sampler` and `Estimator` were the V1 classes until "
            "qiskit-ibm-runtime 0.28, so on a target proven to predate that "
            "release they take `backend=` and `session=` correctly and are not "
            "flagged. With no target declared the current package is assumed, "
            "where both names are the V2 classes."
        ),
        bad_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2\n\n"
            "service = QiskitRuntimeService()\n"
            "backend = service.least_busy()\n"
            "sampler = SamplerV2(backend=backend)\n"
        ),
        good_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2\n\n"
            "service = QiskitRuntimeService()\n"
            "backend = service.least_busy()\n"
            "sampler = SamplerV2(mode=backend)\n"
        ),
        references=(
            "https://quantum.cloud.ibm.com/docs/api/qiskit-ibm-runtime/sampler-v2",
            "https://quantum.cloud.ibm.com/docs/migration-guides/v2-primitives",
        ),
    )

    def on_call(self, event: CallEvent, ctx: RuleContext) -> None:
        if canonical(event.qualified_name) not in RUNTIME_PRIMITIVES:
            return

        for argument in REMOVED_ARGUMENTS:
            if argument not in event.kwargs:
                continue
            node = event.keyword_nodes.get(argument, event.node)
            ctx.emit(
                Finding(
                    rule=self.meta.code,
                    message=(
                        f"{event.qualified_name.rsplit('.', 1)[-1]} takes mode=, "
                        f"not {argument}=; the V2 primitives replaced both "
                        "backend= and session= with mode="
                    ),
                    location=ctx.source.location(node),
                    severity=self.meta.severity,
                    tier=self.meta.tier,
                    fix_hint=f"rename {argument}= to mode=",
                    context={"argument": argument},
                )
            )
            return
