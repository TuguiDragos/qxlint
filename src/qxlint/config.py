"""Configuration from ``[tool.qxlint]`` and the command line.

Precedence, highest first:

1. command line flags
2. ``[tool.qxlint]`` in the nearest ``pyproject.toml``
3. built in defaults

Rule selection is resolved in a fixed order so two runs never disagree:

1. start from every registered rule
2. ``select`` keeps only codes matching one of its prefixes; when ``select`` is
   empty the starting set is every default tier rule
3. a preview rule stays off unless ``preview`` is true or its exact code appears
   in ``select``
4. ``ignore`` removes codes matching one of its prefixes
5. ``per-file-ignores`` removes further codes for paths matching a glob

Command line ``--select`` and ``--ignore`` replace the configured lists rather
than extending them, so a flag can always narrow a noisy project.
"""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from qxlint.diagnostics import Tier
from qxlint.paths import is_regular_file
from qxlint.profile import (
    ProfileSource,
    SemanticProfile,
    VersionKnowledge,
    discover_profile,
    find_project_root,
    knowledge_from_text,
)

SECTION = "qxlint"
DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "build",
    "dist",
    "node_modules",
    ".ipynb_checkpoints",
)


class ConfigError(Exception):
    """Raised for an unusable configuration. Maps to exit code 2."""


@dataclass(frozen=True, slots=True)
class Config:
    """Effective settings for one run."""

    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    preview: bool = False
    per_file_ignores: tuple[tuple[str, tuple[str, ...]], ...] = ()
    exclude: tuple[str, ...] = DEFAULT_EXCLUDES
    extend_exclude: tuple[str, ...] = ()
    target_qiskit: str | None = None
    target_runtime: str | None = None
    source_path: Path | None = None
    root: Path | None = None

    def enabled_codes(self, registered: dict[str, Tier]) -> frozenset[str]:
        """Resolve the run wide rule set."""
        if self.select:
            chosen = {
                code
                for code in registered
                if any(code.startswith(prefix) for prefix in self.select)
            }
        else:
            chosen = {
                code
                for code, tier in registered.items()
                if tier is Tier.DEFAULT or (self.preview and tier is Tier.PREVIEW)
            }

        exact_select = set(self.select)
        chosen = {
            code
            for code in chosen
            if registered[code] is Tier.DEFAULT or self.preview or code in exact_select
        }
        return frozenset(
            code for code in chosen if not any(code.startswith(prefix) for prefix in self.ignore)
        )

    def ignored_for_path(self, path: str) -> frozenset[str]:
        """Extra ignore prefixes contributed by ``per-file-ignores``."""
        out: set[str] = set()
        normalised = path.replace("\\", "/")
        for pattern, codes in self.per_file_ignores:
            if fnmatch.fnmatch(normalised, pattern) or fnmatch.fnmatch(
                Path(normalised).name, pattern
            ):
                out.update(codes)
        return frozenset(out)

    def is_excluded(self, path: Path) -> bool:
        """Does an exclude entry cover this path, given relative to the scan root?

        A plain entry matches a path component, which is what makes `.venv`
        skip a whole tree wherever it sits. An entry holding a glob character
        is matched against the whole relative path as well, so `build/*` covers
        everything under it rather than silently matching nothing.
        """
        parts = path.parts
        as_component = set(parts)
        posix = path.as_posix()
        for entry in (*self.exclude, *self.extend_exclude):
            if entry in as_component:
                return True
            if _has_glob(entry) and (
                fnmatch.fnmatch(posix, entry) or any(fnmatch.fnmatch(part, entry) for part in parts)
            ):
                return True
        return False


_GLOB_CHARACTERS = frozenset("*?[")


def _has_glob(entry: str) -> bool:
    return any(character in _GLOB_CHARACTERS for character in entry)


