"""The notebook magic policy.

Two properties matter and are checked for every case: the rewritten cell parses,
and it has the same number of lines as the original so reported line numbers
still point at what the user sees.
"""

from __future__ import annotations

import pytest

from qxlint.notebook import (
    BARRIER_CALL,
    UNKNOWN_CALL,
    NotebookError,
    parse_cell,
    parse_notebook,
    prepare_cell_source,
)


def prepare(source: str) -> str:
    text, _ = prepare_cell_source(source)
    parse_cell(text)
    return text


def line_count(text: str) -> int:
    return len(text.splitlines())


@pytest.mark.parametrize(
    "source",
    [
        "qc = QuantumCircuit(1)\n",
        "x = (1\n     % 2)\n",
        "def f():\n    return 1\n",
        "import asyncio\nawait asyncio.sleep(0)\n",
    ],
)
def test_valid_python_is_left_untouched(source: str) -> None:
    text, changed = prepare_cell_source(source)
    assert text == source
    assert changed is False


def test_top_level_await_parses() -> None:
    parse_cell("await thing()\n")


def test_safe_line_magic_becomes_a_blank_line() -> None:
    text = prepare("%matplotlib inline\nqc = 1\n")
    assert text.splitlines()[0] == ""
    assert BARRIER_CALL not in text


def test_namespace_mutating_magic_becomes_a_barrier() -> None:
    text = prepare("qc = 1\n%run other.py\nuse(qc)\n")
    assert BARRIER_CALL in text
    assert line_count(text) == 3


def test_unknown_line_magic_is_a_barrier() -> None:
    assert BARRIER_CALL in prepare("%totally_unknown thing\n")


def test_time_magic_unwraps_to_the_statement() -> None:
    assert prepare("%time y = f(x)\n").strip() == "y = f(x)"


def test_shell_escape_is_dropped_without_a_barrier() -> None:
    text = prepare("!pip install qiskit\nimport qiskit\n")
    assert BARRIER_CALL not in text
    assert line_count(text) == 2


def test_shell_capture_binds_an_unknown_value() -> None:
    assert UNKNOWN_CALL in prepare("out = !ls\nprint(out)\n")


# A shell command is not an identifier. Requiring a letter after the `!` left
# every one of these in place and the cell was reported as unparsable. The Colab
# notebook in the external corpus that exposed this used `!./cloudflared`.
@pytest.mark.parametrize(
    "command",
    [
        "!ls -la",
        "!./script.sh",
        "!./cloudflared tunnel --url http://127.0.0.1:8501",
        "!/usr/bin/env python script.py",
        "!~/bin/tool",
        "!$HOME/bin/tool",
        '!"program with spaces"',
        "!../build/run",
        "!2>&1 echo x",
        "!_private_tool",
        "!!ls",
        "! ls",
    ],
)
def test_any_shell_command_is_dropped(command: str) -> None:
    text = prepare(f"x = 1\n{command}\ny = 2\n")
    assert BARRIER_CALL not in text
    assert line_count(text) == 3


@pytest.mark.parametrize(
    "command",
    ["!./script.sh", "!/usr/bin/env python x.py", "!$HOME/tool"],
)
def test_a_shell_command_inside_a_block_keeps_its_indentation(command: str) -> None:
    text = prepare(f"if cond:\n    print(1)\n    {command}\n")
    assert text.splitlines()[2].startswith("    ")
    assert line_count(text) == 3


@pytest.mark.parametrize(
    "source",
    [
        # `!=` opens a continuation line in real formatting. Eating it would
        # hide the actual error in a cell that already fails to parse.
        "if (a\n   != b):\n    pass\nthis is not python\n",
        "x = (a\n   != b)\nthis is not python\n",
    ],
)
def test_a_not_equal_continuation_is_not_a_shell_command(source: str) -> None:
    text, _ = prepare_cell_source(source)
    assert "!=" in text


def test_python_body_cell_magic_keeps_its_body() -> None:
    text = prepare("%%time\nqc = QuantumCircuit(1)\nqc.measure_all()\n")
    assert "measure_all" in text
    assert BARRIER_CALL not in text


def test_non_python_cell_magic_drops_the_whole_cell() -> None:
    text = prepare("%%bash\necho hello\nnot python at all !!\n")
    assert text.splitlines()[0] == BARRIER_CALL
    assert "echo" not in text


def test_unknown_cell_magic_drops_the_whole_cell() -> None:
    text = prepare("%%mymagic arg\nqc = 1\n")
    assert BARRIER_CALL in text
    assert "qc = 1" not in text


def test_help_syntax_is_dropped() -> None:
    assert prepare("qc?\n").strip() == ""


def test_indented_magic_keeps_its_indentation() -> None:
    text = prepare("if cond:\n    %run other.py\n")
    assert text.splitlines()[1].startswith("    ")


@pytest.mark.parametrize(
    "source",
    [
        "%matplotlib inline\nqc = 1\n",
        "qc = 1\n%run other.py\nuse(qc)\n",
        "!pip install x\nimport x\n",
        "out = !ls\n",
        "%%time\na = 1\nb = 2\n",
    ],
)
def test_line_count_is_preserved(source: str) -> None:
    assert line_count(prepare(source)) == line_count(source)


# Notebook structure -----------------------------------------------------


def notebook(*sources: str) -> dict[str, object]:
    return {
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
            }
            for source in sources
        ],
    }


def test_cell_index_is_one_based_over_code_cells() -> None:
    document = notebook("a = 1\n", "b = 2\n")
    document["cells"].insert(0, {"cell_type": "markdown", "metadata": {}, "source": "# t"})
    parsed = parse_notebook("n.ipynb", document)
    assert [cell.index for cell in parsed.cells] == [1, 2]


def test_source_may_be_a_list_of_lines() -> None:
    document = notebook(["a = 1\n", "b = 2\n"])
    assert parse_notebook("n.ipynb", document).cells[0].original == "a = 1\nb = 2\n"


def test_non_object_root_is_rejected() -> None:
    with pytest.raises(NotebookError):
        parse_notebook("n.ipynb", [])


def test_missing_cells_array_is_rejected() -> None:
    with pytest.raises(NotebookError):
        parse_notebook("n.ipynb", {"nbformat": 4})
