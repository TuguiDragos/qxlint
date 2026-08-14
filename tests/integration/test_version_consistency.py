"""One version, five places.

The release workflow compares the three manifests against the tag, but it runs
after a tag exists. These run on every commit, and they also cover
``__version__``, which the workflow never looks at even though it is what
``--version``, the flake8 plugin and the SARIF output report.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from qxlint import __version__

ROOT = Path(__file__).resolve().parents[2]

MANIFESTS = ["npm/package.json", "vscode/package.json", "vscode/package-lock.json"]


def declared() -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version: str = config["project"]["version"]
    return version


def test_the_package_reports_the_version_pyproject_declares() -> None:
    assert __version__ == declared()


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_every_manifest_agrees(manifest: str) -> None:
    package = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
    assert package["version"] == declared()


def test_the_lockfile_root_package_agrees() -> None:
    # npm keeps a second copy under packages[""], and `npm ci` fails if it
    # disagrees with the manifest.
    lock = json.loads((ROOT / "vscode/package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"][""]["version"] == declared()


def test_the_version_file_agrees() -> None:
    # The composite action reads this to pin the analyser it installs, so a
    # stale copy would make `uses: ...@vX` install something else.
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == declared()


def test_the_action_installs_the_version_file() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "$ACTION_PATH/VERSION" in action


def test_the_citation_file_agrees() -> None:
    # Not YAML-parsed: pyyaml is not a dependency, and the field is one line.
    lines = (ROOT / "CITATION.cff").read_text(encoding="utf-8").splitlines()
    version = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("version:"))
    assert version == declared()
