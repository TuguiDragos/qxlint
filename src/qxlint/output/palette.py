"""Terminal colour: the palette, capability detection and degradation.

The palette is the project's own, shared with the logo and the badges. One rule
governs it: **the accent appears as a line, an outline or a run of glyphs, never
as a filled background.** A histogram bar is the single declared exception,
because there the filled surface is the information. That is why this module is
used by the statistics view and by nothing else that prints prose.

Findings keep the conventional red, yellow and cyan. Red for an error is the one
thing people scan for in a wall of CI output, and the palette deliberately
contains no red, so applying it there would cost more than it gained.

Degradation is real, not decorative. A colour is emitted as 24-bit only when the
terminal says it can; otherwise it falls back to the 256 colour cube, then to
the 16 colour codes, then to nothing at all.
"""

from __future__ import annotations

import enum
import math
import os
from dataclasses import dataclass
from typing import IO, Any

RESET = "\033[0m"

# Box drawing degrades too: a terminal that cannot encode these gets ASCII.
BAR_FILLED = "█"
BAR_EMPTY = "░"
BAR_FILLED_ASCII = "#"
BAR_EMPTY_ASCII = "."


class Depth(enum.IntEnum):
    """How much colour the terminal can show. Ordered, so comparisons work."""

    NONE = 0
    ANSI16 = 1
    ANSI256 = 2
    TRUECOLOR = 3


@dataclass(frozen=True, slots=True)
class Colour:
    """One palette entry, with the 16 colour code to fall back to.

    ``ansi16`` is an SGR **foreground** code, so 30 to 37 or 90 to 97. A
    background code such as 40 would repaint the terminal background instead of
    the text. Where the choice is not forced, it is curated rather than nearest:
    the accent reads as bright magenta on a 16 colour terminal, which carries
    the intent better than the nearest neighbour, white.
    """

    name: str
    hex: str
    ansi16: int

    @property
    def rgb(self) -> tuple[int, int, int]:
        value = self.hex.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


# The project palette. Contrast ratios are against BACKGROUND.
BACKGROUND = Colour("background", "#161826", 30)  # panels and badges
SURFACE = Colour("surface", "#1a1e30", 30)  # raised surfaces
ACCENT = Colour("accent", "#9184d9", 95)  # 5.45:1, AA
TEXT = Colour("text", "#e9e9ed", 97)  # 14.54:1, AAA
TEXT_DIM = Colour("text-dim", "#aaaab1", 37)  # 7.62:1, AAA
OUTLINE = Colour("outline", "#3d3f60", 90)  # 1.74:1, decorative only
MUTED = Colour("muted", "#343856", 90)  # 1.55:1, decorative only


def detect_depth(stream: IO[Any] | None, *, no_color: bool = False) -> Depth:
    """Decide how much colour to emit, in the order the ecosystem expects.

    ``NO_COLOR`` wins over everything. https://no-color.org words it exactly:
    "when present and not an empty string (regardless of its value)". An empty
    value therefore counts as unset, the same way ``FORCE_COLOR`` is read.

    ``--no-color`` is next, then a non-terminal destination, which is what keeps
    escapes out of a pipe and out of a CI log file. ``FORCE_COLOR`` overrides the
    terminal check for the cases where a CI system really does render colour.
    """
    if os.environ.get("NO_COLOR"):
        return Depth.NONE
    if no_color:
        return Depth.NONE

    forced = os.environ.get("FORCE_COLOR")
    if not _is_a_terminal(stream) and not forced:
        return Depth.NONE

    term = os.environ.get("TERM", "")
    if term == "dumb":
        return Depth.NONE

    colorterm = os.environ.get("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return Depth.TRUECOLOR
    if "256color" in term:
        return Depth.ANSI256
    return Depth.ANSI16


def _is_a_terminal(stream: IO[Any] | None) -> bool:
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def foreground(colour: Colour, depth: Depth) -> str:
    """Escape sequence setting this colour as the foreground, or nothing."""
    if depth is Depth.NONE:
        return ""
    if depth is Depth.TRUECOLOR:
        red, green, blue = colour.rgb
        return f"\033[38;2;{red};{green};{blue}m"
    if depth is Depth.ANSI256:
        return f"\033[38;5;{nearest_256(colour.rgb)}m"
    return f"\033[{colour.ansi16}m"


def paint(text: str, colour: Colour, depth: Depth) -> str:
    """Wrap text in a colour, or return it untouched when colour is off.

    Empty text produces nothing at all, so a full bar does not emit a stray
    escape pair around the zero length remainder.
    """
    if not text:
        return ""
    prefix = foreground(colour, depth)
    return f"{prefix}{text}{RESET}" if prefix else text


def nearest_256(rgb: tuple[int, int, int]) -> int:
    """Closest xterm 256 index, choosing between the colour cube and the greys.

    The cube and the grey ramp are compared rather than assuming one is better,
    because a near neutral like TEXT_DIM lands far closer on the grey ramp than
    on the six level cube.
    """
    red, green, blue = rgb
    cube_index, cube_rgb = _cube_candidate(rgb)
    grey_index, grey_rgb = _grey_candidate(rgb)
    if _distance(cube_rgb, (red, green, blue)) <= _distance(grey_rgb, (red, green, blue)):
        return cube_index
    return grey_index


_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _cube_candidate(rgb: tuple[int, int, int]) -> tuple[int, tuple[int, int, int]]:
    coordinates = tuple(_closest_level(channel) for channel in rgb)
    index = 16 + 36 * coordinates[0] + 6 * coordinates[1] + coordinates[2]
    values = tuple(_CUBE_LEVELS[c] for c in coordinates)
    return index, (values[0], values[1], values[2])


def _closest_level(channel: int) -> int:
    return min(range(6), key=lambda i: abs(_CUBE_LEVELS[i] - channel))


def _grey_candidate(rgb: tuple[int, int, int]) -> tuple[int, tuple[int, int, int]]:
    """Nearest entry on the 24 step grey ramp.

    The mean is kept exact and rounded half up. Truncating it, or using
    ``round``, which rounds a half to even, picked the wrong step for 0.175% of
    the RGB space, by up to 20 in squared distance. With both corrected the
    result is the nearest cube or grey entry for every colour.
    """
    average = sum(rgb) / 3
    step = min(23, max(0, math.floor((average - 8) / 10 + 0.5)))
    level = 8 + 10 * step
    return 232 + step, (level, level, level)


def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def bar_glyphs(stream: IO[Any] | None) -> tuple[str, str]:
    """Block characters when the stream can encode them, ASCII when it cannot."""
    encoding = getattr(stream, "encoding", None) or ""
    try:
        BAR_FILLED.encode(encoding or "ascii")
    except (LookupError, UnicodeEncodeError):
        return BAR_FILLED_ASCII, BAR_EMPTY_ASCII
    return BAR_FILLED, BAR_EMPTY
