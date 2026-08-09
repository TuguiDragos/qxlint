"""The false side of guards that the rest of the suite only ever takes true.

Statement coverage does not see these: the line runs, but only one way. Each
one here is a real behaviour, usually "the thing was not found" or "it was
already there", which is exactly where a silent wrong answer would hide.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qxlint.cli import EXIT_FINDINGS, EXIT_OK, main
from qxlint.config import Config, resolve_profile
from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    InstructionStep,
    Severity,
    SourceLocation,
    Tier,
)
from qxlint.engine import discover
from qxlint.flake8_plugin import _to_flake8
from qxlint.notebook import prepare_cell_source
from qxlint.output.sarif import render_sarif
from qxlint.output.statistics import render_statistics, render_statistics_json, summarise
from qxlint.profile import ProfileSource, knowledge_from_text
from qxlint.semantics.objects import ObjectFacts, ObjectKind, ObjectStore, TriState
from qxlint.semantics.values import ObjectRef, Sequence, object_refs
from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"


def circuit_finding(rule: str = "QXL301") -> Finding:
    return Finding(
        rule=rule,
        message="m",
        location=CircuitLocation("circ", (InstructionStep(0),), operation="h"),
        severity=Severity.ERROR,
        tier=Tier.DEFAULT,
    )


# ObjectStore: mutating an id that is not there ---------------------------


@pytest.mark.parametrize("method", ["update", "invalidate", "mark_escaped"])
def test_mutating_an_unknown_object_id_does_nothing(method: str) -> None:
    store = ObjectStore()
    known = store.allocate(ObjectFacts(ObjectKind.CIRCUIT, measurement=TriState.DEFINITELY_ABSENT))
    call = getattr(store, method)
    call(known + 999, measurement=TriState.DEFINITELY_PRESENT) if method == "update" else call(
        known + 999
    )
    assert store.ids() == frozenset({known})
    facts = store.get(known)
    assert facts is not None
    assert facts.measurement is TriState.DEFINITELY_ABSENT


# Reachable references are deduplicated ----------------------------------


def test_the_same_reference_reached_twice_is_listed_once() -> None:
    shared = ObjectRef(7)
    value = Sequence((shared, shared, ObjectRef(8)))
    assert [ref.id for ref in object_refs(value)] == [7, 8]


# Statistics with a finding that has no file -----------------------------


def test_a_circuit_finding_is_counted_but_owns_no_file() -> None:
    counts = summarise([circuit_finding()])
    assert counts[0].count == 1
    assert counts[0].files == 0


def test_the_summary_footer_reports_zero_files_for_circuit_findings() -> None:
    assert "1 finding across 0 files" in render_statistics([circuit_finding()])


def test_the_json_summary_reports_zero_files_for_circuit_findings() -> None:
    payload = json.loads(render_statistics_json([circuit_finding()]))
    assert payload["filesWithFindings"] == 0
    assert payload["rules"][0]["files"] == 0


# SARIF for a rule the registry does not know ----------------------------


def test_an_unregistered_rule_gets_no_rule_index() -> None:
    log = json.loads(render_sarif([circuit_finding(rule="QXL999")]))
    result = log["runs"][0]["results"][0]
    assert result["ruleId"] == "QXL999"
    assert "ruleIndex" not in result


def test_a_registered_rule_does_get_a_rule_index() -> None:
    finding = Finding(
        rule="QXL101",
        message="m",
        location=SourceLocation("a.py", 1, 1),
        severity=Severity.ERROR,
        tier=Tier.DEFAULT,
    )
    result = json.loads(render_sarif([finding]))["runs"][0]["results"][0]
    assert isinstance(result["ruleIndex"], int)


# flake8 columns for a location that is not source ------------------------


def test_a_non_source_location_keeps_its_column_unconverted() -> None:
    # Only a source location has bytes to convert against. The plugin never
    # produces the others today, but the conversion must not be applied blindly.
    line, column, message, _ = _to_flake8(circuit_finding(), "irrelevant\n")
    assert (line, column) == (1, 0)
    assert message.startswith("QXL301 ")


# Discovery: a file reached twice ----------------------------------------


def test_a_file_named_twice_is_analysed_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nStatevectorSampler().run([qc])\n"
    path = tmp_path / "bad.py"
    path.write_text(source, encoding="utf-8")
    assert main([str(path), str(path)]) == EXIT_FINDINGS
    assert capsys.readouterr().out.count("QXL103") == 1


def test_discovery_deduplicates_a_file_reached_through_a_directory_and_directly(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    found = discover([tmp_path, tmp_path / "a.py"], Config())
    assert [p.name for p in found] == ["a.py"]


def test_discovery_skips_a_directory_entry_that_is_not_analysable(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert [p.name for p in discover([tmp_path], Config())] == ["a.py"]


# Profile resolution partial knowledge ------------------------------------


def test_a_cli_qiskit_target_still_lets_the_runtime_come_from_the_project(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "d"\ndependencies = ["qiskit-ibm-runtime>=0.48"]\n', encoding="utf-8"
    )
    config = Config(target_qiskit="2.5", root=tmp_path)
    profile = resolve_profile(config)
    assert profile.qiskit.source is ProfileSource.CLI_FLAG
    assert profile.qiskit_ibm_runtime.source is ProfileSource.PROJECT_DEPENDENCIES


def test_a_pyproject_whose_project_table_is_not_a_table_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('project = "nonsense"\n', encoding="utf-8")
    profile = resolve_profile(Config(root=tmp_path))
    assert not profile.qiskit.known
    assert not profile.qiskit_ibm_runtime.known


def test_show_profile_prints_no_config_line_when_there_is_no_pyproject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert main([str(tmp_path), "--show-profile"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "qiskit:" in out
    assert "config:" not in out


def test_knowledge_from_text_records_where_a_value_came_from() -> None:
    knowledge = knowledge_from_text("0.48", ProfileSource.CONFIG, origin="somewhere")
    assert knowledge.source is ProfileSource.CONFIG
    assert knowledge.origin == "somewhere"


# Notebook: a continuation that runs to the end of the cell ---------------


def test_a_magic_continued_to_the_last_line_consumes_the_whole_cell() -> None:
    source = "x = 1\n%pip install a \\\n    b \\\n    c \\\n"
    text, changed = prepare_cell_source(source)
    assert changed is True
    assert "install" not in text
    assert "b" not in text
    assert len(text.splitlines()) == len(source.splitlines())


# Analyser branch pairs ---------------------------------------------------


def test_a_bare_return_does_not_escape_anything() -> None:
    # `return` with no value must still end the path without escaping a circuit.
    source = HEADER + (
        "def build(flag):\n"
        "    qc = QuantumCircuit(2)\n"
        "    if flag:\n"
        "        return\n"
        "    StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_extending_with_unknown_contents_leaves_what_is_already_known() -> None:
    # The extend cannot be applied, so the container keeps the elements it had
    # and a later append is still tracked. The circuit that is visible is still
    # proven unmeasured, so reporting it is right; whatever came from `loaded`
    # is simply not seen, which costs recall rather than precision.
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "circuits = []\n"
        "circuits.extend([*loaded])\n"
        "circuits.append(qc)\n"
        "StatevectorSampler().run(circuits)\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_extending_with_something_that_is_not_a_list_leaves_the_contents_alone() -> None:
    # Same conclusion as above by a different branch: the argument is not a
    # tracked sequence at all, so the extend is dropped and the circuit already
    # in the list stays visible and provably unmeasured.
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "circuits = [qc]\n"
        "circuits.extend(loaded)\n"
        "StatevectorSampler().run(circuits)\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_extending_with_a_known_list_keeps_the_tracking() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "circuits = []\n"
        "circuits.extend([qc])\n"
        "StatevectorSampler().run(circuits)\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_magic_called_with_a_non_constant_name_is_still_a_barrier() -> None:
    # run_cell_magic is a barrier whatever its name argument turns out to be.
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "get_ipython().run_cell_magic(chosen, '', '')\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_a_line_magic_with_a_non_constant_name_is_not_a_barrier() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "get_ipython().run_line_magic(chosen, '')\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_cli_runtime_target_still_lets_qiskit_come_from_the_project(
    tmp_path: Path,
) -> None:
    # The mirror of the case above: discovery runs for the half that is unknown
    # and leaves the half the flag already settled.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "d"\ndependencies = ["qiskit>=2.0"]\n', encoding="utf-8"
    )
    profile = resolve_profile(Config(target_runtime="0.48", root=tmp_path))
    assert profile.qiskit_ibm_runtime.source is ProfileSource.CLI_FLAG
    assert profile.qiskit.source is ProfileSource.PROJECT_DEPENDENCIES


def test_a_magic_name_that_is_not_a_string_is_treated_as_unnamed() -> None:
    # run_line_magic(0, ...) is not a magic qxlint knows, so it is not a barrier.
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "get_ipython().run_line_magic(0, '')\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_cell_magic_with_a_non_string_name_is_still_a_barrier() -> None:
    source = HEADER + (
        "qc = QuantumCircuit(2)\n"
        "get_ipython().run_cell_magic(0, '', '')\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []
