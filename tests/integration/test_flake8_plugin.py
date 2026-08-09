"""The flake8 plugin, driven the way flake8 drives it."""

from __future__ import annotations

import ast

from qxlint.flake8_plugin import QxlintFlake8Plugin

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
