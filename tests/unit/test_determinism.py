"""Determinism, which the README claims and a real bug once broke.

The analyser briefly tracked discarded calls by ``id(node)``. An id is a memory
address, and it is reused once the object is collected. A module keeps its whole
tree alive for the length of one analysis, so that was harmless there. A
**notebook** is not: one analyser is reused across cells so facts carry, and each
cell's tree is collected when the next one is parsed. A later cell's call could
then be allocated at a dead node's address and look discarded.

The symptom was the same directory reporting 0, then 1, then 0 findings across
three identical runs. These tests exercise that exact path, which a module level
test cannot reach.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from qxlint.config import Config
from qxlint.engine import analyse_path
from qxlint.profile import SemanticProfile
from qxlint.registry import tiers
from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"


def notebook(cells: list[str]) -> str:
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": source,
                    "outputs": [],
                    "execution_count": None,
                    "id": f"c{index}",
                }
                for index, source in enumerate(cells)
            ],
        }
    )


def analyse(path: Path) -> list[str]:
    config = Config()
    findings = analyse_path(
        path,
        config=config,
        profile=SemanticProfile(),
        enabled=config.enabled_codes(tiers()),
    )
    return [finding.rule for finding in findings]


# Many cells, so each cell's tree is collected while the analyser lives on, and
# every call in them has its result used. Nothing here may ever be reported.
CLEAN_CELLS = [HEADER] + [
    f"qc{i} = QuantumCircuit(2)\n"
    f"other{i} = QuantumCircuit(2)\n"
    f"combined{i} = qc{i}.compose(other{i})\n"
    f"copied{i} = qc{i}.copy()\n"
    f"print(qc{i}.decompose())\n"
    for i in range(40)
]


def test_a_clean_notebook_is_clean_every_time(tmp_path: Path) -> None:
    path = tmp_path / "clean.ipynb"
    path.write_text(notebook(CLEAN_CELLS), encoding="utf-8")
    for _ in range(30):
        gc.collect()
        assert analyse(path) == []


def test_a_notebook_with_one_no_op_reports_exactly_one_every_time(tmp_path: Path) -> None:
    cells = [*CLEAN_CELLS, "qc0.tensor(other0)\n"]
    path = tmp_path / "one.ipynb"
    path.write_text(notebook(cells), encoding="utf-8")
    for _ in range(30):
        gc.collect()
        assert analyse(path) == ["QXL104"]


def test_results_do_not_depend_on_which_notebook_was_analysed_before(
    tmp_path: Path,
) -> None:
    clean = tmp_path / "a.ipynb"
    clean.write_text(notebook(CLEAN_CELLS), encoding="utf-8")
    noisy = tmp_path / "b.ipynb"
    noisy.write_text(notebook([*CLEAN_CELLS, "qc1.compose(other1)\n"]), encoding="utf-8")

    for _ in range(20):
        assert analyse(noisy) == ["QXL104"]
        assert analyse(clean) == []
        gc.collect()


# Module level shapes, which cannot exhibit the id reuse but must stay stable.

SOURCES = {
    "discarded_compose": HEADER + "qc = QuantumCircuit(2)\no = QuantumCircuit(2)\nqc.compose(o)\n",
    "kept_compose": HEADER + "qc = QuantumCircuit(2)\no = QuantumCircuit(2)\nx = qc.compose(o)\n",
    "unmeasured": HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nStatevectorSampler().run([qc])\n",
    "raises_guarded": HEADER
    + "qc = QuantumCircuit(2)\no = QuantumCircuit(2)\n"
    + "with self.assertRaises(E):\n    qc.compose(o)\n",
    "nested_call": HEADER + "qc = QuantumCircuit(2)\nprint(qc.copy())\n",
}
EXPECTED = {
    "discarded_compose": ["QXL104"],
    "kept_compose": [],
    "unmeasured": ["QXL103"],
    "raises_guarded": [],
    "nested_call": [],
}


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_module_sources_match_their_expectation(name: str) -> None:
    assert codes(lint(SOURCES[name])) == EXPECTED[name]


def test_interleaving_module_sources_never_drifts() -> None:
    for _ in range(25):
        for name, source in SOURCES.items():
            assert codes(lint(source)) == EXPECTED[name], name
        gc.collect()


def test_a_nested_call_is_never_treated_as_discarded() -> None:
    assert codes(lint(SOURCES["nested_call"])) == []


def test_the_outer_call_is_reported_when_the_nested_one_is_not() -> None:
    source = HEADER + "qc = QuantumCircuit(2)\nqc.compose(qc.copy())\n"
    assert codes(lint(source)) == ["QXL104"]


def test_finding_order_is_stable() -> None:
    source = HEADER + (
        "a = QuantumCircuit(2)\n"
        "b = QuantumCircuit(2)\n"
        "a.compose(b)\n"
        "a.h(0)\n"
        "StatevectorSampler().run([b])\n"
        "b.tensor(a)\n"
    )
    expected = [(f.rule, f.location.line) for f in lint(source)]
    for _ in range(20):
        assert [(f.rule, f.location.line) for f in lint(source)] == expected
