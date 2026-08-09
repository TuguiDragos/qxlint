"""Human readable output. Colour only when stdout is a TTY."""

from __future__ import annotations

from qxlint.diagnostics import CircuitLocation, Finding, Severity

RESET = "\033[0m"
COLOURS = {
    Severity.ERROR: "\033[31m",
    Severity.WARNING: "\033[33m",
    Severity.INFO: "\033[36m",
}


def render_text(findings: list[Finding], *, colour: bool = False) -> str:
    lines = []
    for finding in findings:
        code = finding.rule
        if colour:
            code = f"{COLOURS.get(finding.severity, '')}{code}{RESET}"
        prefix = finding.location.render()
        suffix = ""
        if isinstance(finding.location, CircuitLocation) and finding.location.operation:
            suffix = f" [{finding.location.operation}]"
        lines.append(f"{prefix}: {code} {finding.message}{suffix}")
    return "\n".join(lines)
