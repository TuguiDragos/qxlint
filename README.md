<h1 align="center">
  <img src="https://raw.githubusercontent.com/TuguiDragos/qxlint/main/readme-assets/png/qxlint-icon-256.png" alt="" width="56" align="center" />
  &nbsp;qxlint
</h1>

<p align="center"><strong>Deterministic static checks for Qiskit Primitives V2 workflows.</strong></p>

<p align="center">
  <a href="https://pypi.org/project/qxlint/"><img alt="PyPI downloads a month" src="https://img.shields.io/pypi/dm/qxlint?style=flat&color=161826&label=PyPI&logo=pypi&logoColor=9184D9" /></a>
  <a href="https://www.npmjs.com/package/@tuguidragos/qxlint"><img alt="npm downloads a month" src="https://img.shields.io/npm/dm/@tuguidragos/qxlint?style=flat&color=161826&label=npm&logo=npm&logoColor=9184D9" /></a>
  <a href="https://github.com/TuguiDragos/qxlint/blob/main/LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/License-MIT-161826?style=flat" /></a>
</p>

<p align="center">
  <a href="https://github.com/TuguiDragos/qxlint/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/TuguiDragos/qxlint/ci.yml?branch=main&style=flat&color=161826&label=CI&logo=githubactions&logoColor=9184D9" /></a>
  <a href="https://www.python.org/"><img alt="Python 3.11 to 3.14" src="https://img.shields.io/badge/Python-3.11%20--%203.14-161826?style=flat&logo=python&logoColor=9184D9" /></a>
  <a href="https://www.ibm.com/quantum/qiskit"><img alt="Qiskit optional" src="https://img.shields.io/badge/Qiskit-optional-161826?style=flat&logo=qiskit&logoColor=9184D9" /></a>
  <a href="https://docs.pytest.org/"><img alt="903 tests" src="https://img.shields.io/badge/tests-903-161826?style=flat&logo=pytest&logoColor=9184D9" /></a>
  <a href="https://mypy-lang.org/"><img alt="mypy strict" src="https://img.shields.io/badge/mypy-strict-161826?style=flat" /></a>
  <a href="https://tuguidragos.com"><img alt="tuguidragos.com" src="https://img.shields.io/badge/tuguidragos.com-161826?style=flat&logo=safari&logoColor=9184D9" /></a>
</p>

---

qxlint finds the mistakes the Qiskit V1-to-V2 primitives migration introduced:
reading counts off the wrong object, using a V1 field on a V2 result, sampling a
circuit that has no measurements, and passing a channel value a targeted release
has removed.

It reads your source. It never imports it and never executes it, it makes no
network requests, and it needs no quantum hardware.

```bash
uvx qxlint .
```

```
app.py:31:10: QXL101 get_counts() on a PrimitiveResult; counts live on the BitArray in PrimitiveResult -> PubResult -> .data (DataBin) -> <classical register> (BitArray)
app.py:44:1:  QXL103 circuit has no measurement instructions but is passed to a SamplerV2; the result carries no counts
service.py:7:31: QXL201 channel="ibm_quantum" was removed in qiskit-ibm-runtime 0.41; omit the channel argument
```

---

## Why it exists

Two things fail quietly in Primitives V2 code.

**The result shape changed and the errors arrive late.** Counts now live at
`result[i].data.<classical register>`, on a `BitArray`. Calling `get_counts()`
one level too high raises `AttributeError`, but only after the job has run.

**An unmeasured circuit does not fail at all.** With no classical register,
Qiskit 2.5.1 emits a `UserWarning` and returns an empty data bin. With a
classical register but no `measure` instruction there is no warning whatsoever,
and every shot reads as zeros, which looks like a physics result rather than a
bug. This is the case qxlint was built for.

Both are decidable statically, and neither needs a model, a network or a quantum
computer.

---

## Install

