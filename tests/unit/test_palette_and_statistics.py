"""The colour palette, its degradation, and the statistics view."""

from __future__ import annotations

import io
import json

import pytest

from qxlint.diagnostics import Finding, Severity, SourceLocation, Tier
from qxlint.output.palette import (
    ACCENT,
    BACKGROUND,
    BAR_EMPTY,
    BAR_EMPTY_ASCII,
    BAR_FILLED,
    BAR_FILLED_ASCII,
    MUTED,
    OUTLINE,
    RESET,
    SURFACE,
    TEXT,
    TEXT_DIM,
    Colour,
    Depth,
    bar_glyphs,
    detect_depth,
    foreground,
    nearest_256,
    paint,
)
from qxlint.output.statistics import (
    render_statistics,
    render_statistics_json,
    summarise,
)


class FakeStream(io.StringIO):
    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NO_COLOR", "FORCE_COLOR", "COLORTERM", "TERM"):
        monkeypatch.delenv(name, raising=False)


# Capability detection ---------------------------------------------------


def test_a_pipe_never_gets_colour() -> None:
    assert detect_depth(FakeStream(tty=False)) is Depth.NONE


def test_no_color_beats_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    assert detect_depth(FakeStream(tty=True)) is Depth.NONE


@pytest.mark.parametrize("value", ["1", "0", "false", "no", "anything"])
def test_any_non_empty_no_color_disables_colour(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    # "regardless of its value", so NO_COLOR=0 still disables.
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setenv("NO_COLOR", value)
    assert detect_depth(FakeStream(tty=True)) is Depth.NONE


def test_an_empty_no_color_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # https://no-color.org: "when present and not an empty string".
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setenv("NO_COLOR", "")
    assert detect_depth(FakeStream(tty=True)) is Depth.TRUECOLOR


def test_the_no_color_flag_wins_over_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert detect_depth(FakeStream(tty=True), no_color=True) is Depth.NONE


def test_force_color_overrides_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert detect_depth(FakeStream(tty=False)) is Depth.TRUECOLOR


def test_a_dumb_terminal_gets_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    assert detect_depth(FakeStream(tty=True)) is Depth.NONE


@pytest.mark.parametrize("value", ["truecolor", "24bit", "TrueColor"])
def test_colorterm_means_24_bit(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("COLORTERM", value)
    assert detect_depth(FakeStream(tty=True)) is Depth.TRUECOLOR


def test_a_256_colour_term_gets_256(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    assert detect_depth(FakeStream(tty=True)) is Depth.ANSI256


def test_a_plain_terminal_falls_back_to_16(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm")
    assert detect_depth(FakeStream(tty=True)) is Depth.ANSI16


def test_a_stream_without_isatty_is_not_a_terminal() -> None:
    assert detect_depth(None) is Depth.NONE
    assert detect_depth(io.StringIO()) is Depth.NONE


# Rendering a colour -----------------------------------------------------


def test_no_depth_emits_no_escape() -> None:
    assert foreground(ACCENT, Depth.NONE) == ""
    assert paint("x", ACCENT, Depth.NONE) == "x"


def test_truecolor_uses_the_exact_hex() -> None:
    assert foreground(ACCENT, Depth.TRUECOLOR) == "\033[38;2;145;132;217m"


def test_16_colour_uses_the_declared_fallback() -> None:
    assert foreground(ACCENT, Depth.ANSI16) == f"\033[{ACCENT.ansi16}m"


def test_painting_always_resets() -> None:
    painted = paint("x", TEXT, Depth.TRUECOLOR)
    assert painted.endswith(RESET)
    assert painted.count(RESET) == 1


def test_empty_text_produces_nothing_at_all() -> None:
    # A full bar has a zero length remainder; it must not emit a stray escape.
    assert paint("", MUTED, Depth.TRUECOLOR) == ""


def test_the_palette_hexes_are_the_declared_ones() -> None:
    assert ACCENT.hex == "#9184d9"
    assert TEXT.hex == "#e9e9ed"
    assert TEXT_DIM.hex == "#aaaab1"
    assert MUTED.hex == "#343856"


def test_rgb_is_parsed_from_the_hex() -> None:
    assert ACCENT.rgb == (0x91, 0x84, 0xD9)


# 256 colour approximation -----------------------------------------------


@pytest.mark.parametrize(
    ("colour", "lower", "upper"),
    [(ACCENT, 16, 231), (TEXT, 16, 255), (TEXT_DIM, 16, 255), (MUTED, 16, 255)],
)
def test_every_palette_colour_maps_into_the_256_range(
    colour: Colour, lower: int, upper: int
) -> None:
    assert lower <= nearest_256(colour.rgb) <= upper


def test_pure_black_and_white_land_on_sensible_indices() -> None:
    assert nearest_256((0, 0, 0)) == 16
    assert nearest_256((255, 255, 255)) == 231


def test_a_near_neutral_prefers_the_grey_ramp() -> None:
    # The six level cube is coarse; the grey ramp is much closer for a neutral.
    assert nearest_256((170, 170, 170)) >= 232


CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _table() -> dict[int, tuple[int, int, int]]:
    """Every index nearest_256 is allowed to return, with its RGB.

    The system 16 are left out on purpose: their RGB is decided by the terminal
    theme, so they are not a fixed target to be nearest to.
    """
    table: dict[int, tuple[int, int, int]] = {}
    for red in range(6):
        for green in range(6):
            for blue in range(6):
                table[16 + 36 * red + 6 * green + blue] = (
                    CUBE_LEVELS[red],
                    CUBE_LEVELS[green],
                    CUBE_LEVELS[blue],
                )
    for step in range(24):
        level = 8 + 10 * step
        table[232 + step] = (level, level, level)
    return table


def _squared(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def test_nearest_256_really_is_nearest() -> None:
    """It used to lose to brute force on 0.175% of the RGB space.

    The mean of the channels was truncated with ``//`` and then rounded with
    ``round``, which rounds a half to even, so the grey step could come out one
    below the closest one.
    """
    table = _table()
    grid = range(0, 256, 16)
    probes = [(r, g, b) for r in grid for g in grid for b in grid]
    probes += [colour.rgb for colour in (ACCENT, TEXT, TEXT_DIM, MUTED)]
    probes.append((61, 63, 96))  # OUTLINE, the case that exposed it
    for rgb in probes:
        chosen = _squared(table[nearest_256(rgb)], rgb)
        best = min(_squared(value, rgb) for value in table.values())
        assert chosen == best, rgb


# 16 colour fallback -----------------------------------------------------


FOREGROUND_CODES = frozenset(range(30, 38)) | frozenset(range(90, 98))


@pytest.mark.parametrize(
    "colour", [BACKGROUND, SURFACE, ACCENT, TEXT, TEXT_DIM, OUTLINE, MUTED], ids=lambda c: c.name
)
def test_every_ansi16_fallback_is_a_foreground_code(colour: Colour) -> None:
    # 40 and 100 are background codes. Painting text with one repaints the
    # terminal background instead of the text, which is what two entries did.
    assert colour.ansi16 in FOREGROUND_CODES
    assert foreground(colour, Depth.ANSI16) == f"\033[{colour.ansi16}m"


# Bar glyphs -------------------------------------------------------------


def test_a_utf8_stream_gets_block_characters() -> None:
    assert bar_glyphs(FakeStream(tty=True, encoding="utf-8")) == (BAR_FILLED, BAR_EMPTY)


def test_an_ascii_stream_degrades_to_ascii() -> None:
    assert bar_glyphs(FakeStream(tty=True, encoding="ascii")) == (
        BAR_FILLED_ASCII,
        BAR_EMPTY_ASCII,
    )


def test_an_unknown_encoding_degrades_rather_than_raising() -> None:
    assert bar_glyphs(FakeStream(tty=True, encoding="not-a-codec"))[0] == BAR_FILLED_ASCII


# Statistics -------------------------------------------------------------


def finding(rule: str, path: str = "a.py", line: int = 1) -> Finding:
    return Finding(
        rule=rule,
        message="m",
        location=SourceLocation(path, line, 1),
        severity=Severity.ERROR,
        tier=Tier.DEFAULT,
    )


def test_summary_of_nothing_is_empty() -> None:
    assert summarise([]) == []


def test_counts_are_grouped_by_rule() -> None:
    counts = summarise([finding("QXL101"), finding("QXL101"), finding("QXL103")])
    assert [(c.code, c.count) for c in counts] == [("QXL101", 2), ("QXL103", 1)]


def test_ties_break_on_the_code_so_the_order_is_stable() -> None:
    counts = summarise([finding("QXL201"), finding("QXL101")])
    assert [c.code for c in counts] == ["QXL101", "QXL201"]


def test_the_count_orders_before_the_code() -> None:
    # Both previous cases were also in code order, so neither could tell the
    # documented order from a plain sort by code.
    counts = summarise([finding("QXL101"), finding("QXL201"), finding("QXL201")])
    assert [(c.code, c.count) for c in counts] == [("QXL201", 2), ("QXL101", 1)]


def test_the_file_count_is_distinct_files() -> None:
    counts = summarise(
        [finding("QXL101", "a.py"), finding("QXL101", "a.py", 9), finding("QXL101", "b.py")]
    )
    assert counts[0].count == 3
    assert counts[0].files == 2


def test_the_rule_name_comes_from_the_registry() -> None:
    assert summarise([finding("QXL101")])[0].name == "get-counts-on-wrong-receiver"


def test_an_unknown_rule_code_does_not_crash_the_summary() -> None:
    assert summarise([finding("QXL999")])[0].name == "QXL999"


def test_an_empty_run_says_so() -> None:
    assert render_statistics([]) == "No findings."


def test_without_colour_there_are_no_escapes() -> None:
    rendered = render_statistics([finding("QXL101")], depth=Depth.NONE)
    assert "\033" not in rendered
    assert "QXL101" in rendered


def test_with_colour_the_bar_is_the_accent() -> None:
    rendered = render_statistics(
        [finding("QXL101")], depth=Depth.TRUECOLOR, stream=FakeStream(tty=True)
    )
    assert foreground(ACCENT, Depth.TRUECOLOR) in rendered
    assert BAR_FILLED in rendered


def test_the_longest_bar_belongs_to_the_largest_count() -> None:
    findings = [finding("QXL101") for _ in range(10)] + [finding("QXL103")]
    lines = render_statistics(findings, stream=FakeStream(tty=True)).splitlines()
    assert lines[0].count(BAR_FILLED) > lines[1].count(BAR_FILLED)


def test_even_the_smallest_count_gets_a_visible_bar() -> None:
    findings = [finding("QXL101") for _ in range(100)] + [finding("QXL103")]
    lines = render_statistics(findings, stream=FakeStream(tty=True)).splitlines()
    assert lines[1].count(BAR_FILLED) >= 1


def test_the_footer_counts_findings_and_files() -> None:
    rendered = render_statistics([finding("QXL101", "a.py"), finding("QXL103", "b.py")])
    assert "2 findings across 2 files" in rendered


def test_the_footer_is_singular_for_one() -> None:
    assert "1 finding across 1 file" in render_statistics([finding("QXL101")])


def test_the_scanned_total_is_reported_when_known() -> None:
    rendered = render_statistics([finding("QXL101")], total_files=42)
    assert "of 42 scanned" in rendered


def test_the_json_summary_is_valid_and_ordered() -> None:
    payload = json.loads(
        render_statistics_json(
            [finding("QXL101"), finding("QXL101"), finding("QXL103")], total_files=7
        )
    )
    assert payload["totalFindings"] == 3
    assert payload["filesScanned"] == 7
    assert [rule["rule"] for rule in payload["rules"]] == ["QXL101", "QXL103"]
    assert payload["rules"][0]["count"] == 2
    assert payload["rules"][0]["severity"] == "error"


def test_the_json_summary_of_nothing_is_still_valid() -> None:
    payload = json.loads(render_statistics_json([]))
    assert payload["totalFindings"] == 0
    assert payload["rules"] == []
