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

from qxlint.diagnostics import CircuitLocation, Finding, Severity, Tier

__all__ = [
    "NotSamplerReady",
    "QiskitNotInstalled",
    "assert_sampler_ready",
    "check_circuit",
    "check_target",
    "require_qiskit",
]


# The runtime counterpart of QXL103, reported on the object rather than inferred.
UNMEASURED = "QXL103"


class QiskitNotInstalled(RuntimeError):
    """Engine B needs Qiskit. Engine A does not."""


class NotSamplerReady(ValueError):
    """A pub is not ready for a SamplerV2. Carries the findings that say why."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        detail = "; ".join(f.message for f in findings)
        super().__init__(f"these circuits are not ready to run: {detail}")


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


def _circuit_of(pub: Any) -> Any:
    """The circuit inside a pub, which is either the circuit or the first element."""
    if isinstance(pub, tuple):
        return pub[0] if pub else None
    return pub


def _is_measured(circuit: Any) -> bool:
    """Does the circuit contain a measurement anywhere, control flow included?"""
    from qxlint.circuit.walker import walk

    return any(visited.name == "measure" for visited in walk(circuit))


def assert_sampler_ready(
    pubs: Any, *, target: Any | None = None, ignore: Sequence[str] | None = None
) -> None:
    """Raise unless every pub is ready to hand to a SamplerV2.

    This is the runtime answer to what Engine A cannot prove. It reads real
    circuits, so it decides exactly, for every call, where the source analyser
    can only look at 32 percent of them. Call it just before `sampler.run(pubs)`.

    Checks that each circuit contains a measurement, since a SamplerV2 handed an
    unmeasured circuit returns an empty data bin rather than failing, and, when a
    `target` is given, that each circuit is one the target accepts.

    Raises NotSamplerReady, whose `findings` carries the same Finding objects the
    rest of the tool produces. Returns None when there is nothing to say.
    """
    require_qiskit()
    from qxlint.circuit.walker import circuit_name

    items = list(pubs) if isinstance(pubs, (list, tuple)) else [pubs]
    found: list[Finding] = []
    for position, pub in enumerate(items):
        circuit = _circuit_of(pub)
        if circuit is None:
            continue
        if not _is_measured(circuit):
            found.append(
                Finding(
                    rule=UNMEASURED,
                    message=(
                        f"pub {position} has no measurement instructions, so a SamplerV2 "
                        "returns an empty data bin for it"
                    ),
                    location=CircuitLocation(circuit_name(circuit), ()),
                    severity=Severity.ERROR,
                    tier=Tier.DEFAULT,
                    fix_hint="add measure_all(), or measure into a classical register",
                )
            )
        if target is not None:
            found.extend(check_target(circuit, target))
    found = _without(found, ignore)
    if found:
        raise NotSamplerReady(found)
