<p align="center">
  <img src="https://raw.githubusercontent.com/TuguiDragos/qxlint/main/readme-assets/png/qxlint-icon-256.png" alt="qxlint" width="88" />
</p>

<h1 align="center">qxlint (npm)</h1>

<p align="center">
  <a href="https://pypi.org/project/qxlint/"><img alt="PyPI downloads a month" src="https://img.shields.io/pypi/dm/qxlint?style=flat&color=161826&label=PyPI&logo=pypi&logoColor=9184D9" /></a>
  <a href="https://www.npmjs.com/package/qxlint"><img alt="npm downloads a month" src="https://img.shields.io/npm/dm/qxlint?style=flat&color=161826&label=npm&logo=npm&logoColor=9184D9" /></a>
  <a href="https://github.com/TuguiDragos/qxlint/blob/main/LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/License-MIT-161826?style=flat" /></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.11 to 3.14" src="https://img.shields.io/badge/Python-3.11%20--%203.14-161826?style=flat&logo=python&logoColor=9184D9" /></a>
  <a href="https://www.ibm.com/quantum/qiskit"><img alt="Qiskit optional" src="https://img.shields.io/badge/Qiskit-optional-161826?style=flat&logo=qiskit&logoColor=9184D9" /></a>
  <a href="https://jupyter.org/"><img alt="Jupyter notebooks" src="https://img.shields.io/badge/Jupyter-notebooks-161826?style=flat&logo=jupyter&logoColor=9184D9" /></a>
  <a href="https://tuguidragos.com"><img alt="tuguidragos.com" src="https://img.shields.io/badge/tuguidragos.com-161826?style=flat&logo=safari&logoColor=9184D9" /></a>
  <a href="https://docs.pytest.org/"><img alt="903 tests" src="https://img.shields.io/badge/tests-903-161826?style=flat&logo=pytest&logoColor=9184D9" /></a>
</p>

---
Deterministic static checks for Qiskit Primitives V2 workflows.

```bash
npx qxlint .
```

## What this package is

A launcher, not a port. qxlint analyses Python source, so the analyser itself is
the Python package [`qxlint`](https://pypi.org/project/qxlint/). This package
exists so a JavaScript toolchain can call it without a separate Python setup
step, and so `npx qxlint` behaves like every other linter in a JS project.

It bundles no Python runtime and runs no install script.

## Requirements

Python 3.11 or newer, and qxlint reachable in one of these ways:

```bash
uv tool install qxlint
```

```bash
pipx install qxlint
```

```bash
pip install qxlint
```

The launcher tries, in order: `QXLINT_PYTHON` if set, a `qxlint` already on
PATH, a Python interpreter that can import `qxlint`, then `uvx qxlint`, then
`pipx run qxlint`. If none works it prints the install options and exits 2.

Exit codes pass through unchanged: `0` clean, `1` findings, `2` qxlint could not
run.

## If you are already using Python

Use the Python package directly. `uvx qxlint .` needs no installation at all and
skips this wrapper entirely.

## Links

- Documentation and rules: <https://github.com/TuguiDragos/qxlint>
- This package on npm: <https://www.npmjs.com/package/qxlint>
- PyPI package, the analyser itself: <https://pypi.org/project/qxlint/>
- VS Code extension: <https://marketplace.visualstudio.com/items?itemName=tuguidragos.qxlint>

Qiskit is a trademark of IBM Corporation. qxlint is an independent project and is
not affiliated with or endorsed by IBM.
