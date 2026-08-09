"""Edges of the output encoders, the flake8 plugin, docs writing and the entry point.

The notebook and circuit location shapes are built by hand: the source analyser
never produces a CircuitLocation, and a NotebookLocation only reaches the
encoders through a full notebook run, which is not what is under test here.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    InstructionStep,
    Location,
    NotebookLocation,
    Severity,
    SourceLocation,
)
from qxlint.docs import expected_pages, write_pages
from qxlint.flake8_plugin import QxlintFlake8Plugin, _to_byte_column
from qxlint.output.json_format import render_json
from qxlint.output.sarif import render_sarif
from qxlint.output.text import COLOURS, RESET, render_text
from qxlint.registry import all_rules, register
from qxlint.rules.base import Rule

BAD = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(2)\n"
    "qc.h(0)\n"
    "StatevectorSampler().run([qc])\n"
)
GOOD = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(2)\n"
    "qc.measure_all()\n"
    "result = StatevectorSampler().run([qc]).result()\n"
    "counts = result[0].data.meas.get_counts()\n"
)

CIRCUIT = CircuitLocation(
    circuit_name="qc",
    path=(InstructionStep(index=2, block=0), InstructionStep(index=5)),
    operation="cx",
    qubits=(0, 1),
    clbits=(),
)
NOTEBOOK = NotebookLocation(
    path="nb.ipynb",
    cell_index=3,
    line=4,
    column=5,
    end_line=4,
    end_column=9,
    physical_line=42,
    physical_column=6,
)


def finding(location: Location, *, rule: str = "QXL103", message: str = "boom") -> Finding:
    return Finding(rule=rule, message=message, location=location)


def bogus_finding() -> Finding:
    # Location is a closed union, so an outsider can only arrive by a caller bug.
    return Finding(rule="QXL103", message="boom", location=object())


# flake8 plugin ----------------------------------------------------------


def run_plugin(
    source: str, filename: str, *, lines: list[str] | None
) -> list[tuple[int, int, str, type]]:
    return list(QxlintFlake8Plugin(ast.parse(source), filename, lines).run())


def test_the_plugin_reads_the_file_from_disk_when_flake8_passes_no_lines(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text(BAD, encoding="utf-8")
    results = run_plugin(BAD, str(path), lines=None)
    assert len(results) == 1
    line, column, message, cls = results[0]
    assert (line, column) == (5, 0)
    assert message.startswith("QXL103 ")
    assert cls is QxlintFlake8Plugin


def test_a_file_that_cannot_be_read_yields_nothing_at_all(tmp_path: Path) -> None:
    assert run_plugin("x = 1\n", str(tmp_path / "gone.py"), lines=None) == []


def test_a_broken_project_config_silences_the_plugin_instead_of_raising(tmp_path: Path) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.qxlint]\nselect = "nope"\n', encoding="utf-8")
    path = tmp_path / "bad.py"
    path.write_text(BAD, encoding="utf-8")
    lines = BAD.splitlines(keepends=True)

    assert run_plugin(BAD, str(path), lines=lines) == []

    # The same file with a readable config still reports, so the silence above
    # came from the config error and not from the analysis.
    config.write_text("[tool.qxlint]\nignore = []\n", encoding="utf-8")
    assert len(run_plugin(BAD, str(path), lines=lines)) == 1


@pytest.mark.parametrize("line", [0, 2, 99])
def test_a_line_outside_the_text_keeps_its_column_unchanged(line: int) -> None:
    # No finding can point past the end of its own text, so this guard has no
    # route through run() and is exercised directly.
    assert _to_byte_column("héllo = 1\n", line, 4) == 4


def test_a_line_inside_the_text_is_converted_to_a_byte_column() -> None:
    assert _to_byte_column("héllo = 1\n", 1, 4) == 5


# JSON encoder -----------------------------------------------------------


def test_json_encodes_a_notebook_location_with_its_cell() -> None:
    payload = json.loads(render_json([finding(NOTEBOOK)]))
    entry = payload["findings"][0]
    assert entry["engine"] == "A"
    assert entry["location"] == {
        "kind": "notebook",
        "path": "nb.ipynb",
        "cellIndex": 3,
        "cellIndexBase": 1,
        "cellKind": "code",
        "line": 4,
        "column": 5,
        "endLine": 4,
        "endColumn": 9,
        "physicalLine": 42,
    }


def test_json_encodes_a_circuit_location_as_an_instruction_path() -> None:
    payload = json.loads(render_json([finding(CIRCUIT)]))
    entry = payload["findings"][0]
    assert entry["engine"] == "B"
    assert entry["location"] == {
        "kind": "circuit",
        "circuit": "qc",
        "instructionPath": [{"index": 2, "block": 0}, {"index": 5, "block": None}],
        "operation": "cx",
        "qubits": [0, 1],
        "clbits": [],
    }


def test_json_refuses_a_location_it_does_not_know() -> None:
    with pytest.raises(TypeError, match="unsupported location"):
        render_json([bogus_finding()])


# SARIF encoder ----------------------------------------------------------


def sarif_result(item: Finding) -> dict[str, Any]:
    log = json.loads(render_sarif([item]))
    result: dict[str, Any] = log["runs"][0]["results"][0]
    return result


def sarif_location(item: Finding) -> dict[str, Any]:
    location: dict[str, Any] = sarif_result(item)["locations"][0]
    return location


def fingerprint(location: Location) -> str:
    value: str = sarif_result(finding(location))["partialFingerprints"]["qxlintIdentity/v1"]
    return value


def test_a_circuit_finding_gets_a_logical_location_and_no_region() -> None:
    location = sarif_location(finding(CIRCUIT))
    assert "physicalLocation" not in location
    assert location["logicalLocations"] == [
        {"name": "qc", "kind": "function", "fullyQualifiedName": "qc[2].block[0][5]"}
    ]


def test_a_circuit_fingerprint_follows_the_instruction_path_only() -> None:
    moved = replace(CIRCUIT, path=(InstructionStep(index=3),))
    assert fingerprint(CIRCUIT) != fingerprint(moved)
    # Qubits are not part of the rendered anchor, so identity survives a rewiring.
    assert fingerprint(CIRCUIT) == fingerprint(replace(CIRCUIT, qubits=(7,)))


@pytest.mark.parametrize(
    ("path", "uri"),
    [("bad.py", "bad.py"), ("pkg/bad.py", "pkg/bad.py"), ("pkg\\bad.py", "pkg/bad.py")],
)
def test_a_relative_source_path_reaches_sarif_unchanged(path: str, uri: str) -> None:
    location = sarif_location(finding(SourceLocation(path, 3, 7)))
    assert location["physicalLocation"]["artifactLocation"] == {"uri": uri}


def test_sarif_refuses_a_location_it_does_not_know() -> None:
    with pytest.raises(TypeError, match="unsupported location"):
        render_sarif([bogus_finding()])


# The SARIF contract with code scanning ----------------------------------
#
# These three were the parts of the encoder nothing pinned down: the region
# could have been made inclusive, absolute paths could have stopped being
# rewritten, and the fingerprint could have dropped the rule, all without a
# test noticing. Each one changes what GitHub shows on a pull request.


def test_the_default_end_column_is_exclusive() -> None:
    # SARIF endColumn is exclusive, so a one character span ends at column + 1.
    region = sarif_location(finding(SourceLocation("a.py", 3, 7)))["physicalLocation"]["region"]
    assert region == {"startLine": 3, "startColumn": 7, "endLine": 3, "endColumn": 8}


def test_an_explicit_end_is_carried_through_unchanged() -> None:
    region = sarif_location(finding(SourceLocation("a.py", 3, 7, end_line=4, end_column=11)))[
        "physicalLocation"
    ]["region"]
    assert region == {"startLine": 3, "startColumn": 7, "endLine": 4, "endColumn": 11}


def test_an_absolute_path_under_the_working_directory_becomes_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A SARIF consumer resolves the uri against the repository root, so an
    # absolute path does not land on any line at all.
    monkeypatch.chdir(tmp_path)
    absolute = tmp_path / "pkg" / "bad.py"
    location = sarif_location(finding(SourceLocation(str(absolute), 1, 1)))
    assert location["physicalLocation"]["artifactLocation"] == {"uri": "pkg/bad.py"}


def test_a_path_outside_the_working_directory_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = tmp_path / "here"
    inside.mkdir()
    monkeypatch.chdir(inside)
    outside = tmp_path / "elsewhere" / "bad.py"
    location = sarif_location(finding(SourceLocation(str(outside), 1, 1)))
    assert location["physicalLocation"]["artifactLocation"] == {"uri": str(outside)}


def test_the_fingerprint_separates_two_rules_at_the_same_place() -> None:
    location = SourceLocation("a.py", 5, 5)
    first = sarif_result(finding(location, rule="QXL101", message="same"))
    second = sarif_result(finding(location, rule="QXL103", message="same"))
    assert (
        first["partialFingerprints"]["qxlintIdentity/v1"]
        != second["partialFingerprints"]["qxlintIdentity/v1"]
    )


# Text renderer ----------------------------------------------------------


@pytest.mark.parametrize("severity", list(Severity))
def test_colour_wraps_the_rule_code_and_nothing_else(severity: Severity) -> None:
    item = Finding(
        rule="QXL101", message="m", location=SourceLocation("a.py", 1, 2), severity=severity
    )
    assert render_text([item], colour=True) == f"a.py:1:2: {COLOURS[severity]}QXL101{RESET} m"


def test_a_circuit_finding_names_its_operation_after_the_message() -> None:
    assert render_text([finding(CIRCUIT)]) == "qc[2].block[0][5]: QXL103 boom [cx]"


def test_a_circuit_finding_without_an_operation_gets_no_suffix() -> None:
    item = finding(replace(CIRCUIT, operation=None))
    assert render_text([item]) == "qc[2].block[0][5]: QXL103 boom"


# Documentation writing --------------------------------------------------


def test_write_pages_creates_every_generated_file_under_the_given_root(tmp_path: Path) -> None:
    written = write_pages(tmp_path)
    expected = expected_pages()
    assert {str(path.relative_to(tmp_path)) for path in written} == set(expected)
    for path in written:
        assert path.read_text(encoding="utf-8") == expected[str(path.relative_to(tmp_path))]


def test_write_pages_replaces_a_stale_page(tmp_path: Path) -> None:
    stale = tmp_path / "docs" / "rules" / "index.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    write_pages(tmp_path)
    assert stale.read_text(encoding="utf-8") == expected_pages()[str(Path("docs/rules/index.md"))]


# Registry ---------------------------------------------------------------


def test_registering_a_second_rule_under_a_taken_code_is_rejected() -> None:
    code = "QXL103"
    original = all_rules()[code]

    class Clashing(Rule):
        meta = replace(original.meta, name="clashing-rule")

    with pytest.raises(RuntimeError, match=f"duplicate rule code {code}"):
        register(Clashing)
    assert all_rules()[code] is original


# Module entry point -----------------------------------------------------


def run_module(argument: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "qxlint", argument],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_running_the_package_as_a_module_reports_findings_and_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text(BAD, encoding="utf-8")
    result = run_module(str(path), tmp_path)
    assert result.returncode == 1
    assert "QXL103" in result.stdout


def test_running_the_package_as_a_module_exits_zero_and_prints_nothing_when_clean(
    tmp_path: Path,
) -> None:
    path = tmp_path / "good.py"
    path.write_text(GOOD, encoding="utf-8")
    result = run_module(str(path), tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_the_module_entry_point_imports_without_running_the_cli() -> None:
    # Importing must not execute main(); only `python -m qxlint` does that,
    # which is covered by the subprocess test above.
    import qxlint.__main__ as entry

    assert entry.main.__module__ == "qxlint.cli"
