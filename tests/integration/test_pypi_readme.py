"""The packaged README must carry no relative links.

PyPI renders them against the project page, where they 404.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from tests.conftest import requires_repository

ROOT = Path(__file__).resolve().parents[2]

pytestmark = requires_repository
README = (ROOT / "README.md").read_text(encoding="utf-8")

LINK = re.compile(r"\]\(([^)]+)\)")
ABSOLUTE = re.compile(r"https?://|#|mailto:")


def substitutions() -> list[tuple[re.Pattern[str], str]]:
    """The rewrite rules as pyproject.toml actually declares them."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    hook = config["tool"]["hatch"]["metadata"]["hooks"]["fancy-pypi-readme"]
    return [(re.compile(rule["pattern"]), rule["replacement"]) for rule in hook["substitutions"]]


def rewritten() -> str:
    text = README
    for pattern, replacement in substitutions():
        text = pattern.sub(replacement, text)
    return text


def relative_targets(text: str) -> list[str]:
    return [target for target in LINK.findall(text) if not ABSOLUTE.match(target)]


def test_the_readme_is_dynamic_so_the_hook_is_what_ships() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "readme" in config["project"]["dynamic"]
    assert "readme" not in config["project"]


def test_the_source_readme_still_has_relative_links() -> None:
    # Otherwise this file would pass by testing nothing.
    assert relative_targets(README)


def test_no_relative_link_survives_the_rewrite() -> None:
    assert relative_targets(rewritten()) == []


@pytest.mark.parametrize("target", sorted(set(relative_targets(README))))
def test_every_relative_target_exists_in_the_repository(target: str) -> None:
    assert (ROOT / target).exists()


def test_directories_become_tree_urls_and_files_become_blob_urls() -> None:
    text = rewritten()
    assert "https://github.com/TuguiDragos/qxlint/tree/main/corpus/" in text
    assert "https://github.com/TuguiDragos/qxlint/blob/main/docs/rules/qxl101.md" in text


def test_absolute_links_and_anchors_are_left_alone() -> None:
    already_absolute = {target for target in LINK.findall(README) if ABSOLUTE.match(target)}
    assert already_absolute <= set(LINK.findall(rewritten()))
