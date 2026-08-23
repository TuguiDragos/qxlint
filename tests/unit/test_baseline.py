"""Baseline reading, writing and matching."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from qxlint.baseline import (
    FORMAT_VERSION,
    Baseline,
    BaselineError,
    build,
    fingerprint,
    load,
    serialise,
)
from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    InstructionStep,
    NotebookLocation,
    SourceLocation,
)


def finding(rule: str = "QXL101", message: str = "m", path: str = "a.py", line: int = 1) -> Finding:
    return Finding(
        rule=rule, message=message, location=SourceLocation(path=path, line=line, column=1)
    )


def test_fingerprint_ignores_the_line_and_column() -> None:
    assert fingerprint(finding(line=1)) == fingerprint(finding(line=999))


def test_fingerprint_separates_rules_and_messages_and_files() -> None:
    base = fingerprint(finding())
    assert base != fingerprint(finding(rule="QXL102"))
    assert base != fingerprint(finding(message="other"))
    assert base != fingerprint(finding(path="b.py"))


def test_fingerprint_normalises_a_windows_path() -> None:
    assert fingerprint(finding(path="src\\pkg\\a.py"))[0] == "src/pkg/a.py"


def test_fingerprint_of_a_notebook_uses_the_file() -> None:
    location = NotebookLocation(path="nb.ipynb", cell_index=2, line=3, column=1)
    assert fingerprint(Finding(rule="QXL101", message="m", location=location))[0] == "nb.ipynb"


def test_fingerprint_of_a_circuit_finding_falls_back_to_the_circuit() -> None:
    location = CircuitLocation(circuit_name="qc", path=(InstructionStep(index=0),))
    key = fingerprint(Finding(rule="QXL300", message="m", location=location))
    assert key[0] == "qc[0]"


def test_a_baseline_suppresses_exactly_what_it_recorded() -> None:
    findings = [finding(), finding(rule="QXL102")]
    remaining, stale = build(findings).filter(list(findings))
    assert remaining == []
    assert stale == 0


def test_a_repeat_beyond_the_recorded_count_is_reported() -> None:
    baseline = build([finding()])
    remaining, stale = baseline.filter([finding(line=1), finding(line=2)])
    assert len(remaining) == 1
    assert stale == 0


def test_a_recorded_finding_that_is_gone_counts_as_stale() -> None:
    baseline = build([finding(), finding(rule="QXL102")])
    remaining, stale = baseline.filter([finding()])
    assert remaining == []
    assert stale == 1


def test_total_counts_every_recorded_occurrence() -> None:
    assert build([finding(), finding(line=2), finding(rule="QXL102")]).total == 3


def test_a_round_trip_preserves_the_counts(tmp_path: Path) -> None:
    baseline = build([finding(), finding(line=2), finding(rule="QXL102")])
    path = tmp_path / "b.json"
    path.write_text(serialise(baseline, tool_version="9.9.9"), encoding="utf-8")
    assert load(path).counts == baseline.counts


def test_serialising_is_deterministic() -> None:
    one = build([finding(rule="QXL102"), finding()])
    two = build([finding(), finding(rule="QXL102")])
    assert serialise(one, tool_version="1") == serialise(two, tool_version="1")


def test_the_document_records_the_version_and_the_tool() -> None:
    document = json.loads(serialise(build([finding()]), tool_version="9.9.9"))
    assert document["version"] == FORMAT_VERSION
    assert document["tool"] == "qxlint 9.9.9"
    assert document["entries"] == [{"path": "a.py", "rule": "QXL101", "message": "m", "count": 1}]


def test_an_empty_baseline_suppresses_nothing() -> None:
    remaining, stale = Baseline(Counter()).filter([finding()])
    assert len(remaining) == 1
    assert stale == 0


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("not json", "not valid JSON"),
        ("[]", "expected an object at the top level"),
        ('{"version": 2, "entries": []}', "unsupported format version"),
        ('{"version": 1}', "'entries' must be a list"),
        ('{"version": 1, "entries": {}}', "'entries' must be a list"),
        ('{"version": 1, "entries": [1]}', "entry 0 is not an object"),
        (
            '{"version": 1, "entries": [{"rule": "R", "message": "m", "count": 1}]}',
            "missing 'path'",
        ),
        (
            '{"version": 1, "entries": [{"path": 1, "rule": "R", "message": "m", "count": 1}]}',
            "non string path",
        ),
        (
            '{"version": 1, "entries": [{"path": "a", "rule": "R", "message": "m", "count": 0}]}',
            "positive integer",
        ),
        (
            '{"version": 1, "entries": [{"path": "a", "rule": "R", "message": "m",'
            ' "count": true}]}',
            "positive integer",
        ),
        (
            '{"version": 1, "entries": [{"path": "a", "rule": "R", "message": "m", "count": "1"}]}',
            "positive integer",
        ),
    ],
)
def test_a_malformed_baseline_is_an_error_not_an_empty_baseline(
    tmp_path: Path, text: str, fragment: str
) -> None:
    path = tmp_path / "b.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BaselineError, match=fragment):
        load(path)


def test_an_unreadable_baseline_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="cannot read baseline"):
        load(tmp_path / "missing" / "b.json")


def test_duplicate_entries_in_the_file_add_up(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    entry = {"path": "a.py", "rule": "QXL101", "message": "m", "count": 1}
    path.write_text(json.dumps({"version": 1, "entries": [entry, entry]}), encoding="utf-8")
    remaining, stale = load(path).filter([finding(), finding(line=2)])
    assert remaining == []
    assert stale == 0
