"""SemanticProfile: which Qiskit and Runtime versions the analysed project targets.

A version specifier is not a version. ``>=0.38,<0.43`` spans releases where a
symbol is fine, deprecated, and removed, so a rule cannot simply compare. Every
version dependent rule asks for an :class:`Applicability` instead, and fires only
on :attr:`Applicability.ALWAYS`.

The linter never inspects its own installed Qiskit for this. The version in the
linter environment is not the version the analysed project targets.
"""

from __future__ import annotations

import enum
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from qxlint.paths import is_directory, is_regular_file

QISKIT = "qiskit"
QISKIT_IBM_RUNTIME = "qiskit-ibm-runtime"

_HUGE = Version("9999.0.0")
_TINY = Version("0.0.0")


class Applicability(enum.Enum):
    """Whether a version predicate holds across every version the target allows."""

    ALWAYS = "always"
    NEVER = "never"
    MAYBE = "maybe"
    UNKNOWN = "unknown"


class ProfileSource(enum.Enum):
    """Where a version came from. Earlier members win."""

    CLI_FLAG = "cli-flag"
    CONFIG = "config"
    PROJECT_DEPENDENCIES = "project-dependencies"
    LOCK_FILE = "lock-file"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class VersionKnowledge:
    """What is known about one package's target version."""

    exact: Version | None = None
    specifier: SpecifierSet | None = None
    source: ProfileSource = ProfileSource.NONE
    origin: str | None = None

    @property
    def known(self) -> bool:
        return self.exact is not None or self.specifier is not None

    def describe(self) -> str:
        if self.exact is not None:
            return str(self.exact)
        if self.specifier is not None:
            return str(self.specifier)
        return "unknown"

    def at_least(self, threshold: str) -> Applicability:
        """Does every allowed version satisfy ``>= threshold``?"""
        try:
            target = Version(threshold)
        except InvalidVersion:
            return Applicability.UNKNOWN

        if self.exact is not None:
            return Applicability.ALWAYS if self.exact >= target else Applicability.NEVER
        if self.specifier is None:
            return Applicability.UNKNOWN

        allows_below, allows_at_or_above = _probe(self.specifier, target)
        if allows_below and allows_at_or_above:
            return Applicability.MAYBE
        if allows_at_or_above:
            return Applicability.ALWAYS
        if allows_below:
            return Applicability.NEVER
        return Applicability.UNKNOWN


def _probe(specifier: SpecifierSet, target: Version) -> tuple[bool, bool]:
    """Sample the version space around a specifier to see which side it allows.

    ``packaging`` cannot intersect a specifier set with an open range, so the set
    is probed with versions drawn from its own bounds plus the threshold. Every
    bound that matters appears in one of the two sets, so a specifier that allows
    something on a side has an allowed probe on that side.
    """
    candidates = _candidates(specifier, target)
    allows_below = False
    allows_at_or_above = False
    for candidate in candidates:
        if not specifier.contains(candidate, prereleases=True):
            continue
        if candidate < target:
            allows_below = True
        else:
            allows_at_or_above = True
        if allows_below and allows_at_or_above:
            break
    return allows_below, allows_at_or_above


def _candidates(specifier: SpecifierSet, target: Version) -> list[Version]:
    """Probe versions: every mentioned bound, its neighbours, and the extremes."""
    seeds: list[Version] = [_TINY, _HUGE, target]
    for spec in specifier:
        try:
            seeds.append(Version(spec.version.rstrip(".*")))
        except InvalidVersion:
            continue

    out: list[Version] = []
    for seed in seeds:
        for neighbour in _neighbours(seed):
            if neighbour not in out:
                out.append(neighbour)
    return out


def _neighbours(version: Version) -> list[Version]:
    """A version plus the closest points on either side of it."""
    release = [*version.release, 0, 0, 0]
    major, minor, micro = release[0], release[1], release[2]
    out = [version, Version(f"{major}.{minor}.{micro}")]
    out.append(Version(f"{major}.{minor}.{micro + 1}"))
    out.append(Version(f"{major}.{minor + 1}.0"))
    out.append(Version(f"{major + 1}.0.0"))
    if micro > 0:
        out.append(Version(f"{major}.{minor}.{micro - 1}"))
    elif minor > 0:
        out.append(Version(f"{major}.{minor - 1}.999999"))
    elif major > 0:
        out.append(Version(f"{major - 1}.999999.999999"))
    return out


