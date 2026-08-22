"""Notebook analysis end to end."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qxlint.cli import EXIT_FINDINGS, EXIT_OK, main
from qxlint.config import Config
from qxlint.diagnostics import NotebookLocation
from qxlint.engine import analyse_path
from qxlint.profile import SemanticProfile
from qxlint.registry import tiers


def notebook(*cells: str) -> str:
    document = {
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
    return json.dumps(document, indent=1)


def analyse(tmp_path: Path, text: str) -> list:
    path = tmp_path / "n.ipynb"
    path.write_text(text, encoding="utf-8")
    config = Config()
    return analyse_path(
        path,
        config=config,
        profile=SemanticProfile(),
        enabled=config.enabled_codes(tiers()),
    )


def test_facts_carry_across_cells(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\nqc.h(0)\n",
            "StatevectorSampler().run([qc])\n",
        ),
    )
    assert [f.rule for f in findings] == ["QXL103"]
    location = findings[0].location
    assert isinstance(location, NotebookLocation)
    assert location.cell_index == 3
    assert location.line == 1


def test_measurement_in_an_earlier_cell_silences_the_rule(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\nqc.measure_all()\n",
            "StatevectorSampler().run([qc])\n",
        ),
    )
    assert findings == []


def test_namespace_mutating_magic_is_a_barrier(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\n%run setup.py\n",
            "StatevectorSampler().run([qc])\n",
        ),
    )
    assert findings == []


def test_display_magic_does_not_lose_facts(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "%matplotlib inline\n"
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])\n",
        ),
    )
    assert [f.rule for f in findings] == ["QXL103"]


def test_non_python_cell_does_not_break_the_run(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "%%bash\necho hello\n",
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])\n",
        ),
    )
    assert [f.rule for f in findings] == ["QXL103"]


def test_unparsable_cell_is_reported_and_analysis_continues(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "def broken(\n",
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n"
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])\n",
        ),
    )
    assert [f.rule for f in findings] == ["QXL000", "QXL103"]


def test_noqa_works_per_cell(tmp_path: Path) -> None:
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])  # noqa: QXL103\n",
        ),
    )
    assert findings == []


def test_get_ipython_call_form_is_understood(tmp_path: Path) -> None:
    # nbconvert leaves this form behind when a notebook is exported.
    findings = analyse(
        tmp_path,
        notebook(
            "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n",
            "qc = QuantumCircuit(2)\nget_ipython().run_line_magic('run', 'setup.py')\n",
            "StatevectorSampler().run([qc])\n",
        ),
    )
    assert findings == []


def test_invalid_notebook_json_is_a_finding(tmp_path: Path) -> None:
    path = tmp_path / "broken.ipynb"
    path.write_text("{not json", encoding="utf-8")
    config = Config()
    findings = analyse_path(
        path,
        config=config,
        profile=SemanticProfile(),
        enabled=config.enabled_codes(tiers()),
    )
    assert [f.rule for f in findings] == ["QXL000"]


def test_cli_reports_notebooks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(
        notebook(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n"
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])\n"
        ),
        encoding="utf-8",
    )
    assert main([str(path)]) == EXIT_FINDINGS
    assert ":cell1:" in capsys.readouterr().out


def test_notebook_sarif_has_no_misleading_region(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(
        notebook(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n"
            "qc = QuantumCircuit(2)\nStatevectorSampler().run([qc])\n"
        ),
        encoding="utf-8",
    )
    main([str(path), "--format", "sarif"])
    log = json.loads(capsys.readouterr().out)
    location = log["runs"][0]["results"][0]["locations"][0]
    assert "region" not in location["physicalLocation"]
    assert location["logicalLocations"][0]["name"] == "cell 1"


def test_clean_notebook_exits_zero(tmp_path: Path) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(
        notebook(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n"
            "qc = QuantumCircuit(2)\nqc.measure_all()\n"
            "result = StatevectorSampler().run([qc]).result()\n"
            "counts = result[0].data.meas.get_counts()\n"
        ),
        encoding="utf-8",
    )
    assert main([str(path)]) == EXIT_OK


# The line in the file on disk ------------------------------------------
#
# A notebook finding carries a cell and a line inside it, which no SARIF
# consumer can turn into an annotation. The line in the .ipynb itself is what
# GitHub code scanning and every other annotator needs.


def _notebook(cells: list[dict], *, indent: int | None = 1) -> str:
    return json.dumps(
        {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5},
        indent=indent,
        separators=None if indent is not None else (",", ":"),
    )


CODE_CELLS = [
    {"cell_type": "markdown", "source": ["# title\n"], "metadata": {}},
    {
        "cell_type": "code",
        "source": [
            "from qiskit import QuantumCircuit\n",
            "from qiskit.primitives import StatevectorSampler\n",
        ],
        "metadata": {},
        "outputs": [],
        "execution_count": None,
    },
    {
        "cell_type": "code",
        "source": ["qc = QuantumCircuit(2)\n", "StatevectorSampler().run([qc])\n"],
        "metadata": {},
        "outputs": [],
        "execution_count": None,
    },
]


def test_a_notebook_finding_carries_its_line_in_the_file(tmp_path: Path) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(_notebook(CODE_CELLS))
    findings = analyse_path(
        path, config=Config(), profile=SemanticProfile(), enabled=frozenset({"QXL103"})
    )
    assert len(findings) == 1
    location = findings[0].location
    assert isinstance(location, NotebookLocation)
    assert location.cell_index == 2
    assert location.line == 2
    assert location.physical_line is not None
    raw = path.read_text().splitlines()
    assert "StatevectorSampler().run([qc])" in raw[location.physical_line - 1]


def test_a_minified_notebook_points_at_the_line_the_cell_starts_on(tmp_path: Path) -> None:
    # Everything is on line 1, so that is the only position there is, and it is
    # still what an annotator needs. It must never be a plausible wrong number.
    path = tmp_path / "n.ipynb"
    path.write_text(_notebook(CODE_CELLS, indent=None))
    assert len(path.read_text().splitlines()) == 1
    findings = analyse_path(
        path, config=Config(), profile=SemanticProfile(), enabled=frozenset({"QXL103"})
    )
    location = findings[0].location
    assert isinstance(location, NotebookLocation)
    assert location.physical_line == 1


def test_an_unparsable_cell_also_carries_its_line_in_the_file(tmp_path: Path) -> None:
    cells = [
        {
            "cell_type": "code",
            "source": ["x = 1\n", "def broken(\n"],
            "metadata": {},
            "outputs": [],
            "execution_count": None,
        }
    ]
    path = tmp_path / "n.ipynb"
    path.write_text(_notebook(cells))
    findings = analyse_path(
        path, config=Config(), profile=SemanticProfile(), enabled=frozenset({"QXL000"})
    )
    location = findings[0].location
    assert isinstance(location, NotebookLocation)
    assert location.physical_line is not None
    raw = path.read_text().splitlines()
    assert "def broken(" in raw[location.physical_line - 1]


def test_the_json_output_carries_the_physical_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(_notebook(CODE_CELLS))
    main([str(path), "--format", "json", "--select", "QXL103"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["location"]["physicalLine"] is not None
