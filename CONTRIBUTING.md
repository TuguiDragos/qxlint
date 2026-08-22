# Contributing

## Setup

```bash
uv sync
uv run pytest
```

`uv sync --extra circuit` additionally installs Qiskit, which the circuit rules
need. Everything else works without it, and one CI job proves that.

## The bar for a new rule

Rules are deliberately few. Before writing one, answer these:

1. **Is it decidable without running the code?** If it needs a value only known
   at runtime, it is not a rule.
2. **Can you write the "when this is legitimate" section?** If you cannot, the
   pattern is a style preference. The test suite enforces that this text exists.
3. **Does it fire only on proven facts?** A rule that fires on `MAYBE_PRESENT`
   or `UNKNOWN` will produce false positives, and a false positive costs far
   more than a missed finding.
4. **Is the API claim verified against an installed Qiskit?** Not against
   documentation prose, and not against a memory of the API. The tables in
   `semantics/model.py` were built by introspection and say so, and
   `scripts/verify_model.py` re-checks them on a schedule.

## Adding a rule

One rule module plus one test module, nothing else:

```
src/qxlint/rules/qxlNNN_short_name.py     the rule and its RuleMeta
tests/unit/test_rule_qxlNNN.py            one positive, at least two negatives
```

Register it in `qxlint/registry.py::_load`, then regenerate the docs:

```bash
uv run python scripts/generate_docs.py
```

The documentation page is generated from `RuleMeta`. Do not edit
`docs/rules/*.md` by hand; the test suite fails if you do.

Each default tier rule needs at least two negative fixtures, one of which must be
a realistic case where the pattern is correct. For QXL101 that is
`BitArray.get_counts()`, which is the whole reason the rule needs a semantic
layer.

## Touching the semantic layer

`tests/unit/test_semantic_lattice.py` enumerates the merge table cell by cell and
`tests/unit/test_semantic_effects.py` covers aliasing, containers, escape and
control flow. Both are the specification, not incidental coverage. A change that
needs one of them edited needs `docs/semantic-layer.md` edited too.

## Reading a file is a contract

One file qxlint cannot handle must never cost the rest of the run. Anything that
opens or decodes a path has to hold that line: a parse failure, a bad encoding,
a nesting depth the parser cannot follow and a path that is not a regular file
are all findings on that file, and the walk continues.

If you add a new way to read something, add the hostile input test with it.
`tests/unit/test_core_types_edges.py` and `tests/integration/test_cli.py` show
the shape. A test that would **hang** on regression rather than fail is not
acceptable; drive the case through a subprocess with a deadline, as the named
pipe test does.

## Before opening a pull request

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run pytest --cov                      # the gate is 100%, lines and branches
uv run python scripts/generate_docs.py   # must leave the tree unchanged
uv run python scripts/verify_model.py    # needs Qiskit installed
```

The launchers and the extension have their own suites:

```bash
cd npm && npm test
cd vscode && npm test                    # the pure functions
cd vscode && QXLINT_TEST_PATH=$(command -v qxlint) npm run test:e2e
```

`test:e2e` downloads a VS Code build, loads the extension into it and reads the
diagnostics the editor really produces. On Linux it needs a display:
`xvfb-run -a npm run test:e2e`.

CI runs all of these on Python 3.11 through 3.14, on the pinned Qiskit, on the
declared minimum Qiskit, and with no Qiskit at all.

## Coverage is a gate, not a report

The project sits at 100% on both statements and branches, and `pytest --cov`
fails below that. This is not a vanity number: a guard whose false side never
runs is exactly where a linter hides a wrong answer, which is why branch
coverage is on.

Coverage says every line ran. It does not say a test would notice if the line
were wrong, so behaviour that matters gets a test that fails when the behaviour
changes, not merely one that executes the line.

If a line genuinely cannot be reached by any valid input, mark it
`# pragma: no cover` and write the reason next to it. There are a handful of
those, each with an explanation. Reaching for the pragma to avoid writing a test
is not the same thing, and shows up in review as a missing "why".

## Claims are checked, not asserted

Anything the documentation says about Qiskit, about a standard, or about another
tool needs a primary source, and where it can be executed it is executed. The
external corpus in [corpus/](corpus/) is the same idea at a larger scale:
repeated scans over 244 unseen repositories, pinned to commit SHAs and selected
before the linter was run, with every one of the 342 findings read and labelled.

All 342 labels were written by an AI reviewer, `claude-opus-5`, and none has
been confirmed by a human. The `reviewer` column records that on every row.
Treat the corpus as evidence a maintainer still has to check, not as a verdict.

Before a release the corpus is rescanned. A repairable false positive is
repaired and the corpus rescanned again.

## Commit and review

Conventional commit prefixes are appreciated but not enforced. What is enforced:
no new default tier rule without negative fixtures, and no factual claim about
Qiskit without a primary source in the pull request description.

## Releases

There is no changelog file in the repository. Each release carries its notes on
its [GitHub release](https://github.com/TuguiDragos/qxlint/releases), which is
also what the `Changelog` link on PyPI points at.

`pyproject.toml`, `npm/package.json` and `vscode/package.json` all carry the
version, and the release workflow refuses to run if they disagree with each
other or with the tag.
