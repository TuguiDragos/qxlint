"""Rendering a rule from its own metadata."""

from __future__ import annotations

from qxlint.output.explain import _code_block, _wrap, render_listing, render_rule
from qxlint.registry import all_meta


def test_wrapping_keeps_every_word() -> None:
    text = " ".join(f"word{index}" for index in range(40))
    assert " ".join(_wrap(text)).split() == text.split()


def test_wrapping_respects_the_width() -> None:
    assert all(len(line) <= 20 for line in _wrap("alpha beta gamma delta epsilon", width=20))


def test_wrapping_never_splits_a_long_word() -> None:
    url = "https://example.invalid/" + "x" * 120
    assert _wrap(f"see {url} for more") == ["see", url, "for more"]


def test_wrapping_empty_text_produces_no_lines() -> None:
    assert _wrap("") == []
    assert _wrap("   \n  ") == []


def test_a_code_block_keeps_blank_lines_blank() -> None:
    assert _code_block("a = 1\n\nb = 2\n") == ["  a = 1", "", "  b = 2"]


def test_every_rule_renders_with_all_of_its_sections() -> None:
    for meta in all_meta():
        rendered = render_rule(meta)
        assert rendered.startswith(f"{meta.code}  {meta.name}")
        for heading in ("Why", "When it is legitimate", "Reported", "Not reported"):
            assert f"\n{heading}\n" in rendered
        assert meta.severity.value in rendered
        assert meta.tier.value in rendered


def test_a_rule_without_references_omits_the_section() -> None:
    with_references = [meta for meta in all_meta() if meta.references]
    without = [meta for meta in all_meta() if not meta.references]
    assert with_references, "expected at least one rule carrying references"
    assert all("\nReferences" in render_rule(meta) for meta in with_references)
    assert all("\nReferences" not in render_rule(meta) for meta in without)


def test_the_listing_holds_one_line_per_rule() -> None:
    lines = [line for line in render_listing().splitlines() if line.startswith("QXL")]
    assert len(lines) == len(all_meta())


def test_the_listing_columns_line_up() -> None:
    # No rule name contains a severity word, so finding one locates the column.
    lines = [line for line in render_listing().splitlines() if line.startswith("QXL")]
    starts = set()
    for line in lines:
        starts.update(line.index(word) for word in ("error", "warning", "note") if word in line)
    assert len(starts) == 1, f"the severity column is ragged: {sorted(starts)}"
