"""Rule selection precedence, suppression, and column conversion."""

from __future__ import annotations

from pathlib import Path

import pytest

from qxlint.config import Config, ConfigError, load_config
from qxlint.diagnostics import Tier
from qxlint.noqa import ALL, parse_noqa
from qxlint.registry import tiers
from qxlint.source import SourceFile, byte_offset_to_column

REGISTERED = {
    "QXL000": Tier.DEFAULT,
    "QXL101": Tier.DEFAULT,
    "QXL103": Tier.DEFAULT,
    "QXL201": Tier.DEFAULT,
    "QXL302": Tier.PREVIEW,
}


def test_default_selection_is_every_default_tier_rule() -> None:
    assert Config().enabled_codes(REGISTERED) == frozenset({"QXL000", "QXL101", "QXL103", "QXL201"})


def test_preview_rules_stay_off_by_default() -> None:
    assert "QXL302" not in Config().enabled_codes(REGISTERED)


def test_preview_flag_enables_preview_rules() -> None:
    assert "QXL302" in Config(preview=True).enabled_codes(REGISTERED)


def test_preview_rules_stay_off_unless_asked_for() -> None:
    # Nothing verified this: a preview rule leaking into the default set would
    # have gone unnoticed by the whole suite.
    registered = tiers()
    preview = {code for code, tier in registered.items() if tier is Tier.PREVIEW}
    assert preview, "the check is meaningless if no rule is preview tier"

    assert not (Config().enabled_codes(registered) & preview)
    assert preview <= Config(preview=True).enabled_codes(registered)
    for code in sorted(preview):
        assert code in Config(select=(code,)).enabled_codes(registered)


def test_select_matches_by_prefix() -> None:
    assert Config(select=("QXL1",)).enabled_codes(REGISTERED) == frozenset({"QXL101", "QXL103"})


def test_naming_a_preview_rule_exactly_enables_it_without_the_preview_flag() -> None:
    assert Config(select=("QXL302",)).enabled_codes(REGISTERED) == frozenset({"QXL302"})


def test_a_prefix_alone_does_not_enable_a_preview_rule() -> None:
    assert Config(select=("QXL3",)).enabled_codes(REGISTERED) == frozenset()


def test_ignore_applies_after_select() -> None:
    config = Config(select=("QXL",), ignore=("QXL10",))
    assert config.enabled_codes(REGISTERED) == frozenset({"QXL000", "QXL201"})


def test_ignore_wins_over_an_exact_select() -> None:
    config = Config(select=("QXL101",), ignore=("QXL101",))
    assert config.enabled_codes(REGISTERED) == frozenset()


def test_per_file_ignores_match_a_glob() -> None:
    config = Config(per_file_ignores=(("tests/*", ("QXL103",)),))
    assert config.ignored_for_path("tests/thing.py") == frozenset({"QXL103"})
    assert config.ignored_for_path("src/thing.py") == frozenset()


def test_per_file_ignores_match_a_bare_filename_pattern() -> None:
    config = Config(per_file_ignores=(("conftest.py", ("QXL101",)),))
    assert config.ignored_for_path("deep/nested/conftest.py") == frozenset({"QXL101"})


def test_excluded_directories() -> None:
    assert Config().is_excluded(Path(".venv/lib/thing.py"))
    assert not Config().is_excluded(Path("src/thing.py"))


def test_extend_exclude_adds_to_the_defaults() -> None:
    config = Config(extend_exclude=("vendor",))
    assert config.is_excluded(Path("vendor/thing.py"))
    assert config.is_excluded(Path(".venv/lib/thing.py"))
    assert not config.is_excluded(Path("src/thing.py"))


def test_exclude_replaces_the_defaults() -> None:
    # Deliberate: a project may want to lint inside a directory this list skips.
    config = Config(exclude=("vendor",))
    assert config.is_excluded(Path("vendor/thing.py"))
    assert not config.is_excluded(Path(".venv/lib/thing.py"))


def test_exclude_and_extend_exclude_together(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.qxlint]\nexclude = ["vendor"]\nextend-exclude = ["generated"]\n')
    config = load_config(path)
    assert config.exclude == ("vendor",)
    assert config.extend_exclude == ("generated",)
    assert config.is_excluded(Path("vendor/a.py"))
    assert config.is_excluded(Path("generated/b.py"))
    assert not config.is_excluded(Path(".venv/c.py"))


