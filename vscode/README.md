<p align="center">
  <img src="https://raw.githubusercontent.com/TuguiDragos/qxlint/main/readme-assets/png/qxlint-icon-256.png" alt="qxlint" width="96" />
</p>

<h1 align="center">qxlint for VS Code</h1>

<p align="center">
  <a href="https://pypi.org/project/qxlint/"><img alt="PyPI downloads a month" src="https://img.shields.io/pypi/dm/qxlint?style=flat&color=161826&label=PyPI&logo=pypi&logoColor=9184D9" /></a>
  <a href="https://www.npmjs.com/package/@tuguidragos/qxlint"><img alt="npm downloads a month" src="https://img.shields.io/npm/dm/@tuguidragos/qxlint?style=flat&color=161826&label=npm&logo=npm&logoColor=9184D9" /></a>
  <a href="https://github.com/TuguiDragos/qxlint/blob/main/LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/License-MIT-161826?style=flat" /></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.11 to 3.14" src="https://img.shields.io/badge/Python-3.11%20--%203.14-161826?style=flat&logo=python&logoColor=9184D9" /></a>
  <a href="https://www.ibm.com/quantum/qiskit"><img alt="Qiskit optional" src="https://img.shields.io/badge/Qiskit-optional-161826?style=flat&logo=qiskit&logoColor=9184D9" /></a>
  <a href="https://jupyter.org/"><img alt="Jupyter notebooks" src="https://img.shields.io/badge/Jupyter-notebooks-161826?style=flat&logo=jupyter&logoColor=9184D9" /></a>
  <a href="https://tuguidragos.com"><img alt="tuguidragos.com" src="https://img.shields.io/badge/tuguidragos.com-161826?style=flat&logo=safari&logoColor=9184D9" /></a>
  <a href="https://docs.pytest.org/"><img alt="909 tests" src="https://img.shields.io/badge/tests-909-161826?style=flat&logo=pytest&logoColor=9184D9" /></a>
</p>

---
**Deterministic static checks for Qiskit Primitives V2 workflows**, in the
editor and in notebooks.

qxlint catches the workflow mistakes the Qiskit V1-to-V2 primitives migration
introduced: reading counts off the wrong object, using a V1 field on a V2
result, sampling a circuit that has no measurements, and passing a channel value
your targeted release has removed.

It never imports or executes your code.

## What it catches

| Code | Fires when |
| --- | --- |
| `QXL101` | `get_counts()` on a `PrimitiveResult`, `PubResult` or `DataBin` instead of the `BitArray` |
| `QXL102` | `quasi_dists` read from a V2 `PrimitiveResult` |
| `QXL103` | a provably unmeasured circuit reaches a `SamplerV2` |
| `QXL104` | a circuit method that returns a new circuit, called as a bare statement |
| `QXL105` | a measured circuit reaches a `StatevectorEstimator` |
| `QXL201` | `channel="ibm_quantum"`, removed in `qiskit-ibm-runtime` 0.41 |
| `QXL202` | a Runtime `SamplerV2` or `EstimatorV2` given `backend=` or `session=` instead of `mode=` |
| `QXL000` | a file or notebook cell that cannot be parsed |

Rule codes in the Problems panel link straight to the rule's documentation.

## The quiet bug it exists for

An unmeasured circuit sent to a Sampler does not fail. With no classical
register Qiskit emits only a `UserWarning`; with a register but no `measure`
instruction there is no warning at all and every shot reads as zeros, which
looks like a physics result rather than a mistake.

## Why it does not just match patterns

`get_counts()` is correct on a `BitArray` and an `AttributeError` on a
`DataBin`, and the two look identical in the syntax tree. qxlint resolves what
each object actually is, tracks aliases and lists, and stays silent whenever it
cannot prove the answer.

Measured on 244 external repositories, 51,715 files: the corpus holds 4,003
`.get_counts(` calls and 286 `quasi_dists` occurrences, so a linter matching
those textually would have reported 4,289 findings. qxlint reports 18, each on a
V2 result object; the rest are correct legacy code.

## Requirements

The analyser is the Python package. Install it into the environment you have
selected in VS Code:

```
pip install qxlint
```

If you have the **Python extension** installed, qxlint uses the interpreter it
has selected and re-runs when you switch environments. It is not required: set
`qxlint.path` to a `qxlint` executable, or have one on `PATH`, and the extension
works on its own.

## Notebooks

`.ipynb` files are analysed directly, with facts carried across cells in
textual order. Magics are classified rather than blanked, because `%run` can
rebind any name: display magics are dropped, `%%time` bodies are analysed, and
namespace-mutating magics act as a barrier so no stale fact survives them.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `qxlint.enable` | `true` | Run qxlint at all |
| `qxlint.run` | `onSave` | `onSave` or `onType` |
| `qxlint.path` | `""` | Explicit executable, otherwise the selected interpreter |
| `qxlint.select` | `""` | Comma separated codes or prefixes to run |
| `qxlint.ignore` | `""` | Comma separated codes or prefixes to skip |
| `qxlint.targetQiskit` | `""` | Target Qiskit version or specifier |
| `qxlint.targetRuntime` | `""` | Target `qiskit-ibm-runtime` version or specifier |
| `qxlint.args` | `[]` | Extra CLI arguments |

`onType` re-runs the analyser shortly after you stop typing, but the analyser
reads the file from disk, so unsaved edits are not reflected until you save.

Version dependent rules stay silent unless the target version can be
established, from these settings or from your project's `pyproject.toml`.
Project level `[tool.qxlint]` configuration is read by the CLI itself, so the
editor and CI agree.

## Commands

From the command palette:

| Command | What it does |
| --- | --- |
| **qxlint: Lint workspace** | analyse every folder in the workspace, not only open files |
| **qxlint: Re-lint open files** | clear the diagnostics and run again, after changing an interpreter or a setting |
| **qxlint: Show output** | open the qxlint output channel, which logs the exact command it ran |

## Links

- Source and rule documentation: <https://github.com/TuguiDragos/qxlint>
- Python package: <https://pypi.org/project/qxlint/>
- npm launcher: <https://www.npmjs.com/package/@tuguidragos/qxlint>
- Open VSX: <https://open-vsx.org/extension/tuguidragos/qxlint>

---

Qiskit is a trademark of IBM Corporation. qxlint is an independent project and
is not affiliated with or endorsed by IBM.
