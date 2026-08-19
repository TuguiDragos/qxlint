<p align="center">
  <img src="https://raw.githubusercontent.com/TuguiDragos/qxlint/main/readme-assets/png/qxlint-icon-256.png" alt="qxlint" width="88" />
</p>

<h1 align="center">qxlint (npm)</h1>

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
  <a href="https://docs.pytest.org/"><img alt="1052 tests" src="https://img.shields.io/badge/tests-1052-161826?style=flat&logo=pytest&logoColor=9184D9" /></a>
</p>

---
Deterministic static checks for Qiskit Primitives V2 workflows.

```bash
npx @tuguidragos/qxlint .
```

## What this package is

A launcher, not a port. qxlint analyses Python source, so the analyser itself is
the Python package [`qxlint`](https://pypi.org/project/qxlint/). This package
exists so a JavaScript toolchain can call it without a separate Python setup
step, and so `npx @tuguidragos/qxlint` behaves like every other linter in a JS
project.

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

The launcher tries, in order:

1. `QXLINT_PYTHON`, if it is set and can import qxlint.
2. A `qxlint` already on PATH. `node_modules/.bin` is skipped, because the
   `qxlint` in there is this launcher.
3. A Python interpreter that can import qxlint: `python3`, then `python`, and
   on Windows `py` as well.
4. `uvx qxlint==<this version>`, then `pipx run --spec qxlint==<this version>
   qxlint`.

If none of them works it prints the install options and exits 2.

Steps 1 to 3 run whatever you installed, which is the point of them. Step 4
installs, so it pins: running `npx @tuguidragos/qxlint@0.3.0` and getting some
other analyser would make the version in the command line meaningless.

Exit codes pass through unchanged: `0` clean, `1` findings, `2` qxlint could not
run. That is what makes it usable as a CI gate:

```yaml
- run: npx @tuguidragos/qxlint@0.3.0 src
```

## What it checks

Misuse of the Qiskit Primitives V2 API that the language cannot catch and a
test often does not either, because the wrong code frequently runs and returns
something that looks like a result:

- `get_counts()` on a `PrimitiveResult`, where counts live on the `BitArray`
  one level down.
- `quasi_dists` read from a V2 result, where the attribute no longer exists.
- A circuit with no measurement handed to a Sampler, which returns an empty
  data bin and a warning that is easy to miss.
- A measured circuit handed to a `StatevectorEstimator`, which raises.
- `channel="ibm_quantum"` against a runtime release that removed it.

Every rule reports only what it can prove. Where the analyser cannot decide,
it says nothing rather than guessing, because a linter that cries wolf gets
switched off.

## If you are already using Python

Use the Python package directly. `uvx qxlint .` needs no installation at all and
skips this wrapper entirely. This package is only worth the extra hop when the
project is driven from `package.json`.

## Supply chain

- Zero dependencies, and no install, preinstall or postinstall script.
- Published from a tagged GitHub Actions run with npm provenance, so the
  registry records which workflow and which commit produced the tarball.
- Four files in the tarball: the launcher, the manifest, this README and the
  licence.

## Links

- Documentation and rules: <https://github.com/TuguiDragos/qxlint>
- This package on npm: <https://www.npmjs.com/package/@tuguidragos/qxlint>
- PyPI package, the analyser itself: <https://pypi.org/project/qxlint/>
- VS Code extension: <https://marketplace.visualstudio.com/items?itemName=tuguidragos.qxlint>

Qiskit is a trademark of IBM Corporation. qxlint is an independent project and is
not affiliated with or endorsed by IBM.
