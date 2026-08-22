"""Engine B: checks over an in-memory circuit.

Engine B never reads source and never imports user modules, so its findings have
no ``file:line``. They carry a circuit name and an instruction path instead.

Qiskit is an optional dependency. Engine A works without it; importing anything
here without Qiskit installed raises a clear error rather than an ImportError
traceback from deep inside a rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qxlint.diagnostics import Finding

__all__ = ["check_circuit", "check_target", "require_qiskit"]


class QiskitNotInstalled(RuntimeError):
    """Engine B needs Qiskit. Engine A does not."""


def require_qiskit() -> None:
    """Fail early with an actionable message instead of an ImportError."""
    try:
        import qiskit  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise QiskitNotInstalled(
            "qxlint circuit checks need Qiskit. Install it with "
            "`pip install 'qxlint[circuit]'` or `pip install qiskit`."
        ) from exc


def _require_target(target: Any) -> None:
    """Reject a target that is not one, instead of reporting nothing.

    QXL301 asks the target about each instruction, so anything without
    ``instruction_supported`` raises as soon as the circuit has one. An empty
    circuit never asks, and the call then returned no findings, which reads as
    "this circuit is compatible". It is not an answer, so it is not given.
    """
    if not callable(getattr(target, "instruction_supported", None)):
        raise TypeError(
            f"target must be a qiskit Target, got {type(target).__name__}; pass backend.target"
        )


def _analysis_depth(circuit: Any) -> list[Finding]:
    """QXL300, which every circuit entry point reports.

    The walker stops at a fixed nesting depth. A caller reading an empty list as
    "compatible" has to be told when part of the circuit was never visited.
    """
    from qxlint.circuit.qxl300_analysis_depth import IncompleteCircuitAnalysis

    return list(IncompleteCircuitAnalysis().check(circuit))


def _without(findings: list[Finding], ignore: Sequence[str] | None) -> list[Finding]:
    """Drop findings whose code starts with any ignored prefix.

    A circuit finding has no source line, so `# noqa` cannot reach it, and the
    library API never reads a `[tool.qxlint]` section. This argument is the only
    way to silence one, which is why it exists.
    """
    if not ignore:
        return findings
    prefixes = tuple(code.strip().upper() for code in ignore if code.strip())
    if not prefixes:
        return findings
    return [f for f in findings if not f.rule.startswith(prefixes)]


def check_target(
    circuit: Any, target: Any, *, ignore: Sequence[str] | None = None
) -> list[Finding]:
    """Check a circuit against a Qiskit ``Target``.

    This is generic Target compatibility, not IBM Runtime acceptance. See the
    QXL301 module docstring for exactly what is and is not checked.
    """
    require_qiskit()
    _require_target(target)
    from qxlint.circuit.qxl301_target import TargetCompatibility

    findings = [*_analysis_depth(circuit), *TargetCompatibility().check(circuit, target)]
    findings.sort(key=Finding.sort_key)
    return _without(findings, ignore)


def check_circuit(
    circuit: Any,
    *,
    target: Any | None = None,
    preview: bool = False,
    ignore: Sequence[str] | None = None,
) -> list[Finding]:
    """Run the circuit rules.

    ``target`` enables QXL301, the only default tier circuit rule, and it cannot
    run without one. ``preview=True`` additionally enables QXL302 and QXL303.
    With neither argument there is nothing to check and the result is empty; that
    is stated here rather than left as a surprise.
    """
    require_qiskit()
    findings: list[Finding] = []
    if target is not None or preview:
        findings.extend(_analysis_depth(circuit))

    if target is not None:
        _require_target(target)
        from qxlint.circuit.qxl301_target import TargetCompatibility

        findings.extend(TargetCompatibility().check(circuit, target))

    if preview:
        from qxlint.circuit.qxl302_self_inverse import RedundantSelfInversePair
        from qxlint.circuit.qxl303_unused_qubit import UnusedQubit

        findings.extend(RedundantSelfInversePair().check(circuit))
        findings.extend(UnusedQubit().check(circuit))

    findings.sort(key=Finding.sort_key)
    return _without(findings, ignore)
