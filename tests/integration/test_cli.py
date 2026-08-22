"""End to end CLI behaviour, including exit codes and output formats."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from qxlint.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main

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


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_file_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "good.py", GOOD)
    assert main([str(path)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == ""


def test_findings_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "bad.py", BAD)
    assert main([str(path)]) == EXIT_FINDINGS
    assert "QXL103" in capsys.readouterr().out


def test_missing_path_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["does-not-exist.py"]) == EXIT_ERROR
    assert "does not exist" in capsys.readouterr().err


def test_one_file_failing_does_not_cost_the_rest_of_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three real bugs reached this shape: a notebook that was not UTF-8, a
    # generated file that overflowed the parser, and a directory that could not
    # be traversed. Each ended the whole run with no output at all. Every one is
    # fixed at its source; this is the guarantee under them.
    write(tmp_path, "bad.py", BAD)
    write(tmp_path, "boom.py", GOOD)
    import qxlint.cli as cli_module

    real = cli_module.analyse_path

    def explode(path: Path, **kwargs: object) -> object:
        if path.name == "boom.py":
            raise ZeroDivisionError("something nobody predicted")
        return real(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli_module, "analyse_path", explode)
    assert main([str(tmp_path)]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert "QXL103" in captured.out
    assert "internal error analysing" in captured.err
    assert "boom.py" in captured.err


def test_invalid_config_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write(tmp_path, "pyproject.toml", '[tool.qxlint]\nselect = "nope"\n')
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path / "bad.py"), "--config", str(config)]) == EXIT_ERROR
    assert "must be a list" in capsys.readouterr().err


def test_unparsable_file_is_a_finding_not_an_internal_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "broken.py", "def f(\n")
    assert main([str(path)]) == EXIT_FINDINGS
    assert "QXL000" in capsys.readouterr().out


def test_directory_walk_finds_both_suffixes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    (tmp_path / "pkg").mkdir()
    write(tmp_path, "pkg/also_bad.py", BAD)
    assert main([str(tmp_path)]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert out.count("QXL103") == 2


def test_excluded_directories_are_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".venv").mkdir()
    write(tmp_path, ".venv/bad.py", BAD)
    assert main([str(tmp_path)]) == EXIT_OK


def test_select_narrows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "bad.py", BAD)
    assert main([str(path), "--select", "QXL101"]) == EXIT_OK


def test_ignore_removes(tmp_path: Path) -> None:
    path = write(tmp_path, "bad.py", BAD)
    assert main([str(path), "--ignore", "QXL103"]) == EXIT_OK


def test_json_format_is_valid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "bad.py", BAD)
    main([str(path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["coordinates"] == {
        "lineBase": 1,
        "columnBase": 1,
        "endColumnExclusive": True,
    }
    assert payload["findings"][0]["rule"] == "QXL103"
    assert payload["findings"][0]["location"]["kind"] == "source"


def test_sarif_format_is_well_formed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "bad.py", BAD)
    main([str(path), "--format", "sarif"])
    log = json.loads(capsys.readouterr().out)
    assert log["version"] == "2.1.0"
    assert log["$schema"].endswith("sarif-2.1.0.json")
    run = log["runs"][0]
    assert run["tool"]["driver"]["name"] == "qxlint"
    assert run["columnKind"] == "unicodeCodePoints"
    result = run["results"][0]
    region = result["locations"][0]["physicalLocation"]["region"]
    assert set(region) == {"startLine", "startColumn", "endLine", "endColumn"}
    assert result["partialFingerprints"]
    ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert result["ruleId"] in ids


def test_sarif_rules_carry_help_and_a_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "bad.py", BAD)
    main([str(path), "--format", "sarif"])
    log = json.loads(capsys.readouterr().out)
    for rule in log["runs"][0]["tool"]["driver"]["rules"]:
        assert rule["defaultConfiguration"]["level"] in {"error", "warning", "note"}
        assert "When this is legitimate" in rule["help"]["text"]


def test_target_flag_enables_the_version_gated_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'service = QiskitRuntimeService(channel="ibm_quantum")\n'
    )
    path = write(tmp_path, "svc.py", source)
    # An undeclared target reads as current, so the rule already fires. A target
    # proven to predate the deprecation is what silences it.
    assert main([str(path), "--target-runtime", "0.39"]) == EXIT_OK
    assert main([str(path), "--target-runtime", "0.48"]) == EXIT_FINDINGS
    assert "removed" in capsys.readouterr().out


def test_target_is_read_from_project_dependencies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\ndependencies = ["qiskit-ibm-runtime>=0.48"]\n',
    )
    path = write(
        tmp_path,
        "svc.py",
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'service = QiskitRuntimeService(channel="ibm_quantum")\n',
    )
    assert main([str(path)]) == EXIT_FINDINGS


def test_a_declared_range_that_reaches_the_removal_is_reported(tmp_path: Path) -> None:
    # The project says it supports up to 0.42, and the channel is gone from 0.41,
    # so the call breaks inside the range the project claims to support.
    write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\ndependencies = ["qiskit-ibm-runtime>=0.38,<0.43"]\n',
    )
    path = write(
        tmp_path,
        "svc.py",
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'service = QiskitRuntimeService(channel="ibm_quantum")\n',
    )
    assert main([str(path)]) == EXIT_FINDINGS


def test_a_declared_range_entirely_before_the_deprecation_is_silent(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\ndependencies = ["qiskit-ibm-runtime>=0.28,<0.40"]\n',
    )
    path = write(
        tmp_path,
        "svc.py",
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'service = QiskitRuntimeService(channel="ibm_quantum")\n',
    )
    assert main([str(path)]) == EXIT_OK


def test_uv_lock_pin_is_used_when_pyproject_says_nothing(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", '[project]\nname = "demo"\n')
    write(
        tmp_path,
        "uv.lock",
        'version = 1\n[[package]]\nname = "qiskit-ibm-runtime"\nversion = "0.48.0"\n',
    )
    path = write(
        tmp_path,
        "svc.py",
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'service = QiskitRuntimeService(channel="ibm_quantum")\n',
    )
    assert main([str(path)]) == EXIT_FINDINGS


def test_show_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "pyproject.toml", '[project]\nname = "d"\ndependencies = ["qiskit>=2.0"]\n')
    assert main([str(tmp_path), "--show-profile"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "qiskit:" in out
    assert "project-dependencies" in out


def test_output_is_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "a.py", BAD)
    write(tmp_path, "b.py", BAD)
    main([str(tmp_path)])
    first = capsys.readouterr().out
    main([str(tmp_path)])
    assert capsys.readouterr().out == first


# --statistics ------------------------------------------------------------


def test_statistics_summarises_instead_of_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    write(tmp_path, "also.py", BAD)
    assert main([str(tmp_path), "--statistics"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "QXL103" in out
    assert "unmeasured-circuit-to-sampler" in out
    assert "2 findings across 2 files" in out
    # The per finding lines are replaced, not appended.
    assert "circuit has no measurement instructions" not in out


def test_statistics_reports_the_number_of_files_scanned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    write(tmp_path, "good.py", GOOD)
    main([str(tmp_path), "--statistics"])
    assert "of 2 scanned" in capsys.readouterr().out


def test_statistics_on_a_clean_tree_says_so_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "good.py", GOOD)
    assert main([str(tmp_path), "--statistics"]) == EXIT_OK
    # The count is the point: a clean run has to be distinguishable from a run
    # that analysed nothing, which is otherwise byte identical.
    assert "No findings in 1 file." in capsys.readouterr().out


def test_statistics_preserves_the_exit_code(tmp_path: Path) -> None:
    write(tmp_path, "bad.py", BAD)
    # Findings still mean exit 1, so a CI gate behaves the same either way.
    assert main([str(tmp_path), "--statistics"]) == EXIT_FINDINGS


def test_statistics_as_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--statistics", "--format", "json"]) == EXIT_FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["totalFindings"] == 1
    assert payload["rules"][0]["rule"] == "QXL103"
    assert payload["filesScanned"] == 1


@pytest.mark.parametrize(
    ("flag", "value", "expected"),
    [
        ("--select", "ZZZ999", "no rule matches 'ZZZ999'"),
        ("--select", "QXL013", "no rule matches 'QXL013'"),
        ("--ignore", "NOPE", "no rule matches 'NOPE'"),
        ("--target-runtime", "abracadabra", "is not a version or a specifier"),
        ("--target-qiskit", "*", "is not a version or a specifier"),
    ],
)
def test_a_flag_value_that_can_do_nothing_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str, value: str, expected: str
) -> None:
    write(tmp_path, "bad.py", BAD)
    main([str(tmp_path), flag, value])
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--select", "ZZZ999"),
        ("--select", "QXL013"),
        ("--select", "QXL101,QXL013"),
        ("--target-runtime", "abracadabra"),
        ("--target-qiskit", "*"),
    ],
)
def test_a_flag_value_that_can_do_nothing_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str, value: str
) -> None:
    # A mistyped --select turns every rule off, so the run reports nothing and a
    # CI gate goes green without having checked anything. Exit 2 makes that
    # impossible. Same for a target that is not a version: it silently disables
    # the version gated rules.
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), flag, value]) == EXIT_ERROR


def test_an_unmatched_ignore_is_only_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An ignore that matches nothing removes nothing, so it cannot make a run
    # wrongly clean. The findings still have to be reported.
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--ignore", "NOPE"]) == EXIT_FINDINGS
    assert "no rule matches 'NOPE'" in capsys.readouterr().err


def test_a_configured_code_that_matches_nothing_warns_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A pyproject.toml belongs to the tree being scanned, so a stale entry in it
    # is reported rather than ending the run. The codes that do match must not
    # be reported, and must still work.
    write(tmp_path, "bad.py", BAD)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.qxlint]\nselect = ["QXL1", "QXL013"]\nignore = ["QXL101", "NOPE"]\n'
    )
    assert main([str(tmp_path)]) == EXIT_FINDINGS
    err = capsys.readouterr().err
    assert "select: no rule matches 'QXL013'" in err
    assert "ignore: no rule matches 'NOPE'" in err
    assert "QXL1'" not in err
    assert "QXL101'" not in err


def test_a_configuration_with_only_valid_codes_says_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.qxlint]\nselect = ["QXL1"]\nignore = ["QXL101"]\n'
    )
    assert main([str(tmp_path)]) == EXIT_FINDINGS
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--select", "QXL1"),
        ("--select", "QXL103,QXL2"),
        ("--ignore", "QXL"),
        ("--target-runtime", "0.48"),
        ("--target-qiskit", ">=2.0"),
        ("--select", ""),
    ],
)
def test_a_usable_flag_value_says_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str, value: str
) -> None:
    write(tmp_path, "bad.py", BAD)
    main([str(tmp_path), flag, value])
    assert capsys.readouterr().err == ""


def test_statistics_with_sarif_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--statistics", "--format", "sarif"]) == EXIT_ERROR
    assert "no SARIF form" in capsys.readouterr().err


def test_the_no_color_flag_reaches_the_renderer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Captured output is not a terminal, so colour is off anyway and the flag
    # made no observable difference. FORCE_COLOR turns it on, which is what
    # makes the wiring between the flag and detect_depth visible at all.
    write(tmp_path, "bad.py", BAD)
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)

    main([str(tmp_path), "--statistics"])
    assert "\033" in capsys.readouterr().out

    main([str(tmp_path), "--statistics", "--no-color"])
    assert "\033" not in capsys.readouterr().out

    main([str(tmp_path)])
    assert "\033" in capsys.readouterr().out

    main([str(tmp_path), "--no-color"])
    assert "\033" not in capsys.readouterr().out


def test_statistics_output_carries_no_escapes_when_piped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    main([str(tmp_path), "--statistics"])
    assert "\033" not in capsys.readouterr().out


def test_statistics_respects_select(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--statistics", "--select", "QXL101"]) == EXIT_OK
    assert "No findings in 1 file." in capsys.readouterr().out


def test_statistics_is_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "bad.py", BAD)
    write(tmp_path, "also.py", BAD)
    main([str(tmp_path), "--statistics"])
    first = capsys.readouterr().out
    for _ in range(5):
        main([str(tmp_path), "--statistics"])
        assert capsys.readouterr().out == first


def test_no_color_env_suppresses_colour_in_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    write(tmp_path, "bad.py", BAD)
    main([str(tmp_path)])
    assert "\033" not in capsys.readouterr().out


def test_an_unexpected_exception_becomes_exit_two_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented contract: qxlint reports, it does not crash at the user.

    This is the outermost net, for a failure before any file is reached. A
    failure on one file is caught per file instead, and is covered by
    ``test_one_file_failing_does_not_cost_the_rest_of_the_run``.
    """
    write(tmp_path, "bad.py", BAD)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr("qxlint.cli.discover", explode)
    assert main([str(tmp_path)]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "internal error" in err
    assert "RuntimeError" in err
    assert "simulated internal failure" in err
    assert "Traceback" not in err


def test_a_named_pipe_does_not_hang_the_run(tmp_path: Path) -> None:
    """The end to end case for the FIFO guard, run out of process.

    Opening a FIFO blocks until a writer appears, with no timeout, so a
    regression here would hang the test run rather than fail it. A subprocess
    with a deadline turns that back into an ordinary failure.
    """
    os.mkfifo(tmp_path / "pipe.py")
    write(tmp_path, "bad.py", BAD)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "qxlint", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("qxlint blocked on a named pipe instead of reporting it")
    assert result.returncode == EXIT_FINDINGS
    assert "not a regular file" in result.stdout
    assert "QXL103" in result.stdout


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 701 needs 3.12")
def test_nested_same_quotes_in_an_fstring_parse_from_312(tmp_path: Path) -> None:
    # qxlint parses with the interpreter running it, so syntax that changed
    # between versions is judged by that version. PEP 701 made this legal in
    # 3.12; on 3.11 the same file is QXL000. Both sides are pinned so the
    # difference is a documented property rather than a surprise.
    path = write(tmp_path, "fstring.py", 'd = {"k": 1}\nprint(f"{d["k"]}")\n')
    assert main([str(path)]) == EXIT_OK


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="PEP 701 landed in 3.12")
def test_nested_same_quotes_in_an_fstring_are_unparsable_on_311(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "fstring.py", 'd = {"k": 1}\nprint(f"{d["k"]}")\n')
    assert main([str(path)]) == EXIT_FINDINGS
    assert "QXL000" in capsys.readouterr().out


