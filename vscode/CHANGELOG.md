# Changelog

The extension, the [`qxlint` Python package](https://pypi.org/project/qxlint/)
and the
[`@tuguidragos/qxlint` npm launcher](https://www.npmjs.com/package/@tuguidragos/qxlint)
are released together from one tag and share a version number. Changes to the
rules themselves are listed with
[the analyser's releases](https://github.com/TuguiDragos/qxlint/releases).

## 0.1.1

The extension itself is unchanged.

### Added

- **Published to [Open VSX](https://open-vsx.org/extension/tuguidragos/qxlint)**,
  so it installs from VSCodium, Cursor, Windsurf, Gitpod and Theia, which cannot
  use the Microsoft Marketplace. Same `.vsix`, same version.

## 0.1.0

First release.

### Added

- **Diagnostics for every qxlint rule**, in `.py` files and in `.ipynb` cells.
  Notebook findings land on the line inside the cell you are looking at, not on
  a line of the notebook's JSON.
- **Rule codes link to their documentation.** Each code in the Problems panel
  carries the URL of its rule page, which states what the rule checks and, for
  every rule, when the pattern is legitimate.
- **Uses the interpreter the Python extension has selected**, and re-lints when
  you switch environments. `qxlint.path` overrides it when the analyser lives
  somewhere else.
- **The same CLI, the same configuration.** The extension shells out to the
  qxlint command and it reads `[tool.qxlint]` from your project itself, so the
  editor and CI cannot disagree about which rules ran or which Qiskit version
  was targeted.
- **Settings** for `enable`, `run` (`onSave` or `onType`), `path`, `select`,
  `ignore`, `targetQiskit`, `targetRuntime` and extra `args`.
- **Commands**: *qxlint: Lint workspace*, *qxlint: Re-lint open files* and
  *qxlint: Show output*.
- Exit code 2 from the analyser is surfaced as a problem with the tool rather
  than as an empty result, so a broken configuration is visible instead of
  looking like a clean project.

### Requirements

The analyser is the Python package, installed into the environment you have
selected:

```
pip install qxlint
```

The Python extension is used when it is there, to pick up the interpreter you
have selected, and is not required: `qxlint.path`, or a `qxlint` on `PATH`, is
enough. The extension does not run in virtual or untrusted workspaces, because
it runs a program from your workspace's environment.
