# Changelog

The extension, the [`qxlint` Python package](https://pypi.org/project/qxlint/)
and the
[`@tuguidragos/qxlint` npm launcher](https://www.npmjs.com/package/@tuguidragos/qxlint)
are released together from one tag and share a version number. Changes to the
rules themselves are listed with
[the analyser's releases](https://github.com/TuguiDragos/qxlint/releases).

## Unreleased

### Fixed

- **`--statistics` in `qxlint.args` no longer makes every file read clean.** That
  flag emits a summary payload that carries `schemaVersion` and a rule histogram
  and no `findings` key at all. The parser treated a missing `findings` key as
  zero findings, so the file came back clean and nothing said otherwise. A
  payload without `findings` is no longer a lint payload, and a summary payload
  is reported with the reason and the flag to remove.

## 0.3.0

### Fixed

- **A squiggle no longer slides left on a line containing emoji.** qxlint counts
  characters and `vscode.Position` counts UTF-16 code units, which agree until a
  character outside the Basic Multilingual Plane appears earlier on the same line.
  The extension now converts the columns against the document text, so the
  highlight covers the call rather than starting two units before it. Notebook
  cells take the same path and are fixed with it.

## 0.2.0

### Fixed

- **The analyser can no longer be shadowed by the workspace.** The extension
  runs `<interpreter> -m qxlint` with the project as the working directory, and
  a `qxlint` package sitting in that project was imported and executed instead
  of the installed one. The child process now runs with `PYTHONSAFEPATH=1`, so
  the working directory never reaches `sys.path`. `-I` would also have fixed it
  and was rejected: it disables user site-packages too, which would break a
  `pip install --user qxlint`.
- **A missing analyser no longer looks like a clean project.** `python -m
  qxlint` exits 1 with nothing on stdout when the module is not installed, and
  only exit 2 was treated as a failure, so an empty result was read as no
  findings. A run now counts only when it produced a qxlint payload.
- **Diagnostics follow the buffer, not the file on disk.** `onType` re-ran the
  analyser on the saved file, so unsaved edits were never reflected. The buffer
  is sent to the analyser instead, notebooks included. An analyser older than
  0.2.0 does not accept it; the extension notices and falls back to the file.

### Added

- **A status bar item** showing the engine version that produced the current
  diagnostics, or that no engine was found.
- The display name is now **qxlint - Qiskit Linter**, so the listing says what
  the extension is.

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
