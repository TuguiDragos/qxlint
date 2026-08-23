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
from tests.conftest import codes, lint, requires_repository

ROOT = Path(__file__).resolve().parents[2]

pytestmark = requires_repository
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


README = ROOT / "README.md"
NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def readme_rows() -> dict[str, str]:
    """Rule code to the tier cell of its README row."""
    rows = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| [QXL"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        code = cells[0][1 : cells[0].index("]")]
        rows[code] = cells[1]
    return rows


def test_the_readme_table_lists_exactly_the_registered_rules() -> None:
    assert sorted(readme_rows()) == sorted(meta.code for meta in METAS)


@pytest.mark.parametrize("meta", METAS, ids=lambda meta: meta.code)
def test_the_readme_row_matches_the_registered_tier(meta: RuleMeta) -> None:
    assert readme_rows()[meta.code].startswith(meta.tier.value)


def test_the_readme_marks_exactly_the_circuit_rules_as_library() -> None:
    from qxlint.registry import source_reachable

    reachable = source_reachable()
    marked = {code for code, tier in readme_rows().items() if "library" in tier}
    assert marked == {meta.code for meta in METAS if meta.code not in reachable}


def test_the_readme_counts_the_library_rules_correctly() -> None:
    # A rule added or moved between the engines leaves this sentence wrong, and
    # a wrong count in the first thing anybody reads is worse than none.
    from qxlint.registry import source_reachable

    total = len([meta for meta in METAS if meta.code not in source_reachable()])
    assert f"The {NUMBER_WORDS[total]} marked *library*" in README.read_text(encoding="utf-8")
