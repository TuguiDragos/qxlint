"""The fixture corpus.

`clean` and `negative` are the release gate: a finding in either is a false
positive, and the run is expected to be silent. `positive` pins which rule fires
where.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qxlint.config import Config
from qxlint.engine import analyse_path
from qxlint.profile import ProfileSource, SemanticProfile, knowledge_from_text
from qxlint.registry import tiers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RUNTIME_TARGET = SemanticProfile(
    qiskit_ibm_runtime=knowledge_from_text("0.48", ProfileSource.CLI_FLAG)
)


def analyse(path: Path, profile: SemanticProfile | None = None) -> list:
    config = Config()
    return analyse_path(
        path,
        config=config,
        profile=profile or SemanticProfile(),
        enabled=config.enabled_codes(tiers()),
    )


def files(group: str, suffix: str = "*.py") -> list[Path]:
    return sorted((FIXTURES / group).glob(suffix))


def test_the_corpus_exists() -> None:
    assert files("clean")
    assert files("positive")
    assert files("negative")
    assert files("notebooks", "*.ipynb")


@pytest.mark.parametrize("path", files("clean"), ids=lambda p: p.name)
def test_clean_fixtures_report_nothing(path: Path) -> None:
    findings = analyse(path, RUNTIME_TARGET)
    assert findings == [], [f.render_text() for f in findings]


@pytest.mark.parametrize("path", files("negative"), ids=lambda p: p.name)
def test_negative_fixtures_report_nothing(path: Path) -> None:
    findings = analyse(path, RUNTIME_TARGET)
    assert findings == [], [f.render_text() for f in findings]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("qxl101_get_counts.py", ["QXL101"] * 3),
        ("qxl102_quasi_dists.py", ["QXL102"]),
        ("qxl103_unmeasured.py", ["QXL103"] * 3),
        ("qxl201_channel.py", ["QXL201"] * 2),
    ],
)
def test_positive_fixtures_report_exactly_their_rule(name: str, expected: list[str]) -> None:
    findings = analyse(FIXTURES / "positive" / name, RUNTIME_TARGET)
    assert [f.rule for f in findings] == expected


def test_version_gated_fixture_reports_without_a_target() -> None:
    # An undeclared target reads as current, where the channel is long gone.
    findings = analyse(FIXTURES / "positive" / "qxl201_channel.py")
    # The fixture builds the service twice, so it reports twice.
    assert [f.rule for f in findings] == ["QXL201", "QXL201"]


def test_clean_notebook_reports_nothing() -> None:
    findings = analyse(FIXTURES / "notebooks" / "clean.ipynb")
    assert findings == [], [f.render_text() for f in findings]


def test_magics_notebook_fires_only_where_it_should() -> None:
    findings = analyse(FIXTURES / "notebooks" / "magics.ipynb")
    reported = {(f.location.cell_index, f.rule) for f in findings}

    # Cell 4 samples a circuit built in cell 3 with no measurement.
    assert (4, "QXL103") in reported
    # Cell 8 is a `%%time` cell whose body is real Python.
    assert (8, "QXL103") in reported
    # Cell 6 measures, and a `%%bash` cell before it must not have hidden the
    # imports it needs.
    assert not any(cell == 6 for cell, _ in reported)
    # Cell 7 runs `%run`, which can rebind anything, so nothing may be claimed.
    assert not any(cell == 7 for cell, _ in reported)


def test_every_fixture_parses() -> None:
    for group in ("clean", "positive", "negative"):
        for path in files(group):
            findings = analyse(path, RUNTIME_TARGET)
            assert all(f.rule != "QXL000" for f in findings), path
