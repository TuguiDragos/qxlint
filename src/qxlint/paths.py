"""Filesystem predicates that answer instead of raising.

``pathlib``'s own predicates do not behave the same across the versions this
project supports. ``Path.exists`` and ``Path.is_file`` let a PermissionError
through on 3.11, 3.12 and 3.13, and return False on 3.14, so a directory the
user cannot traverse ended the whole run on three interpreters out of four.

A linter must not stop because one path is closed, so everything here answers
from a single ``stat`` and treats any error as "no". ``ValueError`` is included
because a path carrying a null byte raises that rather than an OSError.
"""

from __future__ import annotations

import stat
from pathlib import Path


def _mode(path: Path) -> int | None:
    """The st_mode of the target, or None if it cannot be read at all."""
    try:
        return path.stat().st_mode
    except (OSError, ValueError):
        return None


def exists(path: Path) -> bool:
    """True when the path resolves to something. Symlinks are followed."""
    return _mode(path) is not None


def is_directory(path: Path) -> bool:
    return stat.S_ISDIR(_mode(path) or 0)


def is_regular_file(path: Path) -> bool:
    return stat.S_ISREG(_mode(path) or 0)


def exists_but_is_not_regular(path: Path) -> bool:
    """A FIFO, device, socket or directory: something that must not be opened.

    Opening a FIFO blocks until a writer appears, with no timeout, which hangs
    the run. ``stat`` itself does not block, which is why the question is asked
    this way.

    A path whose stat fails answers False, so the reader still runs and the real
    errno reaches the message.
    """
    mode = _mode(path)
    return mode is not None and not stat.S_ISREG(mode)
