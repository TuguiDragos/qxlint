"""QXL203: service= passed to a Session or Batch that no longer takes it."""

from __future__ import annotations

import ast

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.profile import Applicability
from qxlint.registry import register
from qxlint.rules.base import CallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.model import canonical

# Read from the published wheels: 0.33.2 still declares
# `Session.__init__(self, service, backend, max_time)`, 0.34.0 declares
# `(self, backend, max_time)`. Batch subclasses Session and changed with it.
REMOVED_IN = "0.34"

CONTEXTS = frozenset({"qiskit_ibm_runtime.Session", "qiskit_ibm_runtime.Batch"})


@register
class SessionServiceArgument(Rule):
    meta = RuleMeta(
        code="QXL203",
        name="session-service-argument",
        summary="service= passed to Session or Batch, which dropped the argument",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "Session and Batch took a `service` argument until "
            "qiskit-ibm-runtime 0.33.2 and dropped it in 0.34.0, read from the "
            "published wheels. Passing it now raises TypeError before anything "
            "reaches the service, so the whole script fails at that line. Every "
            "tutorial written before that release opens with this call."
        ),
        when_legitimate=(
            "On a target proven to predate 0.34.0 the argument is still "
            "accepted, and the rule stays silent there. It also only fires on a "
            "`service` keyword, so `Session(backend=...)` and "
            "`Session(mode=...)` are never flagged, and only on the two classes "
            "that changed, resolved through the import rather than by name, so a "
            "local class called Session is not touched."
        ),
        bad_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService, Session\n\n"
            "service = QiskitRuntimeService()\n"
            'session = Session(service=service, backend="ibm_brisbane")\n'
        ),
        good_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService, Session\n\n"
            "service = QiskitRuntimeService()\n"
            'backend = service.backend("ibm_brisbane")\n'
            "session = Session(backend=backend)\n"
        ),
        references=("https://quantum.cloud.ibm.com/docs/api/qiskit-ibm-runtime/session",),
    )

    def on_call(self, event: CallEvent, ctx: RuleContext) -> None:
        if canonical(event.qualified_name) not in CONTEXTS:
            return
        if "service" not in event.kwargs:
            return
        # Silent only when every version the target allows still takes it. An
        # undeclared target reads as current, which is the reading that helps a
        # migration, and matches QXL202 rather than QXL201.
        if ctx.profile.runtime_at_least(REMOVED_IN) is Applicability.NEVER:
            return
        name = canonical(event.qualified_name).rsplit(".", 1)[-1]
        node: ast.expr = event.keyword_nodes.get("service", event.node)
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=(
                    f"{name} takes no service argument; it was removed in "
                    f"qiskit-ibm-runtime {REMOVED_IN} and passing it raises TypeError"
                ),
                location=ctx.source.location(node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint="drop service=, and pass a backend object as backend=",
                context={
                    "targetRuntime": ctx.profile.qiskit_ibm_runtime.describe(),
                    "removedIn": REMOVED_IN,
                },
            )
        )
