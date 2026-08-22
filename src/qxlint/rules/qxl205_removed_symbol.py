"""QXL205: an import of a symbol Qiskit removed."""

from __future__ import annotations

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.profile import Applicability
from qxlint.registry import register
from qxlint.rules.base import ImportEvent, Rule, RuleContext, RuleMeta

# Every entry read from the published wheels, not from a changelog, and the
# absence confirmed on the installed Qiskit 2.5.2. The value is the release that
# dropped it and what replaces it.
REMOVED = {
    "qiskit.execute": ("1.0", "transpile the circuit, then call a primitive"),
    "qiskit.Aer": ("1.0", "install qiskit-aer and import Aer from qiskit_aer"),
    "qiskit.IBMQ": ("1.0", "use QiskitRuntimeService from qiskit_ibm_runtime"),
    "qiskit.opflow": ("1.0", "use qiskit.quantum_info"),
    "qiskit.algorithms": ("1.0", "install qiskit-algorithms"),
    "qiskit.providers.aer": ("1.0", "install qiskit-aer and import from qiskit_aer"),
    "qiskit.utils.QuantumInstance": ("1.0", "use a primitive"),
    "qiskit.assemble": ("2.0", "pass circuits to a primitive directly"),
    "qiskit.primitives.Sampler": ("2.0", "use StatevectorSampler or BackendSamplerV2"),
    "qiskit.primitives.Estimator": ("2.0", "use StatevectorEstimator or BackendEstimatorV2"),
    "qiskit.primitives.BackendSampler": ("2.0", "use BackendSamplerV2"),
    "qiskit.primitives.BackendEstimator": ("2.0", "use BackendEstimatorV2"),
}

# A removed module takes everything under it with it.
MODULES = ("qiskit.opflow", "qiskit.algorithms", "qiskit.providers.aer")


def _entry(qualified: str) -> tuple[str, str, str] | None:
    """The removed name this import touches, with its release and replacement."""
    exact = REMOVED.get(qualified)
    if exact is not None:
        return qualified, exact[0], exact[1]
    for module in MODULES:
        if qualified.startswith(f"{module}."):
            removed_in, replacement = REMOVED[module]
            return module, removed_in, replacement
    return None


@register
class RemovedQiskitSymbol(Rule):
    meta = RuleMeta(
        code="QXL205",
        name="removed-qiskit-symbol",
        summary="an import of a name Qiskit 1.0 or 2.0 removed",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "Qiskit 1.0 removed the top level execute, Aer and IBMQ, the opflow "
            "and algorithms packages, the vendored providers.aer, and "
            "QuantumInstance. Qiskit 2.0 removed assemble and the V1 primitives "
            "Sampler, Estimator, BackendSampler and BackendEstimator. Each "
            "release was read from the published wheels and each absence "
            "confirmed on Qiskit 2.5.2. The import raises before a single line "
            "of the script runs, so nothing downstream can be reached."
        ),
        when_legitimate=(
            "On a target proven to predate the release that removed the name, "
            "the import still works and the rule stays silent. It reads the "
            "dotted path of the import rather than the bound name, so a local "
            "module of the same name is not touched, and a relative import, "
            "which names nothing outside the package, is never considered."
        ),
        bad_example="from qiskit import QuantumCircuit, execute, Aer\n",
        good_example=(
            "from qiskit import QuantumCircuit, transpile\nfrom qiskit_aer import AerSimulator\n"
        ),
        references=("https://quantum.cloud.ibm.com/docs/migration-guides/qiskit-1.0-features",),
    )

    def on_import(self, event: ImportEvent, ctx: RuleContext) -> None:
        found = _entry(event.qualified_name)
        if found is None:
            return
        name, removed_in, replacement = found
        # Silent only when every version the target allows still has it. An
        # undeclared target reads as current, matching QXL202 and QXL203.
        if ctx.profile.qiskit_at_least(removed_in) is Applicability.NEVER:
            return
        ctx.emit(
            Finding(
                rule=self.meta.code,
                message=(
                    f"{name} was removed in Qiskit {removed_in}; "
                    "this import raises before anything else runs"
                ),
                location=ctx.source.location(event.node),
                severity=self.meta.severity,
                tier=self.meta.tier,
                fix_hint=replacement,
                context={
                    "removedIn": removed_in,
                    "symbol": name,
                    "targetQiskit": ctx.profile.qiskit.describe(),
                },
            )
        )