def test_path_entries_keep_their_case(tmp_path: Path) -> None:
    # Rule codes are upper cased on the way in. Directory names must not be:
    # a directory called Generated is not the same as GENERATED.
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.qxlint]\nexclude = ["Vendor"]\nextend-exclude = ["Generated"]\n')
    config = load_config(path)
    assert config.exclude == ("Vendor",)
    assert config.extend_exclude == ("Generated",)
    assert config.is_excluded(Path("Generated/b.py"))
    assert not config.is_excluded(Path("generated/b.py"))


def test_extend_exclude_must_be_a_list(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.qxlint]\nextend-exclude = "vendor"\n')
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_config_reads_the_section(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        "[tool.qxlint]\n"
        'select = ["qxl1"]\n'
        'ignore = ["QXL103"]\n'
        "preview = true\n"
        'target-runtime = "0.48"\n'
        "[tool.qxlint.per-file-ignores]\n"
        '"notebooks/*" = ["QXL101"]\n'
    )
    config = load_config(path)
    assert config.select == ("QXL1",)
    assert config.ignore == ("QXL103",)
    assert config.preview is True
    assert config.target_runtime == "0.48"
    assert config.per_file_ignores == (("notebooks/*", ("QXL101",)),)


def test_load_config_without_the_section_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "x"\n')
    assert load_config(path).select == ()


def test_bad_config_type_raises(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.qxlint]\nselect = "QXL101"\n')
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.qxlint\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bare_noqa_suppresses_everything() -> None:
    noqa = parse_noqa("x = 1  # noqa\n")
    assert noqa.lines[1] == frozenset({ALL})
    assert noqa.suppresses(1, "QXL101")


def test_noqa_with_one_code() -> None:
    noqa = parse_noqa("x = 1  # noqa: QXL101\n")
    assert noqa.suppresses(1, "QXL101")
    assert not noqa.suppresses(1, "QXL103")


def test_noqa_with_several_codes() -> None:
    noqa = parse_noqa("x = 1  # noqa: QXL101, QXL103\n")
    assert noqa.suppresses(1, "QXL101")
    assert noqa.suppresses(1, "QXL103")


def test_noqa_codes_may_be_space_separated() -> None:
    noqa = parse_noqa("x = 1  # noqa: QXL101 QXL103\n")
    assert noqa.suppresses(1, "QXL103")


def test_noqa_is_case_insensitive() -> None:
    assert parse_noqa("x = 1  # NOQA: qxl101\n").suppresses(1, "QXL101")


def test_noqa_inside_a_string_is_not_a_comment() -> None:
    assert parse_noqa('x = "# noqa"\n').is_empty


def test_noqa_with_an_empty_code_list_falls_back_to_all() -> None:
    assert parse_noqa("x = 1  # noqa:\n").suppresses(1, "QXL999")


def test_noqa_on_an_unparsable_file_is_empty() -> None:
    assert parse_noqa("def f(\n").is_empty


@pytest.mark.parametrize("prefix", ["QXL", "QXL1", "QXL10", "QXL101"])
def test_a_noqa_code_is_a_prefix_like_flake8(prefix: str) -> None:
    # flake8 matches a noqa code by prefix, and so do qxlint's own --select and
    # --ignore. Exact matching here made the CLI and the flake8 plugin disagree
    # on the same file.
    assert parse_noqa(f"x = 1  # noqa: {prefix}\n").suppresses(1, "QXL101")


def test_a_prefix_does_not_reach_a_different_family() -> None:
    noqa = parse_noqa("x = 1  # noqa: QXL10\n")
    assert noqa.suppresses(1, "QXL101")
    assert not noqa.suppresses(1, "QXL201")


def test_an_unrelated_code_suppresses_nothing() -> None:
    assert not parse_noqa("x = 1  # noqa: E501\n").suppresses(1, "QXL101")


# Columns ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "byte_offset", "expected"),
    [
        ("x = 1", 0, 1),
        ("x = 1", 4, 5),
        ("é = 1", 3, 3),
        # Each alpha is two bytes, so `foo` starts at byte 9 and character 7.
        ("ααα = foo", 9, 7),
        ("ααα = foo", 6, 4),
        ("x", 99, 2),
    ],
)
def test_byte_offset_to_column(line: str, byte_offset: int, expected: int) -> None:
    assert byte_offset_to_column(line, byte_offset) == expected


def test_source_file_column_of_uses_characters_not_bytes() -> None:
    source = SourceFile("t.py", 'résultat = "x"\nprint(résultat)\n')
    # `résultat` inside print starts at character column 7 and byte column 7.
    assert source.column_of(2, 6) == 7
