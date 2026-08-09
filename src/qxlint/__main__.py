"""Entry point for `python -m qxlint`."""

from __future__ import annotations

from qxlint.cli import main

if __name__ == "__main__":  # pragma: no cover
    # Exercised by a subprocess test, which coverage cannot attribute here.
    raise SystemExit(main())
