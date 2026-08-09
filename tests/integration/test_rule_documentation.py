"""The documentation gate.

Three things are enforced, because a rule whose docs are wrong is worse than a
rule with no docs:

* every registered rule has a generated page, and the checked in files match
  what the modules currently say;
* every "Flagged" example really produces that rule;
* every "Not flagged" example really produces nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qxlint.docs import expected_pages, page_name
from qxlint.registry import all_meta
from qxlint.rules.base import RuleMeta
from tests.conftest import codes, lint

ROOT = Path(__file__).resolve().parents[2]
METAS = all_meta()
CHECKABLE = [meta for meta in METAS if meta.examples_checkable and meta.code != "QXL000"]


def test_at_least_the_expected_rules_are_registered() -> None:
    assert {meta.code for meta in METAS} >= {
        "QXL000",
        "QXL101",
        "QXL102",
        "QXL103",
        "QXL201",
        "QXL301",
        "QXL302",
        "QXL303",
    }


def test_rule_codes_are_unique() -> None:
    assert len({meta.code for meta in METAS}) == len(METAS)


@pytest.mark.parametrize("meta", METAS, ids=lambda meta: meta.code)
def test_every_rule_documents_when_it_is_legitimate(meta: RuleMeta) -> None:
    # A pattern nobody can defend is a style preference, not a rule.
    assert len(meta.when_legitimate.strip()) > 40
    assert len(meta.rationale.strip()) > 40


@pytest.mark.parametrize("relative", sorted(expected_pages()), ids=lambda name: Path(name).name)
def test_generated_docs_are_up_to_date(relative: str) -> None:
    path = ROOT / relative
    assert path.exists(), f"missing {relative}; run python scripts/generate_docs.py"
    assert path.read_text(encoding="utf-8") == expected_pages()[relative], (
        f"{relative} is stale; run python scripts/generate_docs.py"
    )


@pytest.mark.parametrize("meta", METAS, ids=lambda meta: meta.code)
def test_every_rule_has_a_page(meta: RuleMeta) -> None:
    assert (ROOT / "docs" / "rules" / page_name(meta)).exists()


@pytest.mark.parametrize("meta", CHECKABLE, ids=lambda meta: meta.code)
def test_bad_example_produces_the_rule(meta: RuleMeta) -> None:
    found = codes(lint(meta.bad_example, runtime=meta.example_target_runtime))
    assert meta.code in found, f"{meta.code} bad_example produced {found}"


@pytest.mark.parametrize("meta", CHECKABLE, ids=lambda meta: meta.code)
def test_good_example_is_clean(meta: RuleMeta) -> None:
    found = codes(lint(meta.good_example, runtime=meta.example_target_runtime))
    assert found == [], f"{meta.code} good_example produced {found}"


def test_unparsable_example_produces_qxl000() -> None:
    meta = next(m for m in METAS if m.code == "QXL000")
    assert codes(lint(meta.bad_example)) == ["QXL000"]
    assert codes(lint(meta.good_example)) == []
