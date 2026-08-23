"""Accept the findings a project already has, so CI can gate on new ones.

A project adopting qxlint mid life starts with findings it is not going to fix
today. Without a way to record them the only options are leaving the gate off
or turning rules off, and both stop the tool from reporting the next mistake.
A baseline records what was there on the day it was written; a later run
reports only what the baseline does not already account for.

An entry is keyed on path, rule and message, deliberately **not** on the line
number. Findings move whenever a line is inserted above them, and a baseline
that goes stale on every unrelated edit is one nobody keeps. The message is
part of the key because it names the receiver or symbol, so two different
mistakes of the same rule in one file stay distinguishable.

Repeats are counted rather than collapsed. A file holding two accepted
``get_counts`` calls that grows a third reports one finding, not zero, which is
the property that stops a baseline from becoming a blanket per-file mute.

Paths are stored in forward slash form so a baseline written on one platform
keeps matching on another.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from qxlint.diagnostics import Finding, as_uri_path, location_path

FORMAT_VERSION = 1

Fingerprint = tuple[str, str, str]


class BaselineError(Exception):
    """The baseline file cannot be read, or is not a baseline."""


def fingerprint(finding: Finding) -> Fingerprint:
    """Identity of a finding across edits that move it around a file."""
    path = location_path(finding.location)
    if path is None:  # an Engine B finding, addressed by circuit rather than file
        path = finding.location.render()
    return (as_uri_path(path), finding.rule, finding.message)


@dataclass(frozen=True, slots=True)
class Baseline:
    """Accepted findings, counted per fingerprint."""

    counts: Counter[Fingerprint]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def filter(self, findings: list[Finding]) -> tuple[list[Finding], int]:
        """Drop what the baseline accounts for.

        Returns the findings still to report and the number of baseline entries
        that matched nothing, which is what tells a project its baseline has
        entries worth pruning.
        """
        budget = Counter(self.counts)
        remaining: list[Finding] = []
        for finding in findings:
            key = fingerprint(finding)
            if budget[key] > 0:
                budget[key] -= 1
                continue
            remaining.append(finding)
        return remaining, sum(count for count in budget.values() if count > 0)


def build(findings: list[Finding]) -> Baseline:
    return Baseline(Counter(fingerprint(finding) for finding in findings))


def serialise(baseline: Baseline, *, tool_version: str) -> str:
    """Render a baseline as deterministic JSON.

    Entries are sorted so that regenerating a baseline over unchanged code
    produces a byte identical file, which keeps it reviewable in a diff.
    """
    entries = [
        {"path": path, "rule": rule, "message": message, "count": count}
        for (path, rule, message), count in sorted(baseline.counts.items())
    ]
    document = {
        "version": FORMAT_VERSION,
        "tool": f"qxlint {tool_version}",
        "entries": entries,
    }
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def load(path: Path) -> Baseline:
    """Read a baseline, rejecting anything that is not one.

    A malformed baseline is an error rather than an empty baseline on purpose:
    silently treating it as empty would report every accepted finding again and
    read as a regression in the code rather than a problem with the file.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BaselineError(f"cannot read baseline {path}: {exc}") from exc

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline {path} is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise BaselineError(f"baseline {path}: expected an object at the top level")

    version = document.get("version")
    if version != FORMAT_VERSION:
        raise BaselineError(
            f"baseline {path}: unsupported format version {version!r}, expected {FORMAT_VERSION}"
        )

    entries = document.get("entries")
    if not isinstance(entries, list):
        raise BaselineError(f"baseline {path}: 'entries' must be a list")

    counts: Counter[Fingerprint] = Counter()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BaselineError(f"baseline {path}: entry {index} is not an object")
        try:
            key = (entry["path"], entry["rule"], entry["message"])
            count = entry["count"]
        except KeyError as exc:
            raise BaselineError(
                f"baseline {path}: entry {index} is missing {exc.args[0]!r}"
            ) from exc
        if not all(isinstance(part, str) for part in key):
            raise BaselineError(
                f"baseline {path}: entry {index} has a non string path, rule or message"
            )
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise BaselineError(
                f"baseline {path}: entry {index} has a count that is not a positive integer"
            )
        counts[key] += count

    return Baseline(counts)
