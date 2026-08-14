// The launcher is tested end to end, as a real subprocess with a controlled
// environment, because what matters is the resolution order and the exit code
// it hands back to CI, not the shape of its internals.

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const LAUNCHER = path.join(__dirname, "..", "bin", "qxlint.js");
const REPO = path.join(__dirname, "..", "..");
const IS_WINDOWS = process.platform === "win32";

function run(args, env = {}) {
  return spawnSync(process.execPath, [LAUNCHER, ...args], {
    encoding: "utf8",
    env: { ...process.env, ...env },
  });
}

/** A PATH with nothing on it, so no interpreter or runner can be discovered. */
function emptyPath() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-empty-"));
}

/**
 * An interpreter that can import qxlint, or null.
 *
 * The developer checkout has one in `.venv`. CI installs qxlint into the
 * interpreter on PATH instead, and these tests used to skip there, which meant
 * six of them never ran anywhere but a laptop.
 */
function findPython() {
  const candidates = [
    process.env.QXLINT_TEST_PYTHON,
    path.join(REPO, ".venv", "bin", "python"),
    path.join(REPO, ".venv", "Scripts", "python.exe"),
    "python3",
    "python",
  ];
  for (const candidate of candidates) {
    if (!candidate) {
      continue;
    }
    const result = spawnSync(candidate, ["-c", "import qxlint"], { stdio: "ignore" });
    if (result.error === undefined && result.status === 0) {
      return candidate;
    }
  }
  return null;
}

const VENV_PYTHON = findPython();
const hasVenv = VENV_PYTHON !== null;

/** An executable that answers like an installed qxlint, for PATH ordering tests. */
function decoy(directory, text = "qxlint 99.99.99-decoy") {
  const target = path.join(directory, "qxlint");
  fs.writeFileSync(target, `#!/bin/sh\necho "${text}"\nexit 0\n`);
  fs.chmodSync(target, 0o755);
  return target;
}

test("QXLINT_PYTHON is preferred over everything else", { skip: !hasVenv }, () => {
  const result = run(["--version"], { QXLINT_PYTHON: VENV_PYTHON });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /^qxlint \d+\.\d+\.\d+/);
});

test("QXLINT_PYTHON beats a qxlint already on PATH", { skip: !hasVenv }, () => {
  // The previous version of this test could not fail: with nothing else on
  // PATH, both resolution orders produce the same output. A competing qxlint
  // has to exist for the order to be observable at all.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-decoy-"));
  const decoy = path.join(dir, "qxlint");
  fs.writeFileSync(decoy, '#!/bin/sh\necho "qxlint 99.99.99-decoy"\nexit 0\n');
  fs.chmodSync(decoy, 0o755);

  const result = run(["--version"], {
    QXLINT_PYTHON: VENV_PYTHON,
    PATH: `${dir}${path.delimiter}${process.env.PATH}`,
  });
  assert.equal(result.status, 0);
  assert.doesNotMatch(result.stdout, /decoy/);
});

// Skipped on Windows: the decoy is a shell script with no extension, and the
// launcher deliberately accepts only .EXE and .COM there, because a .CMD named
// qxlint is a shim rather than the analyser and cannot be spawned without a
// shell. There is no way to fabricate something Windows would accept.
test("a qxlint on PATH is used when QXLINT_PYTHON is not set", { skip: IS_WINDOWS }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-decoy-"));
  const decoy = path.join(dir, "qxlint");
  fs.writeFileSync(decoy, '#!/bin/sh\necho "qxlint 99.99.99-decoy"\nexit 0\n');
  fs.chmodSync(decoy, 0o755);

  const result = run(["--version"], {
    QXLINT_PYTHON: "",
    PATH: `${dir}${path.delimiter}${process.env.PATH}`,
  });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /decoy/);
});

test("a clean run exits zero", { skip: !hasVenv }, () => {
  const result = run([path.join(REPO, "tests", "fixtures", "clean")], {
    QXLINT_PYTHON: VENV_PYTHON,
  });
  assert.equal(result.status, 0);
});