# Buffers on stdin -------------------------------------------------------
#
# An editor has to be able to check what the user is looking at, which is not
# what is on disk until they save.


def feed(monkeypatch: pytest.MonkeyPatch, text: str | bytes) -> None:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def test_stdin_reports_findings_for_a_path_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The point of the flag: nothing is read from disk, so an unsaved file works.
    feed(monkeypatch, BAD)
    assert main(["--stdin-filename", "/nowhere/unsaved.py", "--no-color"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "QXL103" in out
    assert "/nowhere/unsaved.py" in out


def test_stdin_on_a_clean_buffer_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, GOOD)
    assert main(["--stdin-filename", "buffer.py"]) == EXIT_OK
    assert capsys.readouterr().out.strip() == ""


def test_stdin_ignores_what_is_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = write(tmp_path, "edited.py", BAD)
    feed(monkeypatch, GOOD)
    assert main(["--stdin-filename", str(saved)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == ""


def test_stdin_accepts_a_notebook(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    notebook = {
        "cells": [{"cell_type": "code", "source": BAD.splitlines(keepends=True), "metadata": {}}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    feed(monkeypatch, json.dumps(notebook))
    assert main(["--stdin-filename", "buffer.ipynb", "--no-color"]) == EXIT_FINDINGS
    assert "QXL103" in capsys.readouterr().out


def test_stdin_reports_a_notebook_that_is_not_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, "not a notebook")
    assert main(["--stdin-filename", "buffer.ipynb", "--no-color"]) == EXIT_FINDINGS
    assert "QXL000" in capsys.readouterr().out


def test_stdin_refuses_positional_paths(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([".", "--stdin-filename", "buffer.py"]) == EXIT_ERROR
    assert "no paths may be given" in capsys.readouterr().err


def test_stdin_refuses_a_suffix_it_cannot_analyse(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--stdin-filename", "buffer.txt"]) == EXIT_ERROR
    assert "expected a .py or a .ipynb path" in capsys.readouterr().err


def test_stdin_refuses_input_that_is_not_utf8(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, b"\xff\xfe not utf-8")
    assert main(["--stdin-filename", "buffer.py"]) == EXIT_ERROR
    assert "not valid UTF-8" in capsys.readouterr().err


def test_stdin_honours_a_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write(tmp_path, "pyproject.toml", '[tool.qxlint]\nignore = ["QXL103"]\n')
    feed(monkeypatch, BAD)
    assert main(["--stdin-filename", "buffer.py", "--config", str(config)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == ""


def test_stdin_honours_select(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, BAD)
    assert main(["--stdin-filename", "buffer.py", "--select", "QXL101"]) == EXIT_OK
    assert capsys.readouterr().out.strip() == ""


def test_stdin_rejects_a_select_that_matches_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--stdin-filename", "buffer.py", "--select", "QXL999"]) == EXIT_ERROR
    assert "no rule matches" in capsys.readouterr().err


def test_stdin_supports_statistics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, BAD)
    assert main(["--stdin-filename", "buffer.py", "--statistics", "--no-color"]) == EXIT_FINDINGS
    assert "QXL103" in capsys.readouterr().out


def test_stdin_rejects_sarif_statistics(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--stdin-filename", "b.py", "--statistics", "--format", "sarif"])
    assert code == EXIT_ERROR
    assert "no SARIF form" in capsys.readouterr().err


def test_stdin_can_show_the_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, BAD)
    assert main(["--stdin-filename", "buffer.py", "--show-profile"]) == EXIT_OK
    assert "qiskit:" in capsys.readouterr().out


def test_stdin_warns_about_a_stale_root_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write(tmp_path, "pyproject.toml", '[tool.qxlint]\nignore = ["QXL777"]\n')
    feed(monkeypatch, GOOD)
    assert main(["--stdin-filename", "buffer.py", "--config", str(config)]) == EXIT_OK
    assert "no rule matches" in capsys.readouterr().err


def test_the_json_payload_names_the_engine_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from qxlint import __version__

    feed(monkeypatch, GOOD)
    assert main(["--stdin-filename", "buffer.py", "--format", "json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["toolVersion"] == __version__


@pytest.mark.parametrize("value", ["QXL3", "QXL300", "QXL300,QXL301", "QXL302"])
def test_a_selection_of_only_circuit_rules_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    # These are registered rules, so they pass the "no rule matches" guard, but
    # they read an in-memory circuit and can never fire from a file. Leaving the
    # run green would take a CI gate green having checked nothing.
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--select", value]) == 2
    assert "every selected rule is a circuit rule" in capsys.readouterr().err


def test_a_circuit_rule_alongside_a_source_rule_still_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "bad.py", BAD)
    assert main([str(tmp_path), "--select", "QXL301,QXL103"]) == 1
    assert "QXL103" in capsys.readouterr().out


def test_selecting_the_unparsable_rule_is_allowed(tmp_path: Path) -> None:
    # QXL000 defines no source hook but the engine emits it, so it is reachable.
    write(tmp_path, "clean.py", "x = 1\n")
    assert main([str(tmp_path), "--select", "QXL000"]) == 0


def test_a_run_that_analysed_nothing_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notes.md").write_text("nothing to lint\n")
    assert main([str(tmp_path)]) == EXIT_OK
    captured = capsys.readouterr()
    assert "no Python or notebook files were analysed" in captured.err
    assert captured.out == ""


def test_statistics_distinguishes_nothing_analysed_from_nothing_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "empty").mkdir()
    assert main([str(tmp_path / "empty"), "--statistics"]) == EXIT_OK
    assert "No files were analysed." in capsys.readouterr().out


def test_a_clean_run_over_several_files_counts_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "a.py", GOOD)
    write(tmp_path, "b.py", GOOD)
    assert main([str(tmp_path), "--statistics"]) == EXIT_OK
    assert "No findings in 2 files." in capsys.readouterr().out
