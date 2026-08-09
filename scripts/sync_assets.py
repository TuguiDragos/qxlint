"""Copy the canonical icon into the places that need their own copy.

readme-assets/png is the source. The VS Code extension cannot reference a file
outside its own folder, so it needs a copy, and a copy is exactly the kind of
thing that silently goes stale. This script refreshes it and says what changed.

    python scripts/sync_assets.py
    python scripts/sync_assets.py --check    # fail if a copy is out of date
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIES = [
    # source, destination
    (
        ROOT / "readme-assets" / "png" / "qxlint-icon-256.png",
        ROOT / "vscode" / "images" / "icon.png",
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift instead of fixing it")
    args = parser.parse_args()

    stale = 0
    for source, destination in COPIES:
        if not source.exists():
            print(f"missing source: {source.relative_to(ROOT)}", file=sys.stderr)
            return 1
        if digest(source) == digest(destination):
            print(f"up to date  {destination.relative_to(ROOT)}")
            continue
        stale += 1
        if args.check:
            print(f"STALE       {destination.relative_to(ROOT)}", file=sys.stderr)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        print(f"updated     {destination.relative_to(ROOT)}  <-  {source.relative_to(ROOT)}")

    if args.check and stale:
        print("run: python scripts/sync_assets.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
