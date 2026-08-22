"""Per rule counts, as a histogram.

``docs/release-gate.md`` requires results to be published as per rule counts
rather than one headline number, because a zero false positive claim drawn from
two findings means nothing. This is that view, and it is the one place in the
tool where the accent colour fills a surface, because there the filled surface
carries the number.

Sorted by count, then by code, so two runs over the same tree always agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import IO, Any

from qxlint.diagnostics import Finding, Severity, location_path
from qxlint.output.palette import (
    ACCENT,
    MUTED,
    TEXT,
    TEXT_DIM,
    Depth,
    bar_glyphs,
    paint,
)
from qxlint.registry import all_meta

BAR_WIDTH = 24


@dataclass(frozen=True, slots=True)
class RuleCount:
    code: str
    name: str
    count: int
    severity: Severity
    files: int


def summarise(findings: list[Finding]) -> list[RuleCount]:
    """Collapse findings into per rule counts, most frequent first."""
    metadata = {meta.code: meta for meta in all_meta()}
    totals: dict[str, int] = {}
    files: dict[str, set[str]] = {}

    for finding in findings:
        totals[finding.rule] = totals.get(finding.rule, 0) + 1
        path = location_path(finding.location)
        if path is not None:
            files.setdefault(finding.rule, set()).add(path)

    counts = [
        RuleCount(
            code=code,
            name=metadata[code].name if code in metadata else code,
            count=total,
            severity=metadata[code].severity if code in metadata else Severity.WARNING,
            files=len(files.get(code, ())),
        )
        for code, total in totals.items()
    ]
    # Descending by count, then by code, so the order is stable across runs.
    counts.sort(key=lambda entry: (-entry.count, entry.code))
    return counts


def render_statistics(
    findings: list[Finding],
    *,
    depth: Depth = Depth.NONE,
    stream: IO[Any] | None = None,
    total_files: int | None = None,
) -> str:
    """The histogram view."""
    counts = summarise(findings)
    if not counts:
        if total_files is None:
            summary = "No findings."
        elif total_files == 0:
            summary = "No files were analysed."
        else:
            unit = "file" if total_files == 1 else "files"
            summary = f"No findings in {total_files} {unit}."
        return paint(summary, TEXT_DIM, depth)

    filled_glyph, empty_glyph = bar_glyphs(stream)
    widest = max(entry.count for entry in counts)
    code_width = max(len(entry.code) for entry in counts)

    lines: list[str] = []
    for entry in counts:
        filled = max(1, round(BAR_WIDTH * entry.count / widest)) if widest else 0
        bar = paint(filled_glyph * filled, ACCENT, depth) + paint(
            empty_glyph * (BAR_WIDTH - filled), MUTED, depth
        )
        code = paint(entry.code.ljust(code_width), TEXT, depth)
        count = paint(str(entry.count).rjust(len(str(widest))), TEXT, depth)
        name = paint(entry.name, TEXT_DIM, depth)
        lines.append(f"  {code}  {bar}  {count}  {name}")

    total = sum(entry.count for entry in counts)
    touched = len({location_path(f.location) for f in findings} - {None})
    footer = f"{total} finding{'s' if total != 1 else ''} across {touched} file"
    footer += "s" if touched != 1 else ""
    if total_files is not None:
        footer += f" of {total_files} scanned"
    lines.append("")
    lines.append("  " + paint(footer, TEXT_DIM, depth))
    return "\n".join(lines)


def render_statistics_json(findings: list[Finding], *, total_files: int | None = None) -> str:
    """The same summary as data, for anything that needs to consume it."""
    counts = summarise(findings)
    payload: dict[str, Any] = {
        "schemaVersion": "1",
        "totalFindings": sum(entry.count for entry in counts),
        "filesWithFindings": len({location_path(f.location) for f in findings} - {None}),
        "rules": [
            {
                "rule": entry.code,
                "name": entry.name,
                "severity": entry.severity.value,
                "count": entry.count,
                "files": entry.files,
            }
            for entry in counts
        ],
    }
    if total_files is not None:
        payload["filesScanned"] = total_files
    return json.dumps(payload, indent=2)
