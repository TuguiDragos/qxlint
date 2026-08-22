"""Version profile discovery and configuration edges.

Covers the parts of the profile and config layers that only fire on malformed,
absent or ambiguous project metadata.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from qxlint.cli import main
from qxlint.config import (
    Config,
    ConfigCache,
    ConfigError,
    load_config,
    resolve_profile,
)
from qxlint.profile import (
    Applicability,
    ProfileSource,
    SemanticProfile,
    VersionKnowledge,
    discover_profile,
    find_project_root,
    knowledge_from_text,
)


def cli(text: str) -> VersionKnowledge:
    return knowledge_from_text(text, ProfileSource.CLI_FLAG)


# Applicability ----------------------------------------------------------


def test_an_unparsable_threshold_is_unknown_even_against_an_exact_pin() -> None:
    assert cli("1.2.3").at_least("two point oh") is Applicability.UNKNOWN


def test_a_specifier_that_allows_no_version_at_all_is_unknown() -> None:
    assert cli(">=2.0,<1.0").at_least("1.5") is Applicability.UNKNOWN


def test_an_arbitrary_equality_specifier_carries_no_ordering() -> None:
    # `===abc` is a legal specifier whose version is not a legal version.
    knowledge = cli("===abc")
    assert knowledge.describe() == "===abc"
    assert knowledge.at_least("1.0") is Applicability.UNKNOWN


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        ("1.2.2", Applicability.ALWAYS),
        ("1.2.3", Applicability.ALWAYS),
        ("1.2.4", Applicability.NEVER),
    ],
)
def test_a_micro_level_pin_is_compared_at_micro_precision(
    threshold: str, expected: Applicability
) -> None:
    assert cli("==1.2.3").at_least(threshold) is expected


def test_the_profile_reports_the_source_of_the_first_package_it_knows() -> None:
    profile = SemanticProfile(
        qiskit_ibm_runtime=knowledge_from_text("0.40", ProfileSource.LOCK_FILE)
    )
    assert profile.source is ProfileSource.LOCK_FILE


def test_a_profile_that_knows_nothing_has_no_source() -> None:
    assert SemanticProfile().source is ProfileSource.NONE


def test_each_at_least_helper_reads_its_own_package() -> None:
    profile = SemanticProfile(
        qiskit=knowledge_from_text("1.2", ProfileSource.CLI_FLAG),
        qiskit_ibm_runtime=knowledge_from_text("0.20", ProfileSource.CLI_FLAG),
    )
    assert profile.qiskit_at_least("1.0") is Applicability.ALWAYS
    assert profile.runtime_at_least("1.0") is Applicability.NEVER


# Parsing a version value ------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", ">=nonsense", "1.2.*", "not a version"])
def test_an_unusable_version_value_yields_no_knowledge(text: str) -> None:
    knowledge = knowledge_from_text(text, ProfileSource.CONFIG)
    assert not knowledge.known
    assert knowledge.source is ProfileSource.NONE
    assert knowledge.describe() == "unknown"


def test_a_value_that_is_no_version_can_still_parse_as_a_specifier() -> None:
    # A leading separator keeps the value off the version path but not off the
    # specifier path.
    knowledge = knowledge_from_text(",>=1.2", ProfileSource.CONFIG)
    assert knowledge.describe() == ">=1.2"
    assert knowledge.source is ProfileSource.CONFIG


# Discovery --------------------------------------------------------------


def test_find_project_root_reports_nothing_when_no_pyproject_is_above_the_path(
    tmp_path: Path,
) -> None:
    assert find_project_root(tmp_path / "deep" / "thing.py") is None


def test_a_directory_without_metadata_yields_an_empty_profile(tmp_path: Path) -> None:
    profile = discover_profile(tmp_path)
    assert not profile.qiskit.known
    assert not profile.qiskit_ibm_runtime.known


def test_a_dependency_carrying_an_environment_marker_is_not_a_target(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = [\"qiskit>=1.0; python_version < '3.12'\"]\n"
    )
    assert not discover_profile(tmp_path).qiskit.known


def test_a_dependency_pinned_to_a_direct_url_is_not_a_target(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["qiskit @ https://example.invalid/qiskit.whl"]\n'
    )
    assert not discover_profile(tmp_path).qiskit.known


def test_a_dependency_without_any_specifier_is_not_a_target(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["qiskit"]\n')
    assert not discover_profile(tmp_path).qiskit.known


def test_an_unparsable_requirement_is_skipped_without_losing_its_neighbours(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["qiskit >>> 1.0", "qiskit-ibm-runtime>=0.30"]\n'
    )
    profile = discover_profile(tmp_path)
    assert not profile.qiskit.known
    assert profile.qiskit_ibm_runtime.describe() == ">=0.30"


@pytest.mark.parametrize(
    "lock",
    [
        'package = "not a list"\n',
        'package = ["qiskit"]\n',
        '[[package]]\nname = "qiskit"\n',
        '[[package]]\nname = "qiskit"\nversion = "1.0.0"\n'
        '[[package]]\nname = "qiskit"\nversion = "2.0.0"\n',
        '[[package]]\nname = "qiskit"\nversion = "not-a-version"\n',
    ],
    ids=["not-a-list", "entry-not-a-table", "no-version", "two-versions", "bad-version"],
)
def test_a_lock_file_that_does_not_pin_one_version_is_ignored(tmp_path: Path, lock: str) -> None:
    (tmp_path / "uv.lock").write_text(lock)
    assert not discover_profile(tmp_path).qiskit.known


def test_a_lock_file_pinning_exactly_one_version_becomes_an_exact_target(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "Qiskit"\nversion = "1.4.2"\n'
        '[[package]]\nname = "qiskit-ibm-runtime"\nversion = "0.30.0"\n'
        '[[package]]\nname = "qiskit-ibm-runtime"\nversion = "0.31.0"\n'
    )
    profile = discover_profile(tmp_path)
    assert profile.qiskit.describe() == "1.4.2"
    assert profile.source is ProfileSource.LOCK_FILE
    assert not profile.qiskit_ibm_runtime.known


def test_malformed_metadata_is_treated_as_absent_rather_than_fatal(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n")
    (tmp_path / "uv.lock").write_text("[[package\n")
    assert not discover_profile(tmp_path).qiskit.known


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file whatever its mode")
def test_an_unreadable_pyproject_is_treated_as_absent(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\ndependencies = ["qiskit==1.2"]\n')
    path.chmod(0o000)
    try:
        assert not discover_profile(tmp_path).qiskit.known
    finally:
        path.chmod(0o644)


@pytest.mark.skipif(os.geteuid() == 0, reason="root traverses a directory whatever its mode")
def test_a_directory_that_cannot_be_traversed_has_no_project_root(tmp_path: Path) -> None:
    # Path.is_file raises PermissionError here on 3.11 to 3.13 and returns False
    # on 3.14, so the pathlib version would end the run on three of the four
    # supported interpreters.
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "pyproject.toml").write_text("[project]\n")
    closed.chmod(0o000)
    try:
        assert find_project_root(closed / "sub" / "app.py") is None
    finally:
        closed.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="root traverses a directory whatever its mode")
def test_an_unreadable_directory_does_not_end_the_run(tmp_path: Path) -> None:
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "app.py").write_text("x = 1\n")
    closed.chmod(0o000)
    try:
        assert main([str(closed)]) == 0
    finally:
        closed.chmod(0o755)


# Config -----------------------------------------------------------------


def test_a_pyproject_that_cannot_be_opened_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.mkdir()
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('preview = "yes"\n', "preview must be a boolean"),
        ("target-qiskit = 1\n", "target-qiskit must be a string"),
        ('per-file-ignores = ["notebooks/*"]\n', "per-file-ignores must be a table"),
        (
            '[tool.qxlint.per-file-ignores]\n"notebooks/*" = "QXL101"\n',
            "per-file-ignores['notebooks/*'] must be a list of strings",
        ),
    ],
    ids=["preview", "target-qiskit", "per-file-ignores", "per-file-ignores-codes"],
)
def test_a_setting_of_the_wrong_type_is_a_config_error(
    tmp_path: Path, body: str, message: str
) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.qxlint]\n" + body)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(path)


def test_a_configured_target_wins_over_the_declared_dependencies(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["qiskit==1.0", "qiskit-ibm-runtime>=0.30"]\n'
    )
    profile = resolve_profile(Config(target_qiskit="2.1", root=tmp_path))
    assert profile.qiskit.describe() == "2.1"
    assert profile.qiskit.source is ProfileSource.CLI_FLAG
    assert profile.qiskit_ibm_runtime.describe() == ">=0.30"
    assert profile.qiskit_ibm_runtime.source is ProfileSource.PROJECT_DEPENDENCIES


def test_the_config_cache_serves_the_override_for_every_path(tmp_path: Path) -> None:
    override = Config(select=("QXL101",))
    cache = ConfigCache(override=override)
    assert cache.for_path(tmp_path / "anywhere.py") is override


def test_the_config_cache_outside_a_project_serves_the_defaults(tmp_path: Path) -> None:
    assert ConfigCache().for_path(tmp_path / "thing.py") == Config()


def test_the_config_cache_resolves_each_project_root_separately(tmp_path: Path) -> None:
    for name, code in (("left", "QXL101"), ("right", "QXL103")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "pyproject.toml").write_text(f'[tool.qxlint]\nignore = ["{code}"]\n')
    cache = ConfigCache()
    first = cache.for_path(tmp_path / "left" / "a.py")
    assert first.ignore == ("QXL101",)
    assert cache.for_path(tmp_path / "right" / "b.py").ignore == ("QXL103",)
    # A second file under the same root reuses the loaded config.
    assert cache.for_path(tmp_path / "left" / "c.py") is first


# Profile discovery is cached per root ---------------------------------------
#
# Discovery parses pyproject.toml and uv.lock. It used to run once per analysed
# file, so a project with a large lock file spent most of a scan re-reading it.


def _count_discoveries(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    import qxlint.config as config_module

    seen: list[Path] = []
    real = config_module.discover_profile

    def counting(root: Path) -> SemanticProfile:
        seen.append(root)
        return real(root)

    monkeypatch.setattr(config_module, "discover_profile", counting)
    return seen


def test_profile_discovery_runs_once_per_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["qiskit>=2.0"]\n')
    seen = _count_discoveries(monkeypatch)

    cache = ConfigCache()
    first = cache.profile_for(cache.for_path(tmp_path / "a.py"))
    second = cache.profile_for(cache.for_path(tmp_path / "b.py"))

    assert first is second
    assert seen == [tmp_path]
    assert first.qiskit.known


def test_each_root_in_a_monorepo_is_discovered_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, pin in (("left", "qiskit>=2.0"), ("right", "qiskit-ibm-runtime>=0.48")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "pyproject.toml").write_text(f'[project]\ndependencies = ["{pin}"]\n')
    seen = _count_discoveries(monkeypatch)

    cache = ConfigCache()
    left = cache.profile_for(cache.for_path(tmp_path / "left" / "a.py"))
    right = cache.profile_for(cache.for_path(tmp_path / "right" / "b.py"))

    assert sorted(seen) == sorted([tmp_path / "left", tmp_path / "right"])
    assert left.qiskit.known and not left.qiskit_ibm_runtime.known
    assert right.qiskit_ibm_runtime.known and not right.qiskit.known


def test_a_different_cli_target_is_not_served_from_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["qiskit>=2.0"]\n')
    _count_discoveries(monkeypatch)

    cache = ConfigCache()
    plain = cache.profile_for(Config(root=tmp_path))
    overridden = cache.profile_for(Config(root=tmp_path, target_qiskit="2.1"))

    assert plain.qiskit.describe() != overridden.qiskit.describe()
    assert overridden.qiskit.source is ProfileSource.CLI_FLAG


def test_the_cache_agrees_with_resolve_profile_outside_a_project(tmp_path: Path) -> None:
    config = Config(target_runtime="0.48")
    assert ConfigCache().profile_for(config) == resolve_profile(config)


# Version discovery from a requirements file -----------------------------


def test_a_requirements_file_supplies_a_target(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("qiskit-ibm-runtime>=0.45\n")
    profile = discover_profile(tmp_path)
    assert str(profile.qiskit_ibm_runtime.specifier) == ">=0.45"


def test_a_requirements_file_anchors_a_root_when_there_is_no_pyproject(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("qiskit==2.0\n")
    (tmp_path / "sub").mkdir()
    assert find_project_root(tmp_path / "sub" / "app.py") == tmp_path


def test_a_pyproject_still_wins_over_a_requirements_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0"\ndependencies=["qiskit-ibm-runtime==0.30"]\n'
    )
    (tmp_path / "requirements.txt").write_text("qiskit-ibm-runtime==0.49\n")
    (tmp_path / "sub").mkdir()
    assert find_project_root(tmp_path / "sub" / "app.py") == tmp_path
    assert str(discover_profile(tmp_path).qiskit_ibm_runtime.specifier) == "==0.30"


def test_a_requirements_include_is_followed(tmp_path: Path) -> None:
    (tmp_path / "reqs").mkdir()
    (tmp_path / "requirements.txt").write_text("-r reqs/base.txt\n")
    (tmp_path / "reqs" / "base.txt").write_text("qiskit-ibm-runtime==0.45.0  # pinned\n")
    assert str(discover_profile(tmp_path).qiskit_ibm_runtime.specifier) == "==0.45.0"


def test_a_requirements_include_cycle_terminates(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("-r other.txt\nqiskit==2.0\n")
    (tmp_path / "other.txt").write_text("-r requirements.txt\n")
    assert str(discover_profile(tmp_path).qiskit.specifier) == "==2.0"


def test_option_lines_and_comments_in_a_requirements_file_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# a comment\n--index-url https://example.invalid\n-e .\n\nqiskit>=2.1\n"
    )
    assert str(discover_profile(tmp_path).qiskit.specifier) == ">=2.1"


def test_a_marker_in_a_requirements_file_makes_the_version_conditional(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text('qiskit>=2.0; python_version < "3.12"\n')
    assert not discover_profile(tmp_path).qiskit.known


def test_a_setup_file_anchors_a_root_without_supplying_a_version(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    (tmp_path / "sub").mkdir()
    assert find_project_root(tmp_path / "sub" / "app.py") == tmp_path
    assert not discover_profile(tmp_path).qiskit.known


def test_a_root_without_a_pyproject_still_loads_a_default_config(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("qiskit-ibm-runtime>=0.45\n")
    config = ConfigCache().for_path(tmp_path / "app.py")
    assert config.root == tmp_path
    assert config.source_path is None


def test_an_unreadable_requirements_file_is_not_an_error(tmp_path: Path) -> None:
    target = tmp_path / "requirements.txt"
    target.write_text("qiskit==2.0\n")
    target.chmod(0o000)
    try:
        assert not discover_profile(tmp_path).qiskit.known
    finally:
        target.chmod(0o644)


@pytest.mark.parametrize("directive", ["-r", "-r=", "--requirement="])
def test_an_empty_include_directive_is_skipped(tmp_path: Path, directive: str) -> None:
    (tmp_path / "requirements.txt").write_text(f"{directive}\nqiskit==2.0\n")
    assert str(discover_profile(tmp_path).qiskit.specifier) == "==2.0"


def test_an_unparsable_requirement_line_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("not a requirement!!\nqiskit==2.0\n")
    assert str(discover_profile(tmp_path).qiskit.specifier) == "==2.0"


def test_requirements_for_other_packages_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("numpy>=1.26\nscipy\n")
    assert not discover_profile(tmp_path).qiskit.known
    assert not discover_profile(tmp_path).qiskit_ibm_runtime.known
