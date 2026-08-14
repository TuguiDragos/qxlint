#!/usr/bin/env node
// Thin launcher. qxlint is a Python tool; this package exists so that people
// working in a JavaScript toolchain can run `npx @tuguidragos/qxlint` without
// learning the Python packaging story first. It does not bundle a Python
// runtime.
//
// Resolution order, first that works wins:
//   1. QXLINT_PYTHON, if set
//   2. an already installed `qxlint` on PATH
//   3. a Python interpreter that can import qxlint
//   4. `uvx qxlint==<this version>`, then `pipx run --spec qxlint==<this version>`
//
// Steps 1 to 3 run whatever the user installed, which is the point of them.
// Step 4 installs, so it pins: `npx @tuguidragos/qxlint@0.2.0` that fetched
// whatever PyPI had that day meant the version in the command line said
// nothing about the analyser that ran.
//
// Exit codes are propagated unchanged, which is what makes this usable in CI.

"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ARGS = process.argv.slice(2);
const IS_WINDOWS = process.platform === "win32";

// Set on every child. If it is already set when this launcher starts, a parent
// launcher is above us and step 2 is skipped, so two launchers on PATH cannot
// call each other forever.
const SENTINEL = "QXLINT_NPM_LAUNCHER";
const NESTED = process.env[SENTINEL] === "1";

const CHILD_ENV = { ...process.env, [SENTINEL]: "1" };

function run(command, args, options) {
  return spawnSync(command, args, {
    shell: false,
    stdio: "inherit",
    env: CHILD_ENV,
    ...options,
  });
}

function probe(command, args) {
  const result = spawnSync(command, args, { shell: false, stdio: "ignore", env: CHILD_ENV });
  return result.error === undefined && result.status === 0;
}

function candidatePythons() {
  return IS_WINDOWS ? ["python", "py", "python3"] : ["python3", "python"];
}

/**
 * The pip requirement a runner should install: the exact version this launcher
 * was published with. Falls back to the bare name if the manifest is somehow
 * unreadable, since an unpinned run beats no run at all.
 */
function requirement() {
  try {
    const { version } = require("../package.json");
    return typeof version === "string" && version ? `qxlint==${version}` : "qxlint";
  } catch {
    return "qxlint";
  }
}

let selfPath = null;
try {
  selfPath = fs.realpathSync(__filename);
} catch {
  selfPath = __filename;
}

/** True for a `node_modules/.bin` directory, which only ever holds npm shims. */
function isPackageBin(directory) {
  return (
    path.basename(directory) === ".bin" &&
    path.basename(path.dirname(directory)) === "node_modules"
  );
}

function isSelf(candidate) {
  try {
    return fs.realpathSync(candidate) === selfPath;
  } catch {
    return false;
  }
}

function isRunnableFile(candidate) {
  try {
    if (!fs.statSync(candidate).isFile()) {
      return false;
    }
    fs.accessSync(candidate, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * Absolute path to a real `qxlint` on PATH, or null.
 *
 * npx puts `node_modules/.bin` at the front of PATH, and this launcher is the
 * `qxlint` in there. Letting spawnSync resolve the bare name made the launcher
 * call itself, once per probe, without ever terminating. So PATH is walked
 * here, package shim directories are skipped, and so is this file.
 *
 * On Windows only `.EXE` and `.COM` are accepted: `.CMD` and `.BAT` cannot be
 * spawned without a shell, and a `.CMD` named qxlint is a shim rather than the
 * analyser anyway.
 */
function resolveOnPath(name) {
  const entries = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  const extensions = IS_WINDOWS ? [".EXE", ".COM"] : [""];
  for (const entry of entries) {
    if (isPackageBin(entry)) {
      continue;
    }
    for (const extension of extensions) {
      const candidate = path.join(entry, name + extension);
      if (isRunnableFile(candidate) && !isSelf(candidate)) {
        return candidate;
      }
    }
  }
  return null;
}

function launch() {
  // QXLINT_PYTHON is asked first, which is what the README and the comment
  // above both promise. It used to come after the PATH lookup, so someone with
  // an old global qxlint who pointed this at their project venv silently got
  // the old one, and the editor and CI could then disagree.
  const explicit = process.env.QXLINT_PYTHON;
  if (explicit && probe(explicit, ["-c", "import qxlint"])) {
    return run(explicit, ["-m", "qxlint", ...ARGS]);
  }

  const installed = NESTED ? null : resolveOnPath("qxlint");
  if (installed !== null && probe(installed, ["--version"])) {
    return run(installed, ARGS);
  }

  for (const python of candidatePythons()) {
    if (probe(python, ["-c", "import qxlint"])) {
      return run(python, ["-m", "qxlint", ...ARGS]);
    }
  }

  const spec = requirement();
  for (const [runner, runnerArgs] of [
    ["uvx", [spec]],
    ["pipx", ["run", "--spec", spec, "qxlint"]],
  ]) {
    if (probe(runner, ["--version"])) {
      return run(runner, [...runnerArgs, ...ARGS]);
    }
  }

  return null;
}

const result = launch();

if (result === null) {
  process.stderr.write(
    [
      "qxlint: could not find a way to run the Python package.",
      "",
      "qxlint analyses Python source, so it needs Python available. Any of these works:",
      "",
      "  uv tool install qxlint      # then the launcher finds it",
      "  pipx install qxlint",
      "  pip install qxlint",
      "",
      "Set QXLINT_PYTHON to point at a specific interpreter if it is not on PATH.",
      "",
    ].join("\n"),
  );
  process.exit(2);
}

if (result.error) {
  process.stderr.write(`qxlint: failed to start: ${result.error.message}\n`);
  process.exit(2);
}

process.exit(result.status === null ? 2 : result.status);