| | |
| --- | --- |
| Run without installing | `uvx qxlint .` |
| Install as a tool | `uv tool install qxlint` or `pipx install qxlint` |
| Add to a project | `pip install qxlint` |
| From a JavaScript toolchain | `npx @tuguidragos/qxlint .`, the [npm launcher](https://www.npmjs.com/package/@tuguidragos/qxlint); still needs Python |
| In VS Code | the [qxlint extension](https://marketplace.visualstudio.com/items?itemName=tuguidragos.qxlint), also on [Open VSX](https://open-vsx.org/extension/tuguidragos/qxlint) |
| With the circuit checks | `pip install 'qxlint[circuit]'` |

Python 3.11 to 3.14. **Qiskit is optional**: the source linter needs no Qiskit at
all, and only the in-memory circuit checks require it installed.

---

## Rules

| Code | Tier | Fires when |
| --- | --- | --- |
| [QXL000](docs/rules/qxl000.md) | default | the file or notebook cell cannot be parsed |
| [QXL101](docs/rules/qxl101.md) | default | `get_counts()` on a `PrimitiveResult`, `PubResult` or `DataBin` |
| [QXL102](docs/rules/qxl102.md) | default | `quasi_dists` read from a V2 `PrimitiveResult` |
| [QXL103](docs/rules/qxl103.md) | default | a provably unmeasured circuit reaches a `SamplerV2` |
| [QXL104](docs/rules/qxl104.md) | default | a circuit method returning a new circuit whose result is dropped |
| [QXL105](docs/rules/qxl105.md) | default | a measured circuit reaches a `StatevectorEstimator` |
| [QXL201](docs/rules/qxl201.md) | default | `channel="ibm_quantum"` on a target that removed it |
| [QXL202](docs/rules/qxl202.md) | default | Runtime `SamplerV2` given `backend=` or `session=` instead of `mode=` |
| [QXL301](docs/rules/qxl301.md) | default, library | a circuit uses an operation the `Target` does not support |
| [QXL302](docs/rules/qxl302.md) | preview, library | two adjacent identical self inverse gates cancel |
| [QXL303](docs/rules/qxl303.md) | preview, library | a qubit is declared but never operated on |

Every rule page documents **when the pattern is legitimate**. If that section
cannot be written, the rule does not ship.

The three marked *library* work on an in-memory circuit and are reached through
`qxlint.check_target` and `qxlint.check_circuit`, not by linting a file.

### Precision over recall

A false positive costs more than a missed finding, so a rule fires only on facts
the analyser can prove. Rules never fire on `MAYBE` and never on `UNKNOWN`.

```python
qc = QuantumCircuit(1)
if condition:
    qc.measure_all()
sampler.run([qc])          # QXL103 stays silent: measured on some paths
```

A missed detection is not free either, which is why the semantic layer models
aliases, containers, the library circuits and the transpile pipeline rather than
giving up on them.

---

## How it decides

The valuable rules cannot be AST pattern matches. `get_counts()` is correct on a
`BitArray` and wrong on a `DataBin`; the question is never "does this call
appear" but "what is this object". qxlint answers that with a small abstract
interpreter. [Full design](docs/semantic-layer.md).

**Names bind to object identities, not to facts**, so aliases work:

```python
qc = QuantumCircuit(1)
alias = qc
alias.measure_all()
sampler.run([qc])          # silent, the measurement is on the same object
```

**A local container is not an escape.** This is how most Sampler code is
written, so it has to be analysable:

```python
circuits = []
circuits.append(qc)
sampler.run(circuits)      # the circuit is still tracked
```

**Effects are scoped.** A call that cannot reach a circuit does not affect it; a
call that receives it does.

```python
qc = QuantumCircuit(2)
qc.h(0)
print("running")           # cannot touch qc
sampler.run([qc])          # QXL103 fires

qc2 = QuantumCircuit(2)
helper(qc2)                # may keep and mutate it
sampler.run([qc2])         # silent
```

**Library circuits are circuits.** `RealAmplitudes`, `EfficientSU2`,
`ZFeatureMap`, `QAOAAnsatz` and the rest of `qiskit.circuit.library` are modelled,
so an ansatz is not an opaque object the rules cannot reach.

### Version gated rules

A version specifier is not a version. `>=0.38,<0.43` spans releases where
`channel="ibm_quantum"` is valid, deprecated and removed, so QXL201 asks whether
a predicate holds across *every* version the target allows, and fires only when
it always does.

| Declared target | QXL201 |
| --- | --- |
| `0.48`, `>=0.41` | error: removed in 0.41 |
| `0.40.2`, `==0.40.*` | warning: deprecated since 0.40 |
| `>=0.38,<0.43` | silent, the range spans the change |
| not declared | silent |

Targets come from `--target-runtime`, then `[tool.qxlint]`, then the analysed
project's `pyproject.toml` dependencies, then an unambiguous `uv.lock` pin.
qxlint never inspects its own installed Qiskit for this: the version in the
linter's environment is not the version your project targets.

---

## Notebooks

`.ipynb` files are analysed directly, and semantic facts carry across cells in
textual order.

Magics are not blanked out, because blanking lies to the analyser. `%run` can
rebind any name, so treating it as a no-op would leave stale facts and produce a
false positive. Magics are sorted by what they can actually do:

| Kind | Examples | Handling |
| --- | --- | --- |
| Display or config | `%matplotlib`, `%pip`, `!cmd` | dropped, facts kept |
| Python body | `%%time`, `%%capture`, `%time` | header dropped, body analysed |
| Namespace mutating | `%run`, `%load`, `%pylab`, unknown magics | semantic barrier |
| Non Python body | `%%bash`, `%%sql`, `%%html` | whole cell dropped, barrier |

Line counts are preserved by every rewrite, so a reported line is the line you
see in the cell. Findings carry a 1-based `cell_index` over code cells, matching
nbqa. [Details and limits](docs/notebooks.md).

---

## Integration

<details>
<summary>pre-commit</summary>

```yaml
repos:
  - repo: https://github.com/TuguiDragos/qxlint
    rev: v0.1.0
    hooks:
      - id: qxlint
      - id: qxlint-notebook
```
</details>

<details>
<summary>GitHub Actions with SARIF</summary>

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  qxlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: TuguiDragos/qxlint@v0.1.0
        with:
          paths: .
          format: sarif
          output: qxlint.sarif
      - uses: github/codeql-action/upload-sarif@v4
        if: always()
        with:
          sarif_file: qxlint.sarif
```

`security-events: write` must be granted by the calling workflow; an action
cannot grant it to itself. Private and internal repositories additionally need
GitHub code security enabled.
</details>

<details>
<summary>VS Code</summary>

Install the **qxlint** extension, then install the analyser into the environment
you have selected:

```bash
pip install qxlint
```

Diagnostics appear in `.py` files and in notebook cells, and each rule code in
the Problems panel links to its documentation page. The extension runs the same
CLI with the same `[tool.qxlint]` configuration, so the editor and CI cannot
disagree.

With the Python extension installed it follows the interpreter you have
selected. Without it, point `qxlint.path` at the executable, or have one on
`PATH`. Source in [vscode/](vscode/).
</details>

<details>
<summary>flake8</summary>

```bash
pip install qxlint flake8
flake8 --select=QXL .
```

VS Code does not pick this up automatically, because the Python extension uses
its own bundled flake8:

```json
{ "flake8.importStrategy": "fromEnvironment" }
```

The plugin covers `.py` only. Use the qxlint CLI or nbqa for notebooks.
</details>

<details>
<summary>Configuration</summary>

```toml
[tool.qxlint]
select = ["QXL1", "QXL2"]
ignore = ["QXL102"]
preview = false
extend-exclude = ["vendor"]
target-qiskit = ">=2.0"
target-runtime = "0.48"

[tool.qxlint.per-file-ignores]
# Test suites deliberately exercise the unmeasured path.
"tests/*" = ["QXL103"]
"notebooks/*" = ["QXL103"]
```

`.venv`, `.git`, `node_modules`, `build`, `dist` and the usual caches are
skipped already. `extend-exclude` adds to that list; `exclude` replaces it, for
the rarer case where you want to lint inside one of them.

Suppress a single line with `# noqa: QXL101`, or every rule on it with `# noqa`.
A code is a prefix, as in flake8, so `# noqa: QXL1` covers every QXL1xx rule on
that line. [All options](docs/configuration.md).
</details>

<details>
<summary>Summary view</summary>

```bash
qxlint --statistics .
```

```
  QXL104  ████████████████████████  37  discarded-circuit-result
  QXL101  █████░░░░░░░░░░░░░░░░░░░   7  get-counts-on-wrong-receiver
  QXL102  █░░░░░░░░░░░░░░░░░░░░░░░   2  quasi-dists-on-v2-result

  46 findings across 22 files of 13861 scanned
```

That is real output from one repository in the corpus below.

Per rule counts, which is how results are published. Works with `--format json`
too. The exit code is unchanged, so a CI gate behaves the same with or without it.

Colour is emitted only when the destination can show it. `NO_COLOR` is honoured,
a pipe never receives escape sequences, and 24-bit degrades to 256, then to 16,
then to none. Histogram blocks fall back to ASCII when the encoding cannot carry
them.
</details>

**Exit codes.** `0` clean, `1` findings, `2` qxlint could not run. A file that
does not parse is a finding (QXL000), not an internal error, so a non-zero exit
always means "look at the output". One unreadable file never ends the run.

A `--select` that matches no rule is exit 2, not a clean run: leaving every rule
off would take a CI gate green without having checked anything. Same for a
`--target-*` value that is not a version.

---

## Circuit checks (library API)

These operate on an in-memory circuit, so they have no `file:line`. They report
a circuit name and an instruction path that stays unambiguous inside control
flow blocks.

```python
import qxlint

for finding in qxlint.check_target(isa_circuit, backend.target):
    print(finding.render_text())
# circuit-44[2].block[0][0]: QXL301 operation 'cy' on qubits [0, 1] is not supported by the target
```

```python
qxlint.check_circuit(qc, target=backend.target, preview=True)
```

`check_circuit` with neither `target` nor `preview` returns an empty list, and
says so rather than leaving it as a surprise: QXL301 needs a target, and the
other two circuit rules are preview tier.

A `target` that is not a Qiskit `Target` raises `TypeError`. It used to return
no findings, which is the one answer a compatibility check must never give when
it did not run.

---

## How it is tested

Every claim on this page is backed by something that runs.

### Against its own suite

| | |
| --- | --- |
| Tests | **903**, on Python 3.11, 3.12, 3.13 and 3.14 |
| Qiskit matrix | 2.5.1, the declared floor 2.0.3, and a job with **no Qiskit installed at all** |
| Coverage | **100% of statements and branches**, enforced as a CI gate, not reported as a number |
| Types | `mypy --strict`, clean |
| Style | `ruff check` and `ruff format --check`, clean |
| API model | **340 checks** against a real Qiskit install, run on a schedule so an upstream change is a test failure rather than a user report |
| Mutation testing | 46 hand written mutations, each changing one documented behaviour. 44 were caught; the 2 survivors were each verified to be equivalent mutants |

The API tables were built by introspecting an installed Qiskit, not by reading
documentation prose. The self inverse gate list was built by squaring operator
matrices.

### Against code it has never seen

244 public repositories, selected and pinned to commit SHAs **before** the
linter was run on any of them.

| | |
| --- | --- |
| Repositories | **244**, from 243 distinct owners |
| Files read | **51,715**: 50,389 `.py` and 1,326 `.ipynb` |
| Crashes, timeouts, exit code 2 | **0** |
| Non deterministic results | **0** |
| Findings, every one read and labelled | 342 |
| of which workflow defects rather than unparsable files | **174** |
| False positives, all one defect, since fixed | **30** |
| Findings the current tree reports | **312** |
| Defects the corpus found in qxlint, and fixed | **9** |

The 30 were one defect: the notebook magic detector required a letter after the
`!`, so `! pip install x`, `!{sys.executable} -m pip install x` and `!./run.sh`
stayed in the cell and it was reported as unparsable. Handing the cell to
CPython, which is how QXL000 was checked, cannot catch that: a cell with a shell
escape is not valid Python either way. The question for a notebook cell is what
IPython accepts, and the scan never asked it.

Three of the QXL104 findings are in Qiskit's own test suite, where a circuit
method that returns a new circuit is called as a bare statement:

```python
qc.compose(CCXGate().definition, [0, 1, 2], [])  # Unroll CCX to 2q operations.
qc.assign_parameters({theta: 3.14})
circ.inverse()
```

`compose` and `assign_parameters` default to `inplace=False` and `inverse`
always returns, so the comment on the first line describes something that does
not happen.

Every finding was read in context and labelled, with the line it was reported
on, in [findings.csv](corpus/findings.csv). Full write up in
[corpus/](corpus/).

**What a pattern matcher would have done.** The corpus contains **4,003**
`.get_counts(` calls and **286** `quasi_dists` occurrences. A linter matching
those textually would have reported 4,289 findings. qxlint reports 18, each on a
V2 result object; the other 4,271 are correct legacy or V1 code, where
`get_counts()` is exactly right.

### Against hostile input

Encodings the file does not declare, UTF-16 and cp1252 notebooks, BOMs, null
bytes, CRLF and lone CR, symlink loops, symlinks to ancestors, broken symlinks,
named pipes, unreadable directories, 60 levels of nesting, expressions deeper
than the parser can follow, 200,000 line cells, notebooks whose JSON is broken
and notebooks that are not JSON at all. None of them crashes the run, hangs it,
or costs the findings in the rest of the tree.

### Speed

The whole corpus, 51,715 files across 244 repositories, is **115.7 seconds** in
one process on one laptop core, peaking at 270 MB. A single repository is well
under a second, which is what makes it invisible in a pre-commit hook.

---

## Honest limits

- **No interprocedural analysis.** A circuit mutated inside a helper is not
  tracked, a circuit reaching a primitive as a parameter or a return value
  carries no facts, and calling a function defined in the same module
  invalidates every fact.
- **A function body inherits imports, not data.** A name bound at module level
  is unknown inside a function, because the order in which functions run is not
  known and assuming one would invent facts. So a module level `sampler` used
  inside a function reaches the rules as unknown, and nothing fires. This is
  measured, not guessed: on the 218 repository corpus it costs 8 of 437 primitive
  calls and no findings at all. [Details](docs/semantic-layer.md).
- **The finding set is per interpreter.** qxlint parses with the CPython running
  it, so syntax that changed between versions is judged by that version. An
  f-string with nested same quotes, `f"{d["k"]}"`, is a syntax error on 3.11 and
  valid from 3.12, and QXL000 follows. Run the same interpreter locally and in
  CI, as you would for any other linter.
- **No precision figure is published.** Every finding across the corpus was
  read and labelled and none was wrong, but a single reviewer is not an
  independent precision measurement. See the
  [release gate](docs/release-gate.md) for exactly what is and is not claimed.
- **Recall is measured for one rule only.** For the removed channel, where the
  textual pattern is precise enough to build a trustworthy denominator, qxlint
  reports 79 of the 81 live call sites in the corpus. The two it misses are
  behind an import that is commented out, or one whose `except ImportError`
  branch rebinds the name, where silence is the designed behaviour.
- **Notebook automagic** (a bare `ls`) is indistinguishable from Python and is
  not detected. Out-of-order interactive execution cannot be reconstructed;
  analysis assumes cells run top to bottom.
- **SARIF physical source locations** are guaranteed for `.py` files. Notebook
  findings carry logical cell locations, so inline pull request annotations are
  not guaranteed for them. Circuit findings have no file at all.
- Every statement qxlint makes about IBM Runtime is about its **client side**
  validation, read from its source. qxlint asserts nothing about server
  behaviour.

---

## Prior art

qxlint is not the first Qiskit linter and does not claim to be.

| Project | What it does | Overlap with qxlint |
| --- | --- | --- |
| [flake8-qiskit-migration](https://github.com/qiskit-community/flake8-qiskit-migration) 0.5.0 | 6 checks (`QKT100`-`QKT202`), 207 data entries, all deprecated or removed name lookup | None. It answers "does this still exist"; qxlint answers "is this workflow correct". **Run both.** |
| [LintQ](https://github.com/sola-st/LintQ) (FSE 2024) | 10 CodeQL analyses, 91.0% precision with its 6 default analyses over 7,568 programs | None of its ten evaluated analyses touches Primitives V2 PUBs, observables or layout. Needs a CodeQL database and Docker. |
| QChecker, QSmell | research prototypes, AST and execution trace based | Different targets, both effectively unmaintained |
| [lique](https://github.com/sarulab-ou/lique), [qasmtools](https://github.com/orangekame3/qasmtools) | Rust general quantum linter; OpenQASM 3 toolkit | Adjacent, neither targets the Qiskit Python API |
| LintQ-LLM (arXiv 2504.05204), [arXiv 2605.03943](https://arxiv.org/abs/2605.03943) | LLM based linting, F1 0.70 vs LintQ's 0.41 | See below |

Full comparison with sources: [docs/prior-art.md](docs/prior-art.md).

### On the argument that rule-based quantum linters cannot keep up

"Beyond Rules: LLM-Powered Linting for Quantum Programs" (May 2026) argues that
rule-based quantum linters struggle to keep pace with rapidly evolving APIs.
That is a fair criticism of a linter built as a list of API names, and it is part
of why qxlint implements no migration rules at all.

It is a weaker criticism of this design. qxlint targets Primitives V2, which is
the stabilised surface rather than the moving one: V1 primitives were removed in
Qiskit 2.0 and the V2 shape is now the supported path. Version dependent rules
consult a declared target and stay silent when they cannot prove applicability,
so an API change makes qxlint quieter rather than wrong. And determinism is not a
stylistic preference in CI: the same commit must produce the same findings, at no
per-run cost, offline, with a reviewable reason for every one.

Both approaches can be right. An LLM linter is a good fit for open-ended review;
a deterministic one is a good fit for a merge gate.

---

## Documentation

- [Rules](docs/rules/index.md), generated from the rule modules
- [The semantic layer](docs/semantic-layer.md), the analysis contract
- [Configuration](docs/configuration.md)
- [Notebooks](docs/notebooks.md)
- [Release gate](docs/release-gate.md), what is claimed and what is not
- [Prior art](docs/prior-art.md)
- [External corpus](corpus/), the scans and their labelled findings

## Contributing

Setup, the bar a new rule has to clear, and what runs before a pull request:
[CONTRIBUTING.md](CONTRIBUTING.md).

```bash
uv sync
uv run pytest
```

## License and trademark

MIT. Author: Tugui Dragos, <https://tuguidragos.com>

> Qiskit is a trademark of IBM Corporation. qxlint is an independent project and
> is not affiliated with or endorsed by IBM.