@dataclass(frozen=True, slots=True)
class SemanticProfile:
    """Target versions for the analysed project."""

    qiskit: VersionKnowledge = VersionKnowledge()
    qiskit_ibm_runtime: VersionKnowledge = VersionKnowledge()

    @property
    def source(self) -> ProfileSource:
        for knowledge in (self.qiskit, self.qiskit_ibm_runtime):
            if knowledge.known:
                return knowledge.source
        return ProfileSource.NONE

    def runtime_at_least(self, threshold: str) -> Applicability:
        return self.qiskit_ibm_runtime.at_least(threshold)

    def qiskit_at_least(self, threshold: str) -> Applicability:
        return self.qiskit.at_least(threshold)


def knowledge_from_text(
    text: str, source: ProfileSource, origin: str | None = None
) -> VersionKnowledge:
    """Parse a CLI or config value that may be an exact version or a specifier."""
    value = text.strip()
    if not value:
        return VersionKnowledge(source=ProfileSource.NONE)
    if value[0] in "<>=!~^":
        try:
            return VersionKnowledge(specifier=SpecifierSet(value), source=source, origin=origin)
        except InvalidSpecifier:
            return VersionKnowledge(source=ProfileSource.NONE)
    try:
        return VersionKnowledge(exact=Version(value), source=source, origin=origin)
    except InvalidVersion:
        try:
            return VersionKnowledge(specifier=SpecifierSet(value), source=source, origin=origin)
        except InvalidSpecifier:
            return VersionKnowledge(source=ProfileSource.NONE)


# Files that mark a project root when no pyproject.toml is above the path.
# Order matters only for reporting; any of them anchors a root.
FALLBACK_MANIFESTS = ("requirements.txt", "setup.cfg", "setup.py")


def find_project_root(start: Path) -> Path | None:
    """Nearest ancestor directory holding a project manifest.

    A pyproject.toml always wins, wherever it sits, because that is where the
    configuration lives. Only when there is none does a requirements.txt or a
    setup file anchor the root, so a project that never adopted pyproject still
    gets a target version instead of silence.

    Resolution is per file, so each package in a monorepo gets its own profile.
    A directory the user cannot traverse is a directory with no manifest, on
    every supported version. See :mod:`qxlint.paths`.
    """
    current = start if is_directory(start) else start.parent
    chain = [current, *current.parents]
    for candidate in chain:
        if is_regular_file(candidate / "pyproject.toml"):
            return candidate
    for candidate in chain:
        if any(is_regular_file(candidate / name) for name in FALLBACK_MANIFESTS):
            return candidate
    return None


def discover_profile(root: Path) -> SemanticProfile:
    """Read target versions from a project root.

    Three sources, most authoritative first: declared dependencies in
    ``pyproject.toml``, an unambiguous pin in ``uv.lock``, then
    ``requirements.txt``. A multi environment lock is still out of scope,
    because resolving one correctly means writing a dependency resolver.
    """
    declared = _from_pyproject(root / "pyproject.toml")
    locked = _from_uv_lock(root / "uv.lock")
    listed = _from_requirements(root / "requirements.txt")

    def pick(name: str) -> VersionKnowledge:
        return declared.get(name) or locked.get(name) or listed.get(name) or VersionKnowledge()

    return SemanticProfile(qiskit=pick(QISKIT), qiskit_ibm_runtime=pick(QISKIT_IBM_RUNTIME))


# A requirements file that includes others can chain; stop well before a cycle
# would matter, and never leave the tree the first file came from.
MAX_REQUIREMENTS_DEPTH = 8


