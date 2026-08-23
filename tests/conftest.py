"""Shared helpers for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from qxlint.config import Config
from qxlint.diagnostics import Finding
from qxlint.engine import analyse_text
from qxlint.profile import ProfileSource, SemanticProfile, knowledge_from_text
from qxlint.registry import tiers


def profile(qiskit: str | None = None, runtime: str | None = None) -> SemanticProfile:
    return SemanticProfile(
        qiskit=(
            knowledge_from_text(qiskit, ProfileSource.CLI_FLAG)
            if qiskit
            else SemanticProfile().qiskit
        ),
        qiskit_ibm_runtime=(
            knowledge_from_text(runtime, ProfileSource.CLI_FLAG)
            if runtime
            else SemanticProfile().qiskit_ibm_runtime
        ),
    )


def lint(
    source: str,
    *,
    runtime: str | None = None,
    qiskit: str | None = None,
    select: tuple[str, ...] = (),
    preview: bool = False,
) -> list[Finding]:
    """Analyse a source string with the default rule set."""
    config = Config(select=select, preview=preview)
    enabled = config.enabled_codes(tiers())
    return analyse_text(
        source,
        display_path="t.py",
        profile=profile(qiskit, runtime),
        enabled=enabled,
    )


def codes(findings: list[Finding]) -> list[str]:
    return [finding.rule for finding in findings]


# Colour is decided by four environment variables: NO_COLOR, FORCE_COLOR, TERM
# and COLORTERM. A test that reads any of them from the shell it was started in
# passes or fails by accident, and two did. Under TERM=dumb the flag test failed
# because detect_depth correctly refuses colour there; under an exported
# FORCE_COLOR the piped-output test failed because escapes were forced back on.
#
# TERM is pinned to a colour capable value rather than cleared, on purpose. It
# is the hostile setting for the tests that assert no colour, so those have to
# prove the mechanism works instead of passing because the terminal was mute.
COLOUR_ENVIRONMENT = ("NO_COLOR", "FORCE_COLOR", "COLORTERM")


@pytest.fixture(autouse=True)
def neutral_colour_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test the same colour environment, whatever the shell had."""
    for name in COLOUR_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.fixture
def qiskit_installed() -> bool:
    try:
        import qiskit  # noqa: F401
    except ImportError:
        pytest.skip("qiskit is not installed")
    return True


# The repository holds files a source distribution deliberately does not ship:
# docs, the corpus, the editor and npm manifests, VERSION, CITATION.cff. Tests
# that read them check the repository rather than the package, so they skip
# where those files are absent. Without this a packager building from the sdist
# sees 63 failures and the rational response is to disable the suite entirely,
# which removes the only verification the package gets on their platform.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HAS_REPOSITORY_LAYOUT = (REPOSITORY_ROOT / "docs" / "rules").is_dir() and (
    REPOSITORY_ROOT / "VERSION"
).is_file()

requires_repository = pytest.mark.skipif(
    not HAS_REPOSITORY_LAYOUT,
    reason="needs the repository layout, which a source distribution does not ship",
)
