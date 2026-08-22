# Configuration

qxlint reads `[tool.qxlint]` from the nearest `pyproject.toml` above each
analysed file, so each package in a monorepo gets its own settings and its own
target versions.

```toml
[tool.qxlint]
select = ["QXL1", "QXL2"]
ignore = ["QXL102"]
preview = false
extend-exclude = ["vendor", "generated"]
target-qiskit = ">=2.0"
target-runtime = "0.48"

[tool.qxlint.per-file-ignores]
"notebooks/*" = ["QXL103"]
"tests/*" = ["QXL101"]
```

A key that is not one of the eight above is a typo, and qxlint refuses to run
rather than letting you believe a setting took effect. The message names every
unknown key and suggests the closest real one.

## The command line

```
qxlint [paths ...] [options]
```

With no path, the current directory is analysed.

| Flag | What it does |
| --- | --- |
| `--select CODES` | comma separated rule codes or prefixes to run |
| `--ignore CODES` | comma separated rule codes or prefixes to skip |
| `--target-qiskit SPEC` | target Qiskit version or specifier, for example `2.5` or `>=2.0` |
| `--target-runtime SPEC` | target `qiskit-ibm-runtime` version or specifier |
| `--config PATH` | read settings from this `pyproject.toml` and no other, for every analysed file |
| `--format {text,json,sarif}` | output format, `text` by default |
| `--no-color` | never colour the output |
| `--statistics` | per rule counts instead of a listing |
| `--show-profile` | print the resolved target versions and exit |
| `--version` | print the version and exit |

`--config` turns off the per directory lookup below. It is what a monorepo uses
to lint several packages against one policy, and what a CI job uses to keep a
checked out project's own settings out of the run.

## Precedence

Highest first:

1. command line flags
2. `[tool.qxlint]`, from `--config` if given, otherwise the nearest
   `pyproject.toml` above each analysed file
3. built in defaults

`--select` and `--ignore` **replace** the configured lists rather than extending
them, so a flag can always narrow a noisy project.

## Which files are scanned

A directory argument expands to every `.py` and `.ipynb` under it, minus any
path with an excluded component. These are excluded out of the box:

```
.git  .venv  venv  __pycache__  .tox  .nox  .mypy_cache  .ruff_cache
.pytest_cache  build  dist  node_modules  .ipynb_checkpoints
```

There are two options, and they do different things.

| Option | Effect |
| --- | --- |
| `extend-exclude` | added to the list above. This is usually what you want. |
| `exclude` | **replaces** the list above, so anything not named there is scanned, including `.venv` and `node_modules`. |

A plain entry matches a whole path component: `vendor` skips `vendor/a.py` and
`src/vendor/b.py`, and never `vendored.py`. An entry containing `*`, `?` or `[`
is a glob, matched against the path relative to the scanned directory as well as
against each component, so `build/*` skips everything under `build` and
`*_generated.py` skips that file wherever it sits. In a glob, `*` crosses `/`.
Matching is case sensitive, because directory names are.

Use `exclude` only to deliberately lint inside a directory the defaults skip.
Setting it to add one entry is the common mistake: it brings the entire virtual
environment back into the run.

## How the rule set is resolved

In this order, every time:

1. start from every registered rule
2. `select` keeps only codes matching one of its prefixes; when `select` is
   empty the starting set is every default tier rule, plus preview rules if
   `preview` is true
3. a preview rule stays off unless `preview` is true or its **exact** code
   appears in `select`, so `select = ["QXL3"]` does not silently enable preview
   rules by prefix
4. `ignore` removes codes matching one of its prefixes
5. `per-file-ignores` removes further codes for paths matching a glob. A
   pattern is matched against the path relative to the project root, the path
   as it was typed, and the file name, so the same file is treated the same
   way whether you run `qxlint .`, name the file, or pass an absolute path

In 0.1.1 every preview rule is a circuit rule, reached through `check_circuit`
rather than by linting a file, so `preview` changes nothing about a `qxlint`
run. It is honoured by the resolution above, and takes effect the moment a
preview rule reads source. The circuit rules take `preview=True` as an argument.

## Suppression

```python
counts = result.get_counts()      # noqa: QXL101
counts = result.get_counts()      # noqa: QXL101, QXL103
counts = result.get_counts()      # noqa: QXL1
counts = result.get_counts()      # noqa
```

