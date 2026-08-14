"""Engine A: read a file, analyse it, filter the findings.

Never imports and never executes the code under analysis.
"""

from __future__ import annotations

import ast
import tokenize
import warnings
from collections.abc import Callable
from pathlib import Path

from qxlint.config import Config
from qxlint.diagnostics import Finding, NotebookLocation, Severity, SourceLocation, Tier
from qxlint.noqa import NoqaMap, parse_noqa
from qxlint.notebook import Notebook, NotebookError, read_notebook
from qxlint.paths import exists_but_is_not_regular, is_directory
from qxlint.profile import SemanticProfile
from qxlint.registry import build_ruleset
from qxlint.rules.base import RuleContext, RuleSet
from qxlint.rules.qxl000_unparsable import CODE as UNPARSABLE
from qxlint.semantics.analyzer import Analyzer
from qxlint.semantics.state import State
from qxlint.semantics.values import UNKNOWN
from qxlint.source import SourceFile, too_deep_to_parse

PYTHON_SUFFIX = ".py"
NOTEBOOK_SUFFIX = ".ipynb"
SUFFIXES = (PYTHON_SUFFIX, NOTEBOOK_SUFFIX)


def read_source(path: Path) -> str:
    """Decode using the file's own PEP 263 declaration, not a fixed encoding."""
    with tokenize.open(path) as handle:
        return handle.read()


