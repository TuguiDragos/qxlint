"""SARIF 2.1.0 output.

SARIF ``startLine`` and ``startColumn`` are 1-based and ``endColumn`` is
exclusive, which is exactly the internal contract, so no conversion happens here.

Only ``.py`` findings get a physical region. A notebook finding knows its cell
and its line inside that cell, but not the line of the notebook JSON artifact,
so it is emitted with the artifact plus a logical location and no region. Engine
B findings have no file at all and carry logical locations only. Inline
annotations on a pull request are therefore guaranteed for ``.py`` findings and
not for the other two.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from qxlint import __version__
from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    NotebookLocation,
    Severity,
    SourceLocation,
    as_uri_path,
)
from qxlint.registry import all_meta

SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
INFORMATION_URI = "https://github.com/TuguiDragos/qxlint"

LEVELS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
}


def render_sarif(findings: list[Finding], *, colour: bool = False) -> str:
    del colour
    metas = all_meta()
    index_of = {meta.code: position for position, meta in enumerate(metas)}
    log = {
        "$schema": SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "qxlint",
                        "version": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": [_descriptor(meta) for meta in metas],
                    }
                },
                "results": [_result(finding, index_of) for finding in findings],
                "columnKind": "unicodeCodePoints",
            }
        ],
    }
    return json.dumps(log, indent=2)


def _descriptor(meta: Any) -> dict[str, Any]:
    return {
        "id": meta.code,
        "name": meta.name,
        "shortDescription": {"text": meta.summary},
        "fullDescription": {"text": meta.rationale},
        "help": {"text": f"{meta.rationale}\n\nWhen this is legitimate: {meta.when_legitimate}"},
        "helpUri": f"{INFORMATION_URI}/blob/main/docs/rules/{meta.code.lower()}.md",
        "defaultConfiguration": {"level": LEVELS[meta.severity]},
        "properties": {"tags": ["qiskit", meta.tier.value]},
    }


def _result(finding: Finding, index_of: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": finding.rule,
        "level": LEVELS[finding.severity],
        "message": {"text": finding.message},
        "locations": [_location(finding)],
        "partialFingerprints": {"qxlintIdentity/v1": _fingerprint(finding)},
    }
    if finding.rule in index_of:
        result["ruleIndex"] = index_of[finding.rule]
    return result


def _fingerprint(finding: Finding) -> str:
    """Stable across edits that only move a finding up or down the file."""
    location = finding.location
    if isinstance(location, CircuitLocation):
        anchor = location.render()
    else:
        anchor = as_uri_path(location.path)
        if isinstance(location, NotebookLocation):
            anchor = f"{anchor}#cell{location.cell_index}"
    payload = f"{finding.rule}|{anchor}|{finding.message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _relative(path: str) -> str:
    """SARIF consumers resolve URIs against the repository root.

    An absolute path does not resolve on GitHub, so a path under the working
    directory is rewritten relative to it. Anything outside is left as it is.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        return as_uri_path(path)
    try:
        return as_uri_path(str(candidate.relative_to(Path.cwd())))
    except ValueError:
        return as_uri_path(path)


def _location(finding: Finding) -> dict[str, Any]:
    location = finding.location

    if isinstance(location, SourceLocation):
        # GitHub code scanning treats all four region fields as required, which is
        # stricter than the SARIF spec, so all four are always emitted.
        region: dict[str, Any] = {
            "startLine": location.line,
            "startColumn": location.column,
            "endLine": location.end_line if location.end_line is not None else location.line,
            "endColumn": (
                location.end_column if location.end_column is not None else location.column + 1
            ),
        }
        return {
            "physicalLocation": {
                "artifactLocation": {"uri": _relative(location.path)},
                "region": region,
            }
        }

    if isinstance(location, NotebookLocation):
        return {
            "physicalLocation": {"artifactLocation": {"uri": _relative(location.path)}},
            "logicalLocations": [
                {
                    "name": f"cell {location.cell_index}",
                    "kind": "member",
                    "fullyQualifiedName": (
                        f"{_relative(location.path)}#cell{location.cell_index}"
                        f":{location.line}:{location.column}"
                    ),
                }
            ],
        }

    if isinstance(location, CircuitLocation):
        return {
            "logicalLocations": [
                {
                    "name": location.circuit_name,
                    "kind": "function",
                    "fullyQualifiedName": location.render(),
                }
            ]
        }

    raise TypeError(f"unsupported location {location!r}")