The keyword is case insensitive, codes are separated by commas or whitespace,
and a bare `# noqa` suppresses every rule on that line. A `# noqa:` with no
readable code after it falls back to suppressing everything, matching flake8.

A listed code is a **prefix**, also matching flake8, so `# noqa: QXL1` covers
QXL101 through QXL105 and `# noqa: QXL` covers every rule. That is the same
matching `--select` and `--ignore` use, so one file behaves the same whether it
is linted by the `qxlint` command or by `flake8 --select=QXL`.

Comments are read with `tokenize`, so `# noqa` inside a string literal is not a
suppression. Under flake8, suppression is flake8's job and qxlint does not
apply it twice.

## Target versions

Resolution order for `target-qiskit` and `target-runtime`:

1. `--target-qiskit` / `--target-runtime`
2. `[tool.qxlint]`
3. declared dependencies in the analysed project's `pyproject.toml`
   (`project.dependencies`, `project.optional-dependencies`,
   `dependency-groups`), intersected; skipped entirely if any of them carries an
   environment marker or a direct URL, because that makes the target
   conditional
4. an exact pin in `uv.lock`, used only when the package resolves to exactly one
   version across the whole lock
5. otherwise unknown, and every version dependent rule stays silent

Recursive `requirements.txt` includes and multi environment locks are out of
scope for v0.1. Resolving them correctly means writing a dependency resolver
before writing the linter.

Check what qxlint resolved:

```bash
qxlint --show-profile .
```

## Summary view

`--statistics` replaces the per finding listing with per rule counts, which is
what the release gate asks results to be published as:

```bash
qxlint --statistics .
```

```
  QXL104  ████████████████████████  37  discarded-circuit-result
  QXL101  █████░░░░░░░░░░░░░░░░░░░   7  get-counts-on-wrong-receiver
  QXL102  █░░░░░░░░░░░░░░░░░░░░░░░   2  quasi-dists-on-v2-result

  46 findings across 22 files of 13861 scanned
```

It composes with `--format json`, which emits the same summary as data. It has
no SARIF form, and asking for one is a usage error rather than a silent fallback,
because SARIF describes findings and not aggregates.

The exit code is unaffected: findings still mean exit 1, so a CI gate behaves
identically with or without the flag.

## Colour

Colour is emitted only when the destination can show it, decided in this order:

1. `NO_COLOR` disables it, per [no-color.org](https://no-color.org): present
   and not an empty string, regardless of the value, so `NO_COLOR=0` disables
   colour and `NO_COLOR=` counts as unset
2. `--no-color` disables it
3. a destination that is not a terminal disables it, which is what keeps escape
   sequences out of pipes and CI logs; `FORCE_COLOR` overrides this
4. `TERM=dumb` disables it
5. `COLORTERM=truecolor` or `24bit` gives 24-bit colour, `TERM` containing
   `256color` gives the 256 colour cube, anything else gives the 16 colour codes

Findings keep the conventional red, yellow and cyan for error, warning and note.
The project palette is used only by `--statistics`, where a filled bar carries
the number. Histogram blocks fall back to ASCII when the output encoding cannot
represent them.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | no findings |
| 1 | findings, including QXL000 for a file that could not be parsed |
| 2 | qxlint could not run: bad usage, unreadable or invalid config, missing path, internal error |

A file that fails to parse is a finding, not an internal error. That keeps a
non-zero exit meaningful: it always means "look at the output".

Exit 2 also covers a flag that cannot do what it says:

| Command line | Result |
| --- | --- |
| `--select` with a code matching no rule | exit 2. It would leave every rule off, so the run reports nothing and reads as a clean project. |
| `--select` naming only circuit rules | exit 2. QXL300 to QXL303 read an in-memory circuit and cannot fire from a file, so the run would report nothing for the same reason. Selecting one alongside a source rule is fine. |
| `--target-qiskit` or `--target-runtime` that is not a version or a specifier | exit 2. It would silently disable the version gated rules. |
| `--ignore` with a code matching no rule | warning on stderr, exit code unchanged. An ignore that removes nothing cannot make a run wrongly clean. |
| a run that analysed no files at all | warning on stderr, exit code unchanged. `--statistics` says `No files were analysed.` rather than a count, so it cannot be mistaken for a clean project. |
| the same codes in `[tool.qxlint]` | warning on stderr, exit code unchanged. A `pyproject.toml` belongs to the tree being scanned, and one stale entry in it must not end the whole run. |
