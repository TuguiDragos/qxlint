// Runs inside the extension host, so these are the diagnostics the editor
// actually shows. core.test.ts covers the pure functions; this covers the
// wiring around them, which is where a coordinate or a cell index goes wrong.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");

const WORKSPACE = process.env.QXLINT_TEST_WORKSPACE;
const QXLINT = process.env.QXLINT_TEST_PATH;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function ours(uri) {
  return vscode.languages.getDiagnostics(uri).filter((d) => d.source === "qxlint");
}

async function waitFor(check, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = check();
    if (value !== undefined && value !== null && value !== false) {
      return value;
    }
    if (Date.now() > deadline) {
      return null;
    }
    await sleep(250);
  }
}

async function configure(settings) {
  const target = vscode.ConfigurationTarget.Workspace;
  const config = vscode.workspace.getConfiguration("qxlint");
  for (const [key, value] of Object.entries(settings)) {
    await config.update(key, value, target);
  }
  await sleep(500);
}

async function run() {
  const extension = vscode.extensions.getExtension("tuguidragos.qxlint");
  assert.ok(extension, "the extension was not discovered");
  await extension.activate();
  assert.ok(extension.isActive, "the extension did not activate");

  // Nothing from ms-python is installed in this run, so reaching here proves
  // qxlint activates without the Python extension. Everything below then runs
  // against the analyser named by qxlint.path.
  assert.equal(
    vscode.extensions.getExtension("ms-python.python"),
    undefined,
    "the Python extension is present, so this run does not prove independence from it",
  );

  await configure({ enable: true, path: QXLINT, run: "onSave", select: "", ignore: "" });

  // A finding lands on the right characters ---------------------------------
  const badUri = vscode.Uri.file(path.join(WORKSPACE, "bad.py"));
  const badDoc = await vscode.workspace.openTextDocument(badUri);
  await vscode.window.showTextDocument(badDoc);

  const found = await waitFor(() => {
    const items = ours(badUri);
    return items.length > 0 ? items : null;
  });
  assert.ok(found, "no qxlint diagnostic appeared for bad.py");
  assert.equal(found.length, 1);

  const [diagnostic] = found;
  assert.equal(String(diagnostic.code?.value ?? diagnostic.code), "QXL101");
  assert.equal(diagnostic.severity, vscode.DiagnosticSeverity.Error);
  // qxlint reports line 9 column 10, one based on both axes.
  assert.equal(diagnostic.range.start.line, 8);
  assert.equal(diagnostic.range.start.character, 9);
  assert.equal(badDoc.getText(diagnostic.range), "result.get_counts");
  assert.match(String(diagnostic.code?.target ?? ""), /\/docs\/rules\/qxl101\.md$/);

  // A clean file produces nothing -------------------------------------------
  const cleanUri = vscode.Uri.file(path.join(WORKSPACE, "clean.py"));
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(cleanUri));
  await sleep(5000);
  assert.equal(ours(cleanUri).length, 0, "a clean file produced diagnostics");

  // A notebook finding lands on the cell, not on the .ipynb ------------------
  const notebookUri = vscode.Uri.file(path.join(WORKSPACE, "notebook.ipynb"));
  const notebook = await vscode.workspace.openNotebookDocument(notebookUri);
  await vscode.window.showNotebookDocument(notebook);
  const cellDiagnostics = await waitFor(() => {
    const all = vscode.languages
      .getDiagnostics()
      .filter(([uri]) => uri.scheme === "vscode-notebook-cell")
      .flatMap(([uri, items]) =>
        items.filter((d) => d.source === "qxlint").map((d) => ({ uri, diagnostic: d })),
      );
    return all.length > 0 ? all : null;
  });
  assert.ok(cellDiagnostics, "no diagnostic reached a notebook cell");
  assert.equal(ours(notebookUri).length, 0, "a diagnostic was placed on the .ipynb file itself");
  assert.equal(
    String(cellDiagnostics[0].diagnostic.code?.value ?? ""),
    "QXL101",
    "the notebook finding is not the expected rule",
  );

  // The commands are registered ---------------------------------------------
  const commands = await vscode.commands.getCommands(true);
  for (const command of ["qxlint.lintWorkspace", "qxlint.showOutput", "qxlint.restart"]) {
    assert.ok(commands.includes(command), `${command} is not registered`);
  }

  // Settings reach the analyser ---------------------------------------------
  await configure({ ignore: "QXL101" });
  const cleared = await waitFor(() => (ours(badUri).length === 0 ? true : null), 30_000);
  assert.ok(cleared, "qxlint.ignore did not reach the analyser");
  await configure({ ignore: "" });

  // Disabling clears everything ---------------------------------------------
  await waitFor(() => (ours(badUri).length > 0 ? true : null), 30_000);
  await configure({ enable: false });
  const disabled = await waitFor(() => (ours(badUri).length === 0 ? true : null), 30_000);
  assert.ok(disabled, "qxlint.enable false left diagnostics behind");
  await configure({ enable: true });

  // qxlint.restart clears and re-lints --------------------------------------
  // The close path is not asserted here: VS Code keeps a .py TextDocument open
  // for a while after its editor is gone, so onDidCloseTextDocument does not
  // reliably arrive during a test run. restart goes through the same clear and
  // re-schedule code.
  await waitFor(() => (ours(badUri).length > 0 ? true : null), 30_000);
  await vscode.commands.executeCommand("qxlint.restart");
  const back = await waitFor(() => (ours(badUri).length === 1 ? true : null), 30_000);
  assert.ok(back, "qxlint.restart did not re-report the finding");

  // An unsaved buffer is what gets analysed ---------------------------------
  // The whole point of onType: the file on disk still has the defect, so a
  // cleared diagnostic can only come from the buffer reaching the analyser.
  await configure({ run: "onType" });
  const editor = await vscode.window.showTextDocument(badDoc);
  const original = badDoc.getText();
  const whole = new vscode.Range(badDoc.positionAt(0), badDoc.positionAt(original.length));

  await editor.edit((builder) => builder.replace(whole, "value = 1\n"));
  assert.ok(badDoc.isDirty, "the edit reached disk, so this proves nothing about buffers");
  assert.match(
    fs.readFileSync(badUri.fsPath, "utf8"),
    /get_counts/,
    "the file on disk lost the defect, so this proves nothing about buffers",
  );
  const clearedFromBuffer = await waitFor(() => (ours(badUri).length === 0 ? true : null), 30_000);
  assert.ok(clearedFromBuffer, "the unsaved buffer was not analysed; the saved file was");

  const edited = badDoc.getText();
  await editor.edit((builder) =>
    builder.replace(new vscode.Range(badDoc.positionAt(0), badDoc.positionAt(edited.length)), original),
  );
  const backFromBuffer = await waitFor(() => (ours(badUri).length === 1 ? true : null), 30_000);
  assert.ok(backFromBuffer, "putting the defect back in the buffer did not report it again");

  await vscode.commands.executeCommand("workbench.action.files.revert");
  await configure({ run: "onSave" });

  fs.writeFileSync(path.join(WORKSPACE, "..", "e2e-passed"), "ok\n");
}

module.exports = { run };
