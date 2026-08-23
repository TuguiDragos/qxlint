"""Render what a rule is and why it exists, from the rule's own metadata.

The generated Markdown under ``docs/rules`` is built from the same
:class:`~qxlint.rules.base.RuleMeta`, but documentation is not installed with
the package. Someone who hits an unfamiliar code has the rule object in front
of them and no network, so the explanation has to come out of the process that
reported it.
"""

from __future__ import annotations

from qxlint.diagnostics import Tier
from qxlint.registry import all_meta, source_reachable
from qxlint.rules.base import RuleMeta


def _wrap(text: str, width: int = 78) -> list[str]:
    """Fold a paragraph without breaking a word.

    ``textwrap`` is avoided so a long URL or a dotted path stays on one line
    rather than being split at a character nobody can copy back together.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


def _section(title: str, body: str) -> list[str]:
    return [title, *(f"  {line}" for line in _wrap(body)), ""]


def _code_block(body: str) -> list[str]:
    return [f"  {line}" if line else "" for line in body.rstrip("\n").splitlines()]


def render_rule(meta: RuleMeta) -> str:
    """One rule, in full."""
    reachable = meta.code in source_reachable()
    engine = "source files" if reachable else "in-memory circuits, library API only"
    header = f"{meta.code}  {meta.name}"
    lines = [
        header,
        "=" * len(header),
        "",
        *_wrap(meta.summary),
        "",
        f"severity   {meta.severity.value}",
        f"tier       {meta.tier.value}"
        + ("  (off unless selected)" if meta.tier is Tier.PREVIEW else ""),
        f"applies to {engine}",
    ]
    if meta.version_gated:
        lines.append("gated      only fires on a target where the change applies")
    lines.append("")
    lines.extend(_section("Why", meta.rationale))
    lines.extend(_section("When it is legitimate", meta.when_legitimate))
    lines.append("Reported")
    lines.extend(_code_block(meta.bad_example))
    lines.append("")
    lines.append("Not reported")
    lines.extend(_code_block(meta.good_example))
    if meta.references:
        lines.extend(["", "References"])
        lines.extend(f"  {reference}" for reference in meta.references)
    return "\n".join(lines)


def render_listing() -> str:
    """Every rule, one per line, widest column first so it stays aligned."""
    entries = all_meta()
    reachable = source_reachable()
    width = max(len(meta.name) for meta in entries)
    lines = ["code    name" + " " * (width - 4) + "  severity  tier     applies to"]
    for meta in entries:
        applies = "files" if meta.code in reachable else "circuits"
        lines.append(
            f"{meta.code}  {meta.name.ljust(width)}  "
            f"{meta.severity.value.ljust(8)}  {meta.tier.value.ljust(7)}  {applies}"
        )
    lines.append("")
    lines.append(f"{len(entries)} rules. Explain one with: qxlint --explain {entries[0].code}")
    return "\n".join(lines)