def parse_module(text: str, filename: str) -> ast.Module:
    """Parse a module, keeping compiler warnings out of the linter's output.

    ``ast.parse`` reports an invalid escape sequence as a SyntaxWarning on
    stderr. qxlint is only reading the file, so surfacing that would be noise in
    the middle of its own results.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return ast.parse(text, filename=filename)
        except RecursionError as exc:
            raise too_deep_to_parse(filename) from exc


def _active_codes(config: Config, enabled: frozenset[str], shown: str) -> frozenset[str]:
    ignored = config.ignored_for_path(shown)
    return frozenset(
        code for code in enabled if not any(code.startswith(prefix) for prefix in ignored)
    )


def analyse_path(
    path: Path,
    *,
    config: Config,
    profile: SemanticProfile,
    enabled: frozenset[str],
    display_path: str | None = None,
) -> list[Finding]:
    """Analyse one file and return the findings that survive filtering."""
    shown = display_path if display_path is not None else str(path)
    active = _active_codes(config, enabled, shown)

    if exists_but_is_not_regular(path):
        location = SourceLocation(shown, 1, 1)
        return _filter([_unparsable("not a regular file", location)], active, {})

    if path.suffix == NOTEBOOK_SUFFIX:
        findings, noqa_by_cell = _analyse_notebook(path, shown, profile, active)
        return _filter(findings, active, noqa_by_cell)

    findings, noqa = _analyse_python(path, shown, profile, active)
    return _filter(findings, active, {None: noqa})


def analyse_source(
    text: str,
    path: Path,
    *,
    config: Config,
    profile: SemanticProfile,
    enabled: frozenset[str],
    display_path: str | None = None,
) -> list[Finding]:
    """Analyse source held in memory, as if it had been read from ``path``.

    An editor buffer is what the user is looking at, and it is not what is on
    disk until they save. ``path`` decides the suffix and the configuration, the
    text decides everything else.
    """
    shown = display_path if display_path is not None else str(path)
    active = _active_codes(config, enabled, shown)

    if path.suffix == NOTEBOOK_SUFFIX:
        findings, noqa_by_cell = _notebook_from_text(text, shown, profile, active)
        return _filter(findings, active, noqa_by_cell)

    findings, noqa = _python_from_text(text, shown, profile, active)
    return _filter(findings, active, {None: noqa})


def analyse_text(
    text: str,
    *,
    display_path: str,
    profile: SemanticProfile,
    enabled: frozenset[str],
) -> list[Finding]:
    """Analyse a string. Used by the flake8 plugin and by the tests."""
    findings: list[Finding] = []
    source = SourceFile(path=display_path, text=text)
    try:
        tree = parse_module(text, display_path)
    except SyntaxError as exc:
        return [_syntax_finding(exc, source)]
    _run(tree, source, profile, enabled, findings.append)
    return _filter(findings, enabled, {None: parse_noqa(text)})


def _analyse_python(
    path: Path, shown: str, profile: SemanticProfile, enabled: frozenset[str]
) -> tuple[list[Finding], NoqaMap]:
    try:
        text = read_source(path)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        location = SourceLocation(shown, 1, 1)
        return [_unparsable(f"cannot read file: {exc}", location)], NoqaMap({})
    return _python_from_text(text, shown, profile, enabled)


def _python_from_text(
    text: str, shown: str, profile: SemanticProfile, enabled: frozenset[str]
) -> tuple[list[Finding], NoqaMap]:
    source = SourceFile(path=shown, text=text)
    try:
        tree = parse_module(text, shown)
    except SyntaxError as exc:
        return [_syntax_finding(exc, source)], parse_noqa(text)

    findings: list[Finding] = []
    _run(tree, source, profile, enabled, findings.append)
    return findings, parse_noqa(text)


def _analyse_notebook(
    path: Path, shown: str, profile: SemanticProfile, enabled: frozenset[str]
) -> tuple[list[Finding], dict[int | None, NoqaMap]]:
    try:
        notebook = read_notebook(path)
    except NotebookError as exc:
        location = SourceLocation(shown, 1, 1)
        return [_unparsable(str(exc), location)], {}
    return _notebook_findings(notebook, shown, profile, enabled)


def _notebook_from_text(
    text: str, shown: str, profile: SemanticProfile, enabled: frozenset[str]
) -> tuple[list[Finding], dict[int | None, NoqaMap]]:
    from qxlint.notebook import parse_notebook_text

    try:
        notebook = parse_notebook_text(shown, text)
    except NotebookError as exc:
        location = SourceLocation(shown, 1, 1)
        return [_unparsable(str(exc), location)], {}
    return _notebook_findings(notebook, shown, profile, enabled)


def _notebook_findings(
    notebook: Notebook, shown: str, profile: SemanticProfile, enabled: frozenset[str]
) -> tuple[list[Finding], dict[int | None, NoqaMap]]:
    from qxlint.notebook import parse_cell

    findings: list[Finding] = []
    noqa_by_cell: dict[int | None, NoqaMap] = {}
    ruleset = build_ruleset(enabled)
    state = State()
    analyzer: Analyzer | None = None

    for cell in notebook.cells:
        source = SourceFile(
            path=shown,
            text=cell.text,
            cell_index=cell.index,
            column_offset=cell.column_offset,
        )
        noqa_by_cell[cell.index] = parse_noqa(cell.original)
        ctx = RuleContext(source=source, profile=profile, emit=findings.append)

        try:
            tree = parse_cell(cell.text, filename=shown)
        except SyntaxError as exc:
            findings.append(_syntax_finding(exc, source))
            # A cell that does not parse may have bound or mutated anything, so
            # later cells continue from an unknown state rather than a stale one.
            for name in list(state.env):
                state.bind(name, UNKNOWN)
            state.widen_all()
            continue

        if analyzer is None:
            analyzer = Analyzer(source, ruleset, ctx)
        analyzer.source = source
        analyzer.ctx = ctx
        analyzer.run(tree, state)

    return findings, noqa_by_cell


def _run(
    tree: ast.Module,
    source: SourceFile,
    profile: SemanticProfile,
    enabled: frozenset[str],
    emit: Callable[[Finding], None],
) -> None:
    ruleset: RuleSet = build_ruleset(enabled)
    ctx = RuleContext(source=source, profile=profile, emit=emit)
    Analyzer(source, ruleset, ctx).run(tree, State())


def _syntax_finding(exc: SyntaxError, source: SourceFile) -> Finding:
    line = exc.lineno or 1
    column = exc.offset or 1
    if source.cell_index is None:
        location: SourceLocation | NotebookLocation = SourceLocation(source.path, line, column)
    else:
        location = NotebookLocation(source.path, source.cell_index, line, column)
    reason = exc.msg or "invalid syntax"
    return _unparsable(f"cannot parse: {reason}", location)


def _unparsable(message: str, location: SourceLocation | NotebookLocation) -> Finding:
    return Finding(
        rule=UNPARSABLE,
        message=message,
        location=location,
        severity=Severity.ERROR,
        tier=Tier.DEFAULT,
    )


def _identity(finding: Finding) -> tuple[object, ...]:
    """Everything about a finding that a reader can see.

    Two findings equal under this are one problem reported twice, so only one
    is kept. Every user visible field is included, so a difference in any of
    them, including the column, keeps both.
    """
    return (
        finding.rule,
        finding.message,
        finding.location,
        finding.severity,
        finding.tier,
        finding.fix_hint,
        tuple(sorted(finding.context.items())),
    )


def _filter(
    findings: list[Finding],
    enabled: frozenset[str],
    noqa_by_cell: dict[int | None, NoqaMap],
) -> list[Finding]:
    """Drop disabled rules and suppressed lines, then collapse repeats.

    A loop body is walked twice to reach a fixed point, and rules emit on every
    walk, so a finding inside two nested loops arrived here four times. The
    repeat is an artefact of the walk, not of the code being analysed.

    Deduplication happens here rather than by emitting on the last walk only,
    because the two walks do not see the same state and the earlier one is not
    redundant. In this loop the circuit genuinely has no measurement on the
    first iteration, and only the first walk can see that:

        for i in range(3):
            sampler.run([qc])
            qc.measure_all()
    """
    kept: list[Finding] = []
    seen: set[tuple[object, ...]] = set()
    for finding in findings:
        if finding.rule not in enabled:
            continue
        cell = (
            finding.location.cell_index if isinstance(finding.location, NotebookLocation) else None
        )
        noqa = noqa_by_cell.get(cell)
        line = getattr(finding.location, "line", None)
        if noqa is not None and line is not None and noqa.suppresses(line, finding.rule):
            continue
        identity = _identity(finding)
        if identity in seen:
            continue
        seen.add(identity)
        kept.append(finding)
    kept.sort(key=Finding.sort_key)
    return kept


def discover(paths: list[Path], config: Config) -> list[Path]:
    """Expand directories into the files qxlint analyses."""
    out: list[Path] = []
    seen: set[Path] = set()
    for entry in paths:
        if is_directory(entry):
            for suffix in SUFFIXES:
                for found in sorted(entry.rglob(f"*{suffix}")):
                    if config.is_excluded(found.relative_to(entry)):
                        continue
                    if found in seen:
                        continue
                    seen.add(found)
                    out.append(found)
        elif entry.suffix in SUFFIXES and entry not in seen:
            seen.add(entry)
            out.append(entry)
    return out
