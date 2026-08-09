"""Shared helpers for the test suite."""

from __future__ import annotations

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


@pytest.fixture
def qiskit_installed() -> bool:
    try:
        import qiskit  # noqa: F401
    except ImportError:
        pytest.skip("qiskit is not installed")
    return True
