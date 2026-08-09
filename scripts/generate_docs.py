"""Regenerate docs/rules from the rule modules.

Run with `python scripts/generate_docs.py`. CI checks the result is unchanged.
"""

from __future__ import annotations

from pathlib import Path

from qxlint.docs import write_pages

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    for path in write_pages(root):
        print(path.relative_to(root))
