"""Scan the pinned external corpus and report per-rule counts.

The corpus is defined by ``corpus/manifest.json``, which pins every repository
to a commit SHA and was written before qxlint was run on any of them. This
script only downloads and scans; it never selects, so it cannot be used to add a
repository after seeing what a rule does to it.

Requires the GitHub CLI for downloading tarballs.

    python scripts/scan_corpus.py
    python scripts/scan_corpus.py --target-runtime 0.48
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "corpus" / "manifest.json"
DEFAULT_WORKDIR = ROOT / ".corpus-cache"
TIMEOUT_SECONDS = 900


def download(repo: str, sha: str, dest: Path) -> str | None:
    """Fetch a repository at a pinned SHA, keeping only Python and notebooks."""
    if dest.exists():
        return None
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/tarball/{sha}"], capture_output=True, timeout=600, check=False
    )
    if result.returncode != 0:
        return f"download failed: {result.stderr.decode()[:200]}"
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.isfile() and member.name.endswith((".py", ".ipynb"))
            ]
            dest.mkdir(parents=True, exist_ok=True)
            for member in members:
                member.name = "/".join(member.name.split("/")[1:]) or member.name
                if member.name.startswith("/") or ".." in member.name:
                    continue
                archive.extract(member, dest, filter="data")
    except (tarfile.TarError, OSError) as exc:
        return f"extract failed: {type(exc).__name__}: {exc}"
    return None


def scan(target: Path, extra: list[str]) -> tuple[int, list[dict[str, object]], float, str]:
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "qxlint", str(target), "--format", "json", "--no-color", *extra],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, [], float(TIMEOUT_SECONDS), "timed out"

    elapsed = round(time.time() - start, 2)
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else {"findings": []}
    except json.JSONDecodeError as exc:
        return result.returncode, [], elapsed, f"invalid JSON output: {exc}"
    return result.returncode, payload["findings"], elapsed, result.stderr.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--target-runtime", default=None)
    parser.add_argument("--target-qiskit", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    extra: list[str] = []
    if args.target_runtime:
        extra += ["--target-runtime", args.target_runtime]
    if args.target_qiskit:
        extra += ["--target-qiskit", args.target_qiskit]

    totals: collections.Counter[str] = collections.Counter()
    records: list[dict[str, object]] = []
    failures = 0

    for entry in manifest["repositories"]:
        repo, sha = entry["repo"], entry["sha"]
        dest = args.workdir / repo.replace("/", "__")
        error = download(repo, sha, dest)
        if error:
            print(f"{repo:58s} {error}")
            failures += 1
            continue

        code, findings, elapsed, stderr = scan(dest, extra)
        counts = collections.Counter(str(finding["rule"]) for finding in findings)
        totals.update(counts)
        if code in (2, -1):
            failures += 1
        records.append(
            {
                **entry,
                "exit": code,
                "seconds": elapsed,
                "counts": dict(counts),
                "stderr": stderr,
                "findings": findings,
            }
        )
        summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "clean"
        print(
            f"{repo:58s} py={len(list(dest.rglob('*.py'))):5d} "
            f"nb={len(list(dest.rglob('*.ipynb'))):4d} exit={code} {elapsed:6.2f}s {summary}"
        )

    print(f"\nrepositories: {len(records)}  failures: {failures}")
    print("findings:", dict(totals) or "none")

    if args.out:
        args.out.write_text(json.dumps(records, indent=1))
        print(f"wrote {args.out}")

    # A crash or a timeout is a scan failure. Findings are not.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
