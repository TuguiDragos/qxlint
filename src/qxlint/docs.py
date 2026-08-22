"""Documentation generated from the rule modules.

The claim that adding a rule means one rule module plus one test module is only
true if nothing else has to be written by hand, so the docs pages are rendered
from :class:`~qxlint.rules.base.RuleMeta` and a test fails when the files on
disk drift from what the modules say.
"""

from __future__ import annotations

from pathlib import Path

from qxlint.registry import all_meta, source_reachable
from qxlint.rules.base import RuleMeta

HEADER = "<!-- Generated from the rule modules by scripts/generate_docs.py. Do not edit. -->"
RULES_DIR = Path("docs") / "rules"


def page_name(meta: RuleMeta) -> str:
    return f"{meta.code.lower()}.md"


def _suppression(meta: RuleMeta) -> list[str]:
    """How this rule is actually silenced.

    A circuit rule reaches the user through the library API, so it has no source
    line for a `# noqa` and no configuration file is read. Printing the source
    rule form on those pages documented two mechanisms that do nothing.
    """
    if meta.code not in source_reachable():
        return [
            "```python",
            "findings = qxlint.check_circuit(",
            f'    qc, target=backend.target, ignore=["{meta.code}"]',
            ")",
            "```",
            "",
            "`# noqa` and `[tool.qxlint]` do not reach a circuit rule: the finding",
            "has no source line and the library API reads no configuration file.",
            "",
        ]
    return [
        "```python",
        f"result = compute()  # noqa: {meta.code}",
        "```",
        "",
        "```toml",
        "[tool.qxlint]",
        f'ignore = ["{meta.code}"]',
        "```",
        "",
    ]


def render_rule_page(meta: RuleMeta) -> str:
    lines = [
        HEADER,
        "",
        f"# {meta.code}: {meta.summary}",
        "",
        f"- **Name**: `{meta.name}`",
        f"- **Tier**: {meta.tier.value}",
        f"- **Severity**: {meta.severity.value}",
        f"- **Version gated**: {'yes' if meta.version_gated else 'no'}",
        "",
        "## Why this is a problem",
        "",
        meta.rationale,
        "",
        "## When this is legitimate",
        "",
        meta.when_legitimate,
        "",
        "## Flagged",
        "",
        "```python",
        meta.bad_example.rstrip("\n"),
        "```",
        "",
        "## Not flagged",
        "",
        "```python",
        meta.good_example.rstrip("\n"),
        "```",
        "",
        "## Suppressing",
        "",
        *_suppression(meta),
    ]
    if meta.references:
        lines.append("## References")
        lines.append("")
        lines.extend(f"- <{url}>" for url in meta.references)
        lines.append("")
    return "\n".join(lines)


def render_index(metas: list[RuleMeta]) -> str:
    lines = [
        HEADER,
        "",
        "# Rules",
        "",
        "| Code | Tier | Severity | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for meta in metas:
        lines.append(
            f"| [{meta.code}]({page_name(meta)}) | {meta.tier.value} | "
            f"{meta.severity.value} | {meta.summary} |"
        )
    lines.extend(
        [
            "",
            "Default tier rules run unless ignored. Preview rules run only when "
            "`preview` is enabled or the exact code is selected.",
            "",
        ]
    )
    return "\n".join(lines)


def expected_pages() -> dict[str, str]:
    """Every generated file, keyed by its path relative to the repository root."""
    metas = all_meta()
    pages = {str(RULES_DIR / page_name(meta)): render_rule_page(meta) for meta in metas}
    pages[str(RULES_DIR / "index.md")] = render_index(metas)
    return pages


def write_pages(root: Path) -> list[Path]:
    written: list[Path] = []
    for relative, content in expected_pages().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
