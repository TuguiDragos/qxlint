"""QXL201: the removed `ibm_quantum` channel, gated on the target Runtime version."""

from __future__ import annotations

import ast

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.profile import Applicability
from qxlint.registry import register
from qxlint.rules.base import CallEvent, MethodCallEvent, Rule, RuleContext, RuleMeta
from qxlint.semantics.model import canonical
from qxlint.semantics.objects import ObjectKind
from qxlint.semantics.values import ConstStr

SERVICE = "qiskit_ibm_runtime.QiskitRuntimeService"
SAVE_ACCOUNT = "save_account"
REMOVED_IN = "0.41"
DEPRECATED_IN = "0.40"
VALUE = "ibm_quantum"


def _is_service_channel_call(qualified_name: str) -> bool:
    """The constructor, or the save_account staticmethod on the same class.

    Both validate the channel against the same list, so both reject the removed
    value. save_account is the form the IBM setup docs open with, which is why
    it is the one beginners write.
    """
    if canonical(qualified_name) == SERVICE:
        return True
    prefix, _, attribute = qualified_name.rpartition(".")
    return attribute == SAVE_ACCOUNT and canonical(prefix) == SERVICE


@register
class RemovedIbmQuantumChannel(Rule):
    meta = RuleMeta(
        code="QXL201",
        name="removed-ibm-quantum-channel",
        summary='channel="ibm_quantum" is removed in qiskit-ibm-runtime 0.41',
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        version_gated=True,
        rationale=(
            'The "ibm_quantum" channel was deprecated in qiskit-ibm-runtime 0.40.0 '
            "and removed in 0.41.0 with the sunset of IBM Quantum Platform Classic. "
            "Verified on qiskit-ibm-runtime 0.48.0: QiskitRuntimeService raises "
            "ValueError during construction, and QiskitRuntimeService.save_account "
            "raises InvalidAccountError, so both call sites are checked. Both "
            '"ibm_cloud" and "ibm_quantum_platform" point at the same API, '
            '"ibm_quantum_platform" is the default, and the argument can be '
            "omitted entirely."
        ),
        when_legitimate=(
            "On a project pinned below qiskit-ibm-runtime 0.41 the value still "
            "works, so the rule downgrades to a deprecation notice there and says "
            "nothing at all when the target version cannot be established. A "
            "project that cannot prove its target version never sees this rule."
        ),
        example_target_runtime="0.48",
        bad_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService\n\n"
            'service = QiskitRuntimeService(channel="ibm_quantum", token=TOKEN)\n'
        ),
        good_example=(
            "from qiskit_ibm_runtime import QiskitRuntimeService\n\n"
            "service = QiskitRuntimeService(token=TOKEN)\n"
        ),
        references=(
            "https://github.com/Qiskit/qiskit-ibm-runtime/blob/main/release-notes/0.41.0.rst",
            "https://quantum.cloud.ibm.com/docs/migration-guides/classic-iqp-to-cloud-iqp",
        ),
    )

    def on_call(self, event: CallEvent, ctx: RuleContext) -> None:
        if not _is_service_channel_call(event.qualified_name):
            return
        channel = event.kwargs.get("channel")
        if not isinstance(channel, ConstStr) or channel.value != VALUE:
            return
        self._report(event.keyword_nodes.get("channel", event.node), ctx)

    def on_method_call(self, event: MethodCallEvent, ctx: RuleContext) -> None:
        """``service.save_account(...)`` on an instance of the service.

        save_account is a staticmethod, so this call reaches the same
        validation. The receiver kind has to be proven, so a local class that
        happens to have the method is not flagged. The finding is anchored on
        the call rather than the keyword, because a method call event does not
        carry the keyword nodes.
        """
        if event.method != SAVE_ACCOUNT:
            return
        facts = event.receiver_facts
        if facts is None or facts.kind is not ObjectKind.RUNTIME_SERVICE:
            return
        channel = event.kwargs.get("channel")
        if not isinstance(channel, ConstStr) or channel.value != VALUE:
            return
        self._report(event.node, ctx)

    def _report(self, node: ast.expr, ctx: RuleContext) -> None:
        removed = ctx.profile.runtime_at_least(REMOVED_IN)

        if removed is Applicability.ALWAYS:
            ctx.emit(
                Finding(
                    rule=self.meta.code,
                    message=(
                        f'channel="{VALUE}" was removed in qiskit-ibm-runtime '
                        f"{REMOVED_IN}; omit the channel argument"
                    ),
                    location=ctx.source.location(node),
                    severity=Severity.ERROR,
                    tier=self.meta.tier,
                    fix_hint="drop channel=, or use channel='ibm_quantum_platform'",
                    context={
                        "targetRuntime": ctx.profile.qiskit_ibm_runtime.describe(),
                        "applicability": removed.value,
                    },
                )
            )
            return

        deprecated = ctx.profile.runtime_at_least(DEPRECATED_IN)
        if removed is Applicability.NEVER and deprecated is Applicability.ALWAYS:
            ctx.emit(
                Finding(
                    rule=self.meta.code,
                    message=(
                        f'channel="{VALUE}" is deprecated since qiskit-ibm-runtime '
                        f"{DEPRECATED_IN} and removed in {REMOVED_IN}"
                    ),
                    location=ctx.source.location(node),
                    severity=Severity.WARNING,
                    tier=self.meta.tier,
                    fix_hint="drop channel=, or use channel='ibm_quantum_platform'",
                    context={
                        "targetRuntime": ctx.profile.qiskit_ibm_runtime.describe(),
                        "applicability": deprecated.value,
                    },
                )
            )
