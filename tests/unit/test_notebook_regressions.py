"""Notebook cell shapes found by scanning external repositories.

Every case here is a real cell from the corpus scan of 2026-08-09 that qxlint
reported as unparsable when IPython itself would have accepted it.
"""

from __future__ import annotations

import pytest

from qxlint.notebook import parse_cell, prepare_cell_source


def prepared(source: str) -> str:
    text, _ = prepare_cell_source(source)
    parse_cell(text)
    return text


def line_count(text: str) -> int:
    return len(text.splitlines())


# Kolo-Naukowe-Axion/QC1_Quantum_Banknote_Classifier_on_ODRA_5,
# evaluation_and_comparison/iqm_spark/model_evaluation.ipynb cell 1.
MULTILINE_MAGIC = """\
import ssl

%pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org \\
             "qiskit>=2.0,<3.0" \\
             "qiskit-aer>=0.15.0" \\
             "iqm-client[qiskit]>=33.0,<34.0"

print("done")
"""

# LucaGandolfi77/Qiskit-QuantumComputing, QISKIT/Qiskit04.ipynb cell 14.
LEADING_INDENT = """\
 lista = [0.0001281945665608601,
 0.00025993396733031584,
 0.00024035982467323318]
 print(len(lista))
"""


def test_multiline_line_magic_with_backslash_continuation() -> None:
    text = prepared(MULTILINE_MAGIC)
    assert "qiskit-aer" not in text
    assert line_count(text) == line_count(MULTILINE_MAGIC)


def test_multiline_shell_escape_with_backslash_continuation() -> None:
    source = "x = 1\n!pip install foo \\\n    bar \\\n    baz\ny = 2\n"
    text = prepared(source)
    assert "bar" not in text
    assert line_count(text) == line_count(source)


def test_uniform_leading_indent_is_stripped() -> None:
    text = prepared(LEADING_INDENT)
    assert "lista" in text
    assert line_count(text) == line_count(LEADING_INDENT)


def test_leading_indent_of_several_spaces() -> None:
    source = "    a = 1\n    b = 2\n    print(a + b)\n"
    assert prepared(source).startswith("a = 1")


def test_real_indented_block_is_not_mistaken_for_a_leading_indent() -> None:
    source = "%matplotlib inline\nif cond:\n    a = 1\n"
    text = prepared(source)
    assert "    a = 1" in text


def test_magic_alone_in_an_indented_block_keeps_the_block_valid() -> None:
    source = "try:\n    %pip install qiskit\nexcept Exception:\n    pass\n"
    text = prepared(source)
    assert "pip install" not in text
    assert line_count(text) == line_count(source)


def test_shell_escape_alone_in_an_indented_block() -> None:
    source = "for name in names:\n    !echo $name\nprint('done')\n"
    text = prepared(source)
    assert "echo" not in text
    assert line_count(text) == line_count(source)


@pytest.mark.parametrize(
    "source",
    [
        MULTILINE_MAGIC,
        LEADING_INDENT,
        "try:\n    %pip install qiskit\nexcept Exception:\n    pass\n",
        "for name in names:\n    !echo $name\nprint('done')\n",
    ],
)
def test_line_count_is_preserved_for_every_regression(source: str) -> None:
    assert line_count(prepared(source)) == line_count(source)


def test_genuinely_broken_python_is_still_reported() -> None:
    # Qwenty228/Solving_QUBOs, TSP/local.ipynb cell 7: a missing comma. IPython
    # would reject this too, so reporting it is correct.
    source = "result = minimize(\n    fn,\n    tol=100\n    bounds=bounds\n)\n"
    text, _ = prepare_cell_source(source)
    with pytest.raises(SyntaxError):
        parse_cell(text)


def test_non_python_text_in_a_code_cell_is_still_reported() -> None:
    # LucaGandolfi77/Qiskit-QuantumComputing, QISKIT/Qiskit85.ipynb cell 11:
    # pasted program output stored in a code cell.
    source = "vj0i0=0.43, vj1i0=0.28, vj2i0=0.29\nvj0i1=0.31, vj1i1=0.35, vj2i1=0.35\n"
    text, _ = prepare_cell_source(source)
    with pytest.raises(SyntaxError):
        parse_cell(text)


def test_null_byte_in_a_cell_is_still_reported() -> None:
    # LucaGandolfi77/Qiskit-QuantumComputing, 1603/admm_solver.ipynb cell 1.
    source = 'x = "cor\x00rupt"\n'
    text, _ = prepare_cell_source(source)
    with pytest.raises((SyntaxError, ValueError)):
        parse_cell(text)


def test_a_colab_cell_mixing_shell_commands_and_python() -> None:
    # From the corpus scan of 2026-08-09: a Colab cell whose shell commands are
    # paths rather than names. `!./cloudflared` was left in place and the whole
    # cell was reported as unparsable.
    source = (
        "# 1. start the tunnel\n"
        "!pkill -9 -f streamlit\n"
        "!wget -q -nc https://example.invalid/cloudflared -O cloudflared\n"
        "!chmod +x cloudflared\n"
        "import socket\n"
        "s = socket.socket()\n"
        "if s.connect_ex(('127.0.0.1', 8501)) == 0:\n"
        "    print('up')\n"
        "    !./cloudflared tunnel --url http://127.0.0.1:8501\n"
        "else:\n"
        "    print('down')\n"
        "    !cat streamlit.log\n"
    )
    text = prepared(source)
    assert line_count(text) == line_count(source)
    assert "cloudflared tunnel" not in text
