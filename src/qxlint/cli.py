"""Command line interface.

Exit codes:

* ``0`` no findings
* ``1`` findings were reported, including QXL000 for a file that cannot be parsed
* ``2`` qxlint could not run: bad usage, unreadable or invalid configuration,
  a path that does not exist, or an unexpected internal error

A file that fails to parse is a finding, not an internal error. The distinction
is what makes a non-zero exit meaningful in CI.

An unexpected error on one file does not end the run. The remaining files are
still analysed and their findings are still printed, the failure is named on
stderr, and the exit code is 2 because that one file really was not analysed.
"""

from __future__ import annotations

import argparse
import sys
from difflib import get_close_matches
from pathlib import Path

from qxlint import __version__
from qxlint.baseline import BaselineError, build, load, serialise
from qxlint.config import (
    SECTION,
    Config,
    ConfigCache,
    ConfigError,
    apply_cli_overrides,
    resolve_profile,
)
from qxlint.diagnostics import Finding
from qxlint.engine import SUFFIXES, analyse_path, analyse_source, discover
from qxlint.output import FORMATS
from qxlint.output.explain import render_listing, render_rule
from qxlint.output.palette import Depth, detect_depth
from qxlint.output.statistics import render_statistics, render_statistics_json
from qxlint.paths import exists as path_exists
from qxlint.paths import is_directory
from qxlint.profile import ProfileSource, knowledge_from_text
from qxlint.registry import all_meta, source_reachable, tiers

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qxlint",
        description="Deterministic static checks for Qiskit Primitives V2 workflows.",
    )
    # No default here on purpose: an empty list has to stay distinguishable
    # from an explicit ".", so --stdin-filename can reject paths it cannot use.
    parser.add_argument("paths", nargs="*", help="files or directories, default '.'")
    parser.add_argument("--version", action="version", version=f"qxlint {__version__}")
    parser.add_argument("--select", help="comma separated rule codes or prefixes to run")
    parser.add_argument("--ignore", help="comma separated rule codes or prefixes to skip")
    parser.add_argument(
        "--target-qiskit",
        metavar="SPEC",
        help="target Qiskit version or specifier, for example 2.5 or '>=2.0'",
    )
    parser.add_argument(
        "--target-runtime",
        metavar="SPEC",
        help="target qiskit-ibm-runtime version or specifier",
    )
    parser.add_argument("--config", type=Path, help="path to a pyproject.toml to use")
    parser.add_argument(
        "--stdin-filename",
        metavar="PATH",
        help=(
            "read the source from stdin and report it as PATH; the file itself "
            "is never opened, so an editor can check a buffer it has not saved"
        ),
    )
    parser.add_argument(
        "--format", dest="fmt", choices=sorted(FORMATS), default="text", help="output format"
    )
    parser.add_argument("--no-color", action="store_true", help="never colour the output")
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="summarise findings per rule instead of listing them",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        type=Path,
        help=(
            "suppress the findings recorded in PATH, so a gate reports only "
            "what a project has not already accepted"
        ),
    )
    parser.add_argument(
        "--baseline-write",
        metavar="PATH",
        type=Path,
        help="write the current findings to PATH as a baseline and report nothing",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="print every rule with its severity and tier, and exit",
    )
    parser.add_argument(
        "--explain",
        metavar="CODE",
        help="print what one rule checks and why it exists, and exit",
    )
    parser.add_argument(
        "--show-profile",
        action="store_true",
        help="print the resolved target versions and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except (ConfigError, BaselineError) as exc:
        print(f"qxlint: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover
        return EXIT_ERROR
    except Exception as exc:
        print(f"qxlint: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _run(args: argparse.Namespace) -> int:
    if args.list_rules:
        print(render_listing())
        return EXIT_OK
    if args.explain is not None:
        return _explain(args.explain)
    if args.stdin_filename is not None:
        return _run_stdin(args)

    paths = [Path(entry) for entry in (args.paths or ["."])]
    for path in paths:
        if not path_exists(path):
            print(f"qxlint: path does not exist: {path}", file=sys.stderr)
            return EXIT_ERROR

    cache = ConfigCache()
    if args.config is not None:
        from qxlint.config import load_config

        cache.override = load_config(args.config)

    _check_flags(args)
    _check_baseline_flags(args)
    _warn_about_the_root_config(cache.for_path(paths[0]), args)

    if args.show_profile:
        return _print_profile(paths, cache, args)

    if args.statistics and args.fmt == "sarif":
        print(
            "qxlint: --statistics has no SARIF form; use --format text or json",
            file=sys.stderr,
        )
        return EXIT_ERROR

    registered = tiers()
    findings: list[Finding] = []
    targets = _targets(paths, cache)
    failed = False

    for path in targets:
        config = _effective(cache.for_path(path), args)
        profile = cache.profile_for(config)
        enabled = config.enabled_codes(registered)
        try:
            findings.extend(analyse_path(path, config=config, profile=profile, enabled=enabled))
        except Exception as exc:
            # One file qxlint cannot handle must not cost the whole run. Every
            # failure the engine knows about is already a QXL000 finding; this
            # is the net under the ones it does not, and it names the file so
            # the report is actionable. The run still ends in exit 2, because
            # that file really was not analysed.
            print(
                f"qxlint: internal error analysing {path}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failed = True

    if not targets:
        # Zero files analysed and zero findings look identical to a clean run,
        # and take a CI gate green having checked nothing.
        print("qxlint: no Python or notebook files were analysed", file=sys.stderr)
    return _report(findings, args, total_files=len(targets), failed=failed)


def _report(
    findings: list[Finding], args: argparse.Namespace, *, total_files: int, failed: bool
) -> int:
    findings.sort(key=Finding.sort_key)

    if args.baseline_write is not None:
        return _write_baseline(findings, args.baseline_write, failed=failed)
    if args.baseline is not None:
        findings = _suppress(findings, args.baseline)
    depth = detect_depth(sys.stdout, no_color=args.no_color)

    if args.statistics:
        rendered = _render_statistics(findings, args.fmt, depth, total_files)
    else:
        rendered = FORMATS[args.fmt](findings, colour=depth is not Depth.NONE)

    if rendered:
        print(rendered)
    if failed:
        return EXIT_ERROR
    return EXIT_FINDINGS if findings else EXIT_OK


def _explain(code: str) -> int:
    """Print one rule, or name the closest codes when there is no such rule."""
    wanted = code.strip().upper()
    for meta in all_meta():
        if meta.code == wanted:
            print(render_rule(meta))
            return EXIT_OK
    known = [meta.code for meta in all_meta()]
    close = get_close_matches(wanted, known, n=3, cutoff=0.5)
    if len(close) > 1:
        close = [", ".join(close[:-1]) + " or " + close[-1]]
    suggestion = f", did you mean {close[0]}" if close else ""
    raise ConfigError(f"--explain: no rule {code!r}{suggestion}. See --list-rules")


def _write_baseline(findings: list[Finding], path: Path, *, failed: bool) -> int:
    """Record the current findings and report none of them.

    Exit is 0 even though findings were found: the run did what it was asked to
    do. A file qxlint could not analyse still ends in 2, because a baseline
    written from an incomplete run would silently accept whatever that file
    holds.
    """
    try:
        path.write_text(serialise(build(findings), tool_version=__version__), encoding="utf-8")
    except OSError as exc:
        raise BaselineError(f"cannot write baseline {path}: {exc}") from exc
    print(f"qxlint: wrote {len(findings)} findings to {path}", file=sys.stderr)
    return EXIT_ERROR if failed else EXIT_OK


def _suppress(findings: list[Finding], path: Path) -> list[Finding]:
    remaining, stale = load(path).filter(findings)
    if stale:
        # Not a failure: code that fixed an accepted finding is the point. It is
        # reported so the file can be regenerated rather than growing forever.
        print(
            f"qxlint: baseline {path}: {stale} recorded findings no longer occur, "
            "rewrite it with --baseline-write",
            file=sys.stderr,
        )
    return remaining


def _run_stdin(args: argparse.Namespace) -> int:
    """Analyse a buffer handed over on stdin.

    The path is metadata: it selects the configuration and decides whether the
    text is Python or a notebook. Nothing on disk is read, so this works on a
    file that has never been saved.
    """
    if args.paths:
        print(
            "qxlint: --stdin-filename reads the source from stdin, so no paths may be given",
            file=sys.stderr,
        )
        return EXIT_ERROR

    shown = args.stdin_filename
    path = Path(shown)
    if path.suffix not in SUFFIXES:
        print(
            f"qxlint: --stdin-filename: expected a {' or a '.join(SUFFIXES)} path, got {shown}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    cache = ConfigCache()
    if args.config is not None:
        from qxlint.config import load_config

        cache.override = load_config(args.config)

    _check_flags(args)
    _check_baseline_flags(args)
    directory = path.parent if str(path.parent) else Path()
    # The file's own config, not the effective one: a stale entry has to be
    # blamed on the file it is in, and a bad CLI flag is already reported by
    # _check_flags.
    _warn_about_the_root_config(cache.for_path(directory), args)
    config = _effective(cache.for_path(directory), args)

    if args.show_profile:
        return _print_profile([directory], cache, args)
    if args.statistics and args.fmt == "sarif":
        print(
            "qxlint: --statistics has no SARIF form; use --format text or json",
            file=sys.stderr,
        )
        return EXIT_ERROR

    # Decoded here rather than through sys.stdin, whose encoding follows the
    # locale. An editor buffer arrives as UTF-8 whatever the locale says.
    try:
        text = sys.stdin.buffer.read().decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"qxlint: --stdin-filename: input is not valid UTF-8: {exc}", file=sys.stderr)
        return EXIT_ERROR

    profile = resolve_profile(config)
    enabled = config.enabled_codes(tiers())
    findings = analyse_source(text, path, config=config, profile=profile, enabled=enabled)
    return _report(findings, args, total_files=1, failed=False)


def _render_statistics(findings: list[Finding], fmt: str, depth: Depth, total_files: int) -> str:
    """Summary view. Exit codes are unaffected: findings still mean exit 1."""
    if fmt == "json":
        return render_statistics_json(findings, total_files=total_files)
    return render_statistics(findings, depth=depth, stream=sys.stdout, total_files=total_files)


def _targets(paths: list[Path], cache: ConfigCache) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        config = cache.for_path(path if is_directory(path) else path.parent)
        for found in discover([path], config):
            if found not in seen:
                seen.add(found)
                out.append(found)
    return out


def _effective(config: Config, args: argparse.Namespace) -> Config:
    return apply_cli_overrides(
        config,
        select=_codes(args.select),
        ignore=_codes(args.ignore),
        preview=False,
        target_qiskit=args.target_qiskit,
        target_runtime=args.target_runtime,
    )


def _codes(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(part.strip().upper() for part in value.split(",") if part.strip())


def _check_baseline_flags(args: argparse.Namespace) -> None:
    """Reject baseline flag combinations that cannot do what they say."""
    if args.baseline is not None and args.baseline_write is not None:
        raise ConfigError(
            "--baseline and --baseline-write cannot be combined: one reads the "
            "accepted findings, the other replaces them"
        )
    if args.baseline_write is not None and args.stdin_filename is not None:
        raise ConfigError(
            "--baseline-write needs the whole project, so it cannot be combined "
            "with --stdin-filename, which analyses one buffer"
        )
    if args.baseline is not None and not path_exists(args.baseline):
        # Silently treating a missing baseline as empty would report every
        # accepted finding again and read as a regression in the code.
        raise ConfigError(f"--baseline: path does not exist: {args.baseline}")


def _check_flags(args: argparse.Namespace) -> None:
    """Reject a flag value that cannot do what it says.

    ``--select QXL013`` matches no rule, so every rule is off and the run reports
    nothing. That reads as a clean project and takes a CI gate green without
    having checked anything, which is why it is an error rather than a warning.
    A version that is not a version disables a version gated rule the same way.

    ``--ignore`` stays a warning on purpose: an ignore that matches nothing
    removes nothing, so it cannot make a run wrongly clean.
    """
    registered = tiers()
    selected = _codes(args.select)
    for code in selected or ():
        if not any(known.startswith(code) for known in registered):
            raise ConfigError(f"--select: no rule matches {code!r}")

    _reject_a_circuit_only_selection(selected or (), "--select")

    for code in _codes(args.ignore) or ():
        if not any(known.startswith(code) for known in registered):
            print(f"qxlint: --ignore: no rule matches {code!r}", file=sys.stderr)

    for flag, value in (
        ("--target-qiskit", args.target_qiskit),
        ("--target-runtime", args.target_runtime),
    ):
        if value and not knowledge_from_text(value, ProfileSource.CLI_FLAG).known:
            raise ConfigError(f"{flag}: {value!r} is not a version or a specifier")


def _reject_a_circuit_only_selection(selected: tuple[str, ...], spelling: str) -> None:
    """A selection that can only match circuit rules reports nothing, ever.

    QXL300 to QXL303 read an in-memory circuit, so a run over files cannot reach
    them however they are selected. Selecting only those produces an empty,
    exit 0 run on a project that really does have findings, which is the one
    result a gate must never give. The flag spelling has always been an error;
    the `[tool.qxlint]` spelling used to be silent, which made it the easier way
    to reach the failure.
    """
    if not selected:
        return
    reachable = source_reachable()
    if any(known.startswith(code) for code in selected for known in reachable):
        return
    raise ConfigError(
        f"{spelling}: every selected rule is a circuit rule, which needs an "
        "in-memory circuit and cannot run over files. Use the library API, "
        "or select a rule that reads source."
    )


def _warn_about_the_root_config(config: Config, args: argparse.Namespace) -> None:
    """A configured code that matches no rule was silent before this.

    It is a warning rather than an error: a pyproject.toml belongs to the tree
    being scanned, and one stale entry in it must not end a whole run.

    A configured selection that can only match circuit rules is the exception,
    and is an error, because it does not merely remove a rule: it removes every
    rule a file run can reach, and the result is an empty exit 0 report. A
    `--select` flag replaces the configured list entirely, so the configured
    one is only judged when no flag was given.
    """
    if not _codes(args.select):
        _reject_a_circuit_only_selection(config.select, f"[tool.{SECTION}] select")
    registered = tiers()
    for key, codes in (("select", config.select), ("ignore", config.ignore)):
        for code in codes:
            if any(known.startswith(code) for known in registered):
                continue
            print(
                f"qxlint: {config.source_path}: [tool.qxlint] {key}: no rule matches {code!r}",
                file=sys.stderr,
            )


def _print_profile(paths: list[Path], cache: ConfigCache, args: argparse.Namespace) -> int:
    root = paths[0] if paths else Path()
    config = _effective(cache.for_path(root if is_directory(root) else root.parent), args)
    profile = resolve_profile(config)
    print(f"qiskit:             {profile.qiskit.describe()} ({profile.qiskit.source.value})")
    runtime = profile.qiskit_ibm_runtime
    print(f"qiskit-ibm-runtime: {runtime.describe()} ({runtime.source.value})")
    if config.source_path is not None:
        print(f"config:             {config.source_path}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
