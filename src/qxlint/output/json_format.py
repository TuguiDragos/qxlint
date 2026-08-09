"""JSON output.

Coordinates are 1-based and end columns are exclusive, the same contract as the
text and SARIF formats. ``locationKind`` says which shape the location object
takes, so a consumer never has to guess.
"""

from __future__ import annotations

import json
from typing import Any

from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    NotebookLocation,
    SourceLocation,
)

SCHEMA_VERSION = "1"


def render_json(findings: list[Finding], *, colour: bool = False) -> str:
    del colour
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "coordinates": {"lineBase": 1, "columnBase": 1, "endColumnExclusive": True},
        "findings": [_finding_to_dict(finding) for finding in findings],
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rule": finding.rule,
        "message": finding.message,
        "severity": finding.severity.value,
        "tier": finding.tier.value,
        "engine": finding.engine,
        "location": _location_to_dict(finding.location),
    }
    if finding.fix_hint:
        out["fixHint"] = finding.fix_hint
    if finding.context:
        out["context"] = finding.context
    return out


def _location_to_dict(location: object) -> dict[str, Any]:
    if isinstance(location, SourceLocation):
        return {
            "kind": "source",
            "path": location.path,
            "line": location.line,
            "column": location.column,
            "endLine": location.end_line,
            "endColumn": location.end_column,
        }
    if isinstance(location, NotebookLocation):
        return {
            "kind": "notebook",
            "path": location.path,
            "cellIndex": location.cell_index,
            "cellIndexBase": 1,
            "cellKind": "code",
            "line": location.line,
            "column": location.column,
            "endLine": location.end_line,
            "endColumn": location.end_column,
            "physicalLine": location.physical_line,
        }
    if isinstance(location, CircuitLocation):
        return {
            "kind": "circuit",
            "circuit": location.circuit_name,
            "instructionPath": [
                {"index": step.index, "block": step.block} for step in location.path
            ],
            "operation": location.operation,
            "qubits": list(location.qubits),
            "clbits": list(location.clbits),
        }
    raise TypeError(f"unsupported location {location!r}")
