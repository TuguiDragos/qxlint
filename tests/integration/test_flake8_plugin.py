"""The flake8 plugin, driven the way flake8 drives it."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from qxlint import flake8_plugin
from qxlint.config import ConfigCache
from qxlint.flake8_plugin import QxlintFlake8Plugin


def reset_config_cache() -> None:
    """The plugin caches config per root, so each case needs a fresh one."""
    flake8_plugin._CACHE = ConfigCache()


SOURCE = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(2)\n"
    "qc.h(0)\n"
    "StatevectorSampler().run([qc])\n"
)


def run(source: str, filename: str = "sample.py") -> list[tuple[int, int, str, type]]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    return list(QxlintFlake8Plugin(tree, filename, lines).run())


def test_plugin_yields_the_expected_tuple() -> None:
    results = run(SOURCE)
    assert len(results) == 1
    line, column, message, cls = results[0]
    assert line == 5
    assert column == 0
    assert message.startswith("QXL103 ")
    assert cls is QxlintFlake8Plugin


def test_plugin_is_silent_on_correct_code() -> None:
    source = SOURCE.replace("qc.h(0)\n", "qc.measure_all()\n")
    assert run(source) == []


def test_plugin_reports_zero_based_columns_like_flake8() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "counts = result.get_counts()\n"
    )
    line, column, message, _ = run(source)[0]
    assert (line, column) == (6, 9)
    assert message.startswith("QXL101 ")


def test_plugin_reports_the_raw_ast_byte_column_on_a_non_ascii_line() -> None:
    """flake8 columns are byte based, so the plugin must undo the conversion.

    The accented text sits before the reported node, so the byte column and the
    character column genuinely differ, and the plugin must match what flake8
    itself would have produced from ``col_offset``.
    """
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "rés = StatevectorSampler().run([qc]).result()\n"
        "compté = rés.get_counts()\n"
    )
    line, column, _, _ = run(source)[0]

    tree = ast.parse(source)
    call = tree.body[-1].value
    assert isinstance(call, ast.Call)
    node = call.func
    assert (line, column) == (node.lineno, node.col_offset)


def test_plugin_survives_an_unreadable_file() -> None:
    assert run("x = 1\n", filename="missing.py") == []


def test_plugin_version_matches_the_package() -> None:
    from qxlint import __version__

    assert QxlintFlake8Plugin.version == __version__
    assert QxlintFlake8Plugin.name == "qxlint"


# A broken configuration used to end the plugin's run with a bare `return`, so
# `flake8 --select=QXL` printed nothing and exited 0. That takes a CI gate green
# on a project qxlint never analysed, which is the one failure mode a linter
# must not have. Reproduced before the fix: exit 0 and no output, while the
# standalone command exited 2 and named the key.


def broken_config(tmp_path: Path, text: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    source = tmp_path / "bad.py"
    source.write_text(SOURCE, encoding="utf-8")
    return source


@pytest.mark.parametrize(
    ("config", "fragment"),
    [
        ("[tool.qxlint]\nnope = 1\n", "unknown key"),
        ("[tool.qxlint\nselect = [", "invalid TOML"),
        ("[tool.qxlint]\nselect = 42\n", "select"),
        ('[tool.qxlint]\ntarget-runtime = "not-a-version"\n', "not a version"),
    ],
)
def test_a_broken_config_is_reported_rather_than_swallowed(
    tmp_path: Path, config: str, fragment: str
) -> None:
    source = broken_config(tmp_path, config)
    reset_config_cache()
    results = run(SOURCE, str(source))
    assert len(results) == 1, results
    line, column, message, cls = results[0]
    assert (line, column) == (1, 0)
    assert message.startswith("QXL000 ")
    assert fragment in message
    assert cls is QxlintFlake8Plugin


def test_a_working_config_still_produces_the_findings(tmp_path: Path) -> None:
    source = broken_config(tmp_path, '[tool.qxlint]\nselect = ["QXL103"]\n')
    reset_config_cache()
    results = run(SOURCE, str(source))
    assert [message.split()[0] for _, _, message, _ in results] == ["QXL103"]


def test_every_file_under_a_broken_config_is_reported(tmp_path: Path) -> None:
    # One finding per file, so no file is silently skipped and the count in a
    # CI log matches the number of files that were not analysed.
    source = broken_config(tmp_path, "[tool.qxlint]\nnope = 1\n")
    other = tmp_path / "other.py"
    other.write_text(SOURCE, encoding="utf-8")
    reset_config_cache()
    assert len(run(SOURCE, str(source))) == 1
    assert len(run(SOURCE, str(other))) == 1