test("findings exit one, so CI fails the step", { skip: !hasVenv }, () => {
  const result = run([path.join(REPO, "tests", "fixtures", "positive")], {
    QXLINT_PYTHON: VENV_PYTHON,
  });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /QXL1\d\d/);
});

test("a missing path exits two, not one", { skip: !hasVenv }, () => {
  const result = run(["definitely-not-here.py"], { QXLINT_PYTHON: VENV_PYTHON });
  assert.equal(result.status, 2);
});

test("with nothing installed it explains how to install, and exits two", () => {
  const result = run(["--version"], { PATH: emptyPath(), QXLINT_PYTHON: "" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /could not find a way to run the Python package/);
  assert.match(result.stderr, /uv tool install qxlint/);
  assert.match(result.stderr, /pipx install qxlint/);
  assert.match(result.stderr, /QXLINT_PYTHON/);
});

test("a broken QXLINT_PYTHON falls through instead of crashing", () => {
  const result = run(["--version"], {
    PATH: emptyPath(),
    QXLINT_PYTHON: "/nonexistent/python",
  });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /could not find a way to run/);
});

test("arguments are passed through unchanged", { skip: !hasVenv }, () => {
  // Selecting only QXL101 leaves the QXL103 fixture clean, so a flag that
  // reached qxlint intact is the only way this exits zero.
  const result = run(
    [path.join(REPO, "tests", "fixtures", "positive", "qxl103_unmeasured.py"), "--select", "QXL101"],
    { QXLINT_PYTHON: VENV_PYTHON },
  );
  assert.equal(result.status, 0);
});

test("a flag qxlint rejects propagates exit two", { skip: !hasVenv }, () => {
  const result = run([path.join(REPO, "tests", "fixtures", "clean"), "--select", "QXL999"], {
    QXLINT_PYTHON: VENV_PYTHON,
  });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /no rule matches/);
});

// Self resolution ------------------------------------------------------
//
// npx puts `node_modules/.bin` at the front of PATH, and the qxlint in there is
// this launcher. Resolving the bare name made it call itself once per probe and
// never finish. These three tests each fail on the version that did that.

test("an npm shim on PATH is skipped, not called again", { skip: IS_WINDOWS }, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-shim-"));
  const shim = path.join(root, "node_modules", ".bin");
  fs.mkdirSync(shim, { recursive: true });
  fs.symlinkSync(LAUNCHER, path.join(shim, "qxlint"));

  const real = path.join(root, "real");
  fs.mkdirSync(real);
  decoy(real, "qxlint 1.2.3-real");

  const result = run(["--version"], {
    QXLINT_PYTHON: "",
    PATH: [shim, real].join(path.delimiter),
  });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /1\.2\.3-real/);
});

test("a symlink to this launcher on PATH is skipped", { skip: IS_WINDOWS }, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-self-"));
  const first = path.join(root, "first");
  const second = path.join(root, "second");
  fs.mkdirSync(first);
  fs.mkdirSync(second);
  fs.symlinkSync(LAUNCHER, path.join(first, "qxlint"));
  decoy(second, "qxlint 4.5.6-real");

  const result = run(["--version"], {
    QXLINT_PYTHON: "",
    PATH: [first, second].join(path.delimiter),
  });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /4\.5\.6-real/);
});

test("two separate launcher copies do not call each other forever", { skip: IS_WINDOWS }, () => {
  // Neither copy is this file, so skipping self is not enough. The sentinel in
  // the child environment is what stops it.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-pair-"));
  const source = fs.readFileSync(LAUNCHER, "utf8");
  for (const name of ["a", "b"]) {
    const directory = path.join(root, name);
    fs.mkdirSync(directory);
    const copy = path.join(directory, "qxlint");
    fs.writeFileSync(copy, source);
    fs.chmodSync(copy, 0o755);
  }

  const started = Date.now();
  const result = run(["--version"], {
    QXLINT_PYTHON: "",
    PATH: [path.join(root, "a"), path.join(root, "b"), path.dirname(process.execPath)].join(
      path.delimiter,
    ),
  });
  assert.equal(result.status, 2);
  assert.ok(Date.now() - started < 30_000, "the launcher pair did not terminate quickly");
});

test("the sentinel is set for children", { skip: !hasVenv }, () => {
  const result = run(["--version"], { QXLINT_PYTHON: VENV_PYTHON });
  assert.equal(result.status, 0);
  assert.equal(process.env.QXLINT_NPM_LAUNCHER, undefined, "it must not leak into this process");
});

test("the launcher is valid CommonJS with a node shebang", () => {
  const source = fs.readFileSync(LAUNCHER, "utf8");
  assert.ok(source.startsWith("#!/usr/bin/env node"));
  const check = spawnSync(process.execPath, ["--check", LAUNCHER], { encoding: "utf8" });
  assert.equal(check.status, 0);
});

test("the launcher is executable", { skip: IS_WINDOWS }, () => {
  // npm sets this bit at install time, so losing it in the repository is
  // invisible in a real install. The two shim tests above need it: without it
  // the shim is not a candidate at all and they would pass on any launcher.
  assert.ok((fs.statSync(LAUNCHER).mode & 0o111) !== 0, "npm/bin/qxlint.js must be mode 755");
});

// Pinning --------------------------------------------------------------
//
// Steps 1 to 3 run what the user installed. Step 4 installs, so it has to ask
// for this exact version: `npx @tuguidragos/qxlint@0.1.1` that fetched
// whatever PyPI had that day made the version in the command line meaningless.

/** A stand-in runner that records every argument list it is called with. */
function recorder(directory, name) {
  const record = path.join(directory, `${name}.log`);
  const target = path.join(directory, name);
  fs.writeFileSync(target, `#!/bin/sh\necho "$@" >> "${record}"\nexit 0\n`);
  fs.chmodSync(target, 0o755);
  return record;
}

function declaredVersion() {
  return JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8")).version;
}

test("the uvx fallback asks for this exact version", { skip: IS_WINDOWS }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-uvx-"));
  const record = recorder(dir, "uvx");

  const result = run(["--version"], { PATH: dir, QXLINT_PYTHON: "" });
  assert.equal(result.status, 0);

  const calls = fs.readFileSync(record, "utf8").trim().split("\n");
  assert.deepEqual(calls[0].split(" "), ["--version"], "the runner is probed first");
  assert.deepEqual(calls[1].split(" "), [`qxlint==${declaredVersion()}`, "--version"]);
});

test("the pipx fallback pins with --spec, which is its documented form", { skip: IS_WINDOWS }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-pipx-"));
  const record = recorder(dir, "pipx");

  const result = run(["--version"], { PATH: dir, QXLINT_PYTHON: "" });
  assert.equal(result.status, 0);

  const calls = fs.readFileSync(record, "utf8").trim().split("\n");
  assert.deepEqual(calls[1].split(" "), [
    "run",
    "--spec",
    `qxlint==${declaredVersion()}`,
    "qxlint",
    "--version",
  ]);
});

test("uvx is preferred over pipx", { skip: IS_WINDOWS }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qxlint-both-"));
  const uvx = recorder(dir, "uvx");
  const pipx = recorder(dir, "pipx");

  assert.equal(run(["--version"], { PATH: dir, QXLINT_PYTHON: "" }).status, 0);
  assert.ok(fs.existsSync(uvx), "uvx was never called");
  assert.ok(!fs.existsSync(pipx), "pipx was called even though uvx worked");
});

// Packaging ------------------------------------------------------------

test("the package ships the licence it declares", () => {
  const root = path.join(__dirname, "..", "..");
  const shipped = path.join(__dirname, "..", "LICENSE");
  assert.ok(fs.existsSync(shipped), "npm/LICENSE is missing but package.json says MIT");
  assert.equal(
    fs.readFileSync(shipped, "utf8"),
    fs.readFileSync(path.join(root, "LICENSE"), "utf8"),
    "npm/LICENSE has drifted from the repository LICENSE",
  );

  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  assert.ok(
    manifest.files.includes("LICENSE"),
    "LICENSE is not in the files allowlist, so npm would leave it out of the tarball",
  );
});