def load_config(path: Path) -> Config:
    """Read ``[tool.qxlint]`` from a ``pyproject.toml``."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    tool = data.get("tool")
    section = tool.get(SECTION) if isinstance(tool, dict) else None
    if not isinstance(section, dict):
        return Config(source_path=path, root=path.parent)

    return Config(
        select=_str_tuple(section, "select", path),
        ignore=_str_tuple(section, "ignore", path),
        preview=_bool(section, "preview", path),
        per_file_ignores=_per_file_ignores(section, path),
        # `exclude` replaces the defaults, as it does in ruff and flake8, so a
        # project can deliberately scan a directory this list would skip.
        # `extend-exclude` is the additive form, which is what most projects
        # actually want: adding one entry should not silently bring `.venv` and
        # `node_modules` back into the run.
        exclude=_str_tuple(section, "exclude", path) or DEFAULT_EXCLUDES,
        extend_exclude=_str_tuple(section, "extend-exclude", path),
        target_qiskit=_opt_str(section, "target-qiskit", path),
        target_runtime=_opt_str(section, "target-runtime", path),
        source_path=path,
        root=path.parent,
    )


def apply_cli_overrides(
    config: Config,
    *,
    select: tuple[str, ...] | None,
    ignore: tuple[str, ...] | None,
    preview: bool,
    target_qiskit: str | None,
    target_runtime: str | None,
) -> Config:
    """Layer command line flags over a loaded config."""
    return replace(
        config,
        select=select if select is not None else config.select,
        ignore=ignore if ignore is not None else config.ignore,
        preview=preview or config.preview,
        target_qiskit=target_qiskit or config.target_qiskit,
        target_runtime=target_runtime or config.target_runtime,
    )


def resolve_profile(config: Config) -> SemanticProfile:
    """Build the semantic profile in the documented source order."""
    qiskit = VersionKnowledge()
    runtime = VersionKnowledge()

    if config.target_qiskit:
        qiskit = knowledge_from_text(config.target_qiskit, ProfileSource.CLI_FLAG)
    if config.target_runtime:
        runtime = knowledge_from_text(config.target_runtime, ProfileSource.CLI_FLAG)

    if (not qiskit.known or not runtime.known) and config.root is not None:
        discovered = discover_profile(config.root)
        if not qiskit.known:
            qiskit = discovered.qiskit
        if not runtime.known:
            runtime = discovered.qiskit_ibm_runtime

    return SemanticProfile(qiskit=qiskit, qiskit_ibm_runtime=runtime)


@dataclass
class ConfigCache:
    """Per directory config lookup, so a monorepo resolves each file correctly."""

    _by_root: dict[Path, Config] = field(default_factory=dict)
    _profiles: dict[tuple[Path, str, str], SemanticProfile] = field(default_factory=dict)
    override: Config | None = None

    def for_path(self, path: Path) -> Config:
        if self.override is not None:
            return self.override
        root = find_project_root(path.resolve())
        if root is None:
            return Config()
        if root not in self._by_root:
            manifest = root / "pyproject.toml"
            self._by_root[root] = (
                load_config(manifest) if is_regular_file(manifest) else Config(root=root)
            )
        return self._by_root[root]

    def profile_for(self, config: Config) -> SemanticProfile:
        """The same answer as resolve_profile, discovered once per root.

        Discovery parses pyproject.toml and uv.lock. Doing it per file made a
        scan of a project with a large lock file spend most of its time there.
        The result depends on nothing but these three values.
        """
        if config.root is None:
            return resolve_profile(config)
        key = (config.root, config.target_qiskit or "", config.target_runtime or "")
        cached = self._profiles.get(key)
        if cached is None:
            cached = resolve_profile(config)
            self._profiles[key] = cached
        return cached


# Rule codes are matched case insensitively, so they are normalised on the way
# in. Path components are not: a directory named `Build` is not `build`.
CODE_KEYS = frozenset({"select", "ignore"})


def _str_tuple(section: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
    value = section.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{path}: [tool.{SECTION}] {key} must be a list of strings")
    if key in CODE_KEYS:
        return tuple(item.strip().upper() for item in value)
    return tuple(value)


def _bool(section: dict[str, object], key: str, path: Path) -> bool:
    value = section.get(key, False)
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: [tool.{SECTION}] {key} must be a boolean")
    return value


def _opt_str(section: dict[str, object], key: str, path: Path) -> str | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path}: [tool.{SECTION}] {key} must be a string")
    return value


def _per_file_ignores(
    section: dict[str, object], path: Path
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    value = section.get("per-file-ignores")
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: [tool.{SECTION}] per-file-ignores must be a table")
    out: list[tuple[str, tuple[str, ...]]] = []
    for pattern, codes in value.items():
        if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
            raise ConfigError(
                f"{path}: [tool.{SECTION}] per-file-ignores['{pattern}'] must be a list of strings"
            )
        out.append((pattern, tuple(code.strip().upper() for code in codes)))
    return tuple(out)