def _requirement_lines(path: Path, seen: set[Path], depth: int) -> list[str]:
    """Plain requirement lines, following ``-r`` includes but not option lines."""
    resolved = path.resolve() if is_regular_file(path) else path
    if depth > MAX_REQUIREMENTS_DEPTH or resolved in seen or not is_regular_file(path):
        return []
    seen.add(resolved)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    out: list[str] = []
    for raw in text.replace("\\\n", " ").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            for flag in ("-r", "--requirement"):
                prefix = f"{flag} "
                if line.startswith(prefix) or line.startswith(f"{flag}="):
                    included = line[len(flag) :].lstrip("= ").strip()
                    if included:
                        out.extend(_requirement_lines(path.parent / included, seen, depth + 1))
                    break
            continue
        out.append(line)
    return out


def _from_requirements(path: Path) -> dict[str, VersionKnowledge]:
    """Read declared versions from a requirements file."""
    lines = _requirement_lines(path, set(), 0)
    if not lines:
        return {}

    collected: dict[str, list[Requirement]] = {}
    for raw in lines:
        try:
            requirement = Requirement(raw)
        except InvalidRequirement:
            continue
        name = canonicalize_name(requirement.name)
        if name in (QISKIT, QISKIT_IBM_RUNTIME):
            collected.setdefault(name, []).append(requirement)

    out: dict[str, VersionKnowledge] = {}
    for package, requirements in collected.items():
        knowledge = _combine_requirements(requirements, str(path))
        if knowledge is not None:
            out[package] = knowledge
    return out


def _from_pyproject(path: Path) -> dict[str, VersionKnowledge]:
    data = _load_toml(path)
    if data is None:
        return {}

    requirement_strings: list[str] = []
    project = data.get("project", {})
    if isinstance(project, dict):
        requirement_strings.extend(_as_str_list(project.get("dependencies")))
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for extra in optional.values():
                requirement_strings.extend(_as_str_list(extra))
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for group in groups.values():
            requirement_strings.extend(_as_str_list(group))

    collected: dict[str, list[Requirement]] = {}
    for raw in requirement_strings:
        try:
            requirement = Requirement(raw)
        except InvalidRequirement:
            continue
        name = canonicalize_name(requirement.name)
        if name in (QISKIT, QISKIT_IBM_RUNTIME):
            collected.setdefault(name, []).append(requirement)

    out: dict[str, VersionKnowledge] = {}
    for package, requirements in collected.items():
        knowledge = _combine_requirements(requirements, str(path))
        if knowledge is not None:
            out[package] = knowledge
    return out


def _combine_requirements(requirements: list[Requirement], origin: str) -> VersionKnowledge | None:
    """Intersect declared specifiers, giving up when a marker makes them conditional."""
    if any(requirement.marker is not None for requirement in requirements):
        return None
    if any(requirement.url is not None for requirement in requirements):
        return None
    combined = SpecifierSet()
    for requirement in requirements:
        combined &= requirement.specifier
    if not str(combined):
        return None
    return VersionKnowledge(
        specifier=combined,
        source=ProfileSource.PROJECT_DEPENDENCIES,
        origin=origin,
    )


def _from_uv_lock(path: Path) -> dict[str, VersionKnowledge]:
    """Read a pin from ``uv.lock``, only when the package resolves to one version."""
    data = _load_toml(path)
    if data is None:
        return {}
    packages = data.get("package")
    if not isinstance(packages, list):
        return {}

    versions: dict[str, set[str]] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        raw_name = entry.get("name")
        raw_version = entry.get("version")
        if not isinstance(raw_name, str) or not isinstance(raw_version, str):
            continue
        name = canonicalize_name(raw_name)
        if name in (QISKIT, QISKIT_IBM_RUNTIME):
            versions.setdefault(name, set()).add(raw_version)

    out: dict[str, VersionKnowledge] = {}
    for package, found in versions.items():
        if len(found) != 1:
            continue
        try:
            version = Version(next(iter(found)))
        except InvalidVersion:
            continue
        out[package] = VersionKnowledge(
            exact=version, source=ProfileSource.LOCK_FILE, origin=str(path)
        )
    return out


def _load_toml(path: Path) -> dict[str, object] | None:
    if not is_regular_file(path):
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
