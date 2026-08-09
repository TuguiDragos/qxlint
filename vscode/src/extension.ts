// qxlint VS Code extension.
//
// The analyser is the Python package. This extension runs it and turns its JSON
// output into diagnostics, so there is exactly one implementation of every rule
// and the editor can never disagree with CI.
//
// Coordinate contract: qxlint emits 1-based lines and 1-based character columns
// with an exclusive end column. vscode.Position is zero-based on BOTH axes, so
// every coordinate is decremented once on the way in.

import { spawn } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";

import {
  codeCellPosition,
  isFailure,
  messageWithFix,
  parseFindings,
  ruleDocumentationUrl,
  severityOf,
  toZeroBasedRange,
  type QxlintFinding,
  type QxlintLocation,
} from "./core.js";

const SECTION = "qxlint";
const SOURCE = "qxlint";
const DOCS = "https://github.com/TuguiDragos/qxlint/blob/main/docs/rules";
const PYTHON_EXTENSION = "ms-python.python";
const NOTEBOOK_CELL_SCHEME = "vscode-notebook-cell";
const MAX_OUTPUT_BYTES = 64 * 1024 * 1024;

let diagnostics: vscode.DiagnosticCollection;
let log: vscode.LogOutputChannel;
const timers = new Map<string, NodeJS.Timeout>();
const inflight = new Map<string, AbortController>();

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  diagnostics = vscode.languages.createDiagnosticCollection(SECTION);
  log = vscode.window.createOutputChannel("qxlint", { log: true });
  context.subscriptions.push(diagnostics, log);

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((document) => schedule(document.uri)),
    vscode.workspace.onDidSaveTextDocument((document) => schedule(document.uri)),
    vscode.workspace.onDidCloseTextDocument((document) => forget(document.uri)),
    vscode.workspace.onDidChangeTextDocument((event) => {
      // A cell edit arrives here as well as on the notebook. Route it to the
      // notebook so the file is analysed once, with cross-cell context.
      if (event.document.uri.scheme === NOTEBOOK_CELL_SCHEME) {
        return;
      }
      if (runOnType(event.document.uri)) {
        schedule(event.document.uri, 400);
      }
    }),

    vscode.workspace.onDidOpenNotebookDocument((notebook) => schedule(notebook.uri)),
    vscode.workspace.onDidSaveNotebookDocument((notebook) => schedule(notebook.uri)),
    vscode.workspace.onDidCloseNotebookDocument((notebook) => forgetNotebook(notebook)),
    vscode.workspace.onDidChangeNotebookDocument((event) => {
      if (runOnType(event.notebook.uri)) {
        schedule(event.notebook.uri, 400);
      }
    }),

    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration(SECTION)) {
        refresh();
      }
    }),

    vscode.commands.registerCommand("qxlint.lintWorkspace", lintWorkspace),
    vscode.commands.registerCommand("qxlint.showOutput", () => log.show()),
    vscode.commands.registerCommand("qxlint.restart", refresh),
  );

  await watchInterpreter(context);
  refresh();
}

export function deactivate(): void {
  for (const timer of timers.values()) {
    clearTimeout(timer);
  }
  for (const controller of inflight.values()) {
    controller.abort();
  }
  timers.clear();
  inflight.clear();
}

// Settings ------------------------------------------------------------------

function settings(resource?: vscode.Uri): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration(SECTION, resource);
}

function runOnType(resource: vscode.Uri): boolean {
  return settings(resource).get<string>("run") === "onType";
}

function analysable(uri: vscode.Uri): boolean {
  if (uri.scheme !== "file") {
    return false;
  }
  const extension = path.extname(uri.fsPath).toLowerCase();
  return extension === ".py" || extension === ".ipynb";
}

// Scheduling ----------------------------------------------------------------

function schedule(uri: vscode.Uri, delay = 0): void {
  if (!analysable(uri) || !settings(uri).get<boolean>("enable", true)) {
    return;
  }
  const key = uri.toString();
  const existing = timers.get(key);
  if (existing) {
    clearTimeout(existing);
  }
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key);
      void lint(uri);
    }, delay),
  );
}

function forget(uri: vscode.Uri): void {
  diagnostics.delete(uri);
  inflight.get(uri.toString())?.abort();
}

function forgetNotebook(notebook: vscode.NotebookDocument): void {
  diagnostics.delete(notebook.uri);
  for (const cell of notebook.getCells()) {
    diagnostics.delete(cell.document.uri);
  }
}

function refresh(): void {
  diagnostics.clear();
  for (const document of vscode.workspace.textDocuments) {
    schedule(document.uri);
  }
  for (const notebook of vscode.workspace.notebookDocuments) {
    schedule(notebook.uri);
  }
}

async function lintWorkspace(): Promise<void> {
  const folders = vscode.workspace.workspaceFolders ?? [];
  if (folders.length === 0) {
    void vscode.window.showInformationMessage("qxlint: no workspace folder is open.");
    return;
  }
  diagnostics.clear();
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: "qxlint" },
    async () => {
      for (const folder of folders) {
        await lint(folder.uri, folder.uri);
      }
    },
  );
}

// Running -------------------------------------------------------------------

async function lint(target: vscode.Uri, folderOverride?: vscode.Uri): Promise<void> {
  const config = settings(target);
  if (!config.get<boolean>("enable", true)) {
    return;
  }

  const key = target.toString();
  inflight.get(key)?.abort();
  const controller = new AbortController();
  inflight.set(key, controller);

  const command = await resolveCommand(target);
  const folder = folderOverride ?? vscode.workspace.getWorkspaceFolder(target)?.uri;
  const cwd = folder?.fsPath ?? path.dirname(target.fsPath);

  const args = [
    ...command.args,
    target.fsPath,
    "--format",
    "json",
    "--no-color",
    ...flag("--select", config.get<string>("select")),
    ...flag("--ignore", config.get<string>("ignore")),
    ...flag("--target-qiskit", config.get<string>("targetQiskit")),
    ...flag("--target-runtime", config.get<string>("targetRuntime")),
    ...config.get<string[]>("args", []),
  ];

  log.debug(`${command.executable} ${args.join(" ")}`);

  let stdout: string;
  try {
    stdout = await execute(command.executable, args, cwd, controller.signal);
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      log.error(String(error));
    }
    return;
  } finally {
    if (inflight.get(key) === controller) {
      inflight.delete(key);
    }
  }

  let findings: QxlintFinding[];
  try {
    findings = parseFindings(stdout);
  } catch {
    log.error(`could not parse qxlint output: ${stdout.slice(0, 400)}`);
    return;
  }

  apply(target, findings, cwd);
}

function flag(name: string, value: string | undefined): string[] {
  return value && value.trim() ? [name, value.trim()] : [];
}

function execute(
  executable: string,
  args: string[],
  cwd: string,
  signal: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    // spawn, not execFile: execFile truncates at a 1 MB buffer and kills the
    // child, which would look like malformed qxlint output on a large project.
    const child = spawn(executable, args, { cwd, signal, windowsHide: true, shell: false });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    let size = 0;

    child.stdout.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size <= MAX_OUTPUT_BYTES) {
        out.push(chunk);
      }
    });
    child.stderr.on("data", (chunk: Buffer) => err.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const stderr = Buffer.concat(err).toString().trim();
      if (stderr) {
        log.warn(stderr);
      }
      // Exit 1 means findings, which is a normal result. Exit 2 means qxlint
      // could not run, and the reason is on stderr.
      if (isFailure(code)) {
        reject(new Error(stderr || "qxlint could not run"));
        return;
      }
      resolve(Buffer.concat(out).toString());
    });
  });
}

interface Command {
  executable: string;
  args: string[];
}

async function resolveCommand(resource: vscode.Uri): Promise<Command> {
  const configured = settings(resource).get<string>("path");
  if (configured && configured.trim()) {
    return { executable: configured.trim(), args: [] };
  }
  const interpreter = await interpreterFor(resource);
  if (interpreter) {
    // `<interpreter> -m qxlint` also sidesteps the Windows .cmd shim problem
    // that spawning a bare `qxlint` would hit.
    return { executable: interpreter, args: ["-m", "qxlint"] };
  }
  return { executable: "qxlint", args: [] };
}

async function interpreterFor(resource: vscode.Uri): Promise<string | undefined> {
  // Use whatever interpreter the Python extension has selected, so qxlint runs
  // in the project's environment rather than a random global one. The API is
  // consumed defensively rather than through a typed dependency, so a change in
  // its shape degrades to "not found" instead of breaking the extension.
  const extension = vscode.extensions.getExtension(PYTHON_EXTENSION);
  if (!extension) {
    return undefined;
  }
  try {
    const api = extension.isActive ? extension.exports : await extension.activate();
    const environments = api?.environments;
    if (!environments) {
      return undefined;
    }
    const active = environments.getActiveEnvironmentPath?.(resource);
    const details = active ? await environments.resolveEnvironment?.(active) : undefined;
    return details?.executable?.uri?.fsPath ?? details?.path ?? active?.path;
  } catch (error) {
    log.debug(`python extension lookup failed: ${String(error)}`);
    return undefined;
  }
}

async function watchInterpreter(context: vscode.ExtensionContext): Promise<void> {
  const extension = vscode.extensions.getExtension(PYTHON_EXTENSION);
  if (!extension) {
    return;
  }
  try {
    const api = extension.isActive ? extension.exports : await extension.activate();
    const listener = api?.environments?.onDidChangeActiveEnvironmentPath;
    if (typeof listener === "function") {
      context.subscriptions.push(listener(() => refresh()));
    }
  } catch (error) {
    log.debug(`could not watch the interpreter: ${String(error)}`);
  }
}

// Diagnostics ---------------------------------------------------------------

function apply(target: vscode.Uri, findings: QxlintFinding[], cwd: string): void {
  clearFor(target);

  const grouped = new Map<string, { uri: vscode.Uri; items: vscode.Diagnostic[] }>();
  for (const finding of findings) {
    const placed = locate(finding, cwd);
    if (!placed) {
      continue;
    }
    const key = placed.uri.toString();
    const bucket = grouped.get(key) ?? { uri: placed.uri, items: [] };
    bucket.items.push(build(finding, placed.range));
    grouped.set(key, bucket);
  }

  for (const { uri, items } of grouped.values()) {
    diagnostics.set(uri, items);
  }
}

function clearFor(target: vscode.Uri): void {
  diagnostics.delete(target);
  for (const notebook of vscode.workspace.notebookDocuments) {
    if (notebook.uri.fsPath === target.fsPath) {
      for (const cell of notebook.getCells()) {
        diagnostics.delete(cell.document.uri);
      }
    }
  }
}

function build(finding: QxlintFinding, range: vscode.Range): vscode.Diagnostic {
  const diagnostic = new vscode.Diagnostic(
    range,
    messageWithFix(finding),
    severityOf(finding.severity) as vscode.DiagnosticSeverity,
  );
  diagnostic.source = SOURCE;
  diagnostic.code = {
    value: finding.rule,
    target: vscode.Uri.parse(ruleDocumentationUrl(finding.rule, DOCS)),
  };
  return diagnostic;
}

function locate(
  finding: QxlintFinding,
  cwd: string,
): { uri: vscode.Uri; range: vscode.Range } | undefined {
  const location = finding.location;
  if (location.kind === "circuit" || !location.path) {
    return undefined;
  }
  const absolute = path.isAbsolute(location.path) ? location.path : path.resolve(cwd, location.path);

  if (location.kind === "notebook") {
    const cell = codeCell(absolute, location.cellIndex ?? 1);
    if (!cell) {
      return undefined;
    }
    return { uri: cell.document.uri, range: toRange(location, cell.document) };
  }

  const document = vscode.workspace.textDocuments.find((entry) => entry.uri.fsPath === absolute);
  return { uri: vscode.Uri.file(absolute), range: toRange(location, document) };
}

function codeCell(fsPath: string, cellIndex: number): vscode.NotebookCell | undefined {
  // qxlint numbers code cells from one and skips markdown cells, so the index
  // is resolved against code cells only. The cell URI is never constructed by
  // hand: its fragment is an opaque encoding tied to a live cell handle.
  for (const notebook of vscode.workspace.notebookDocuments) {
    if (notebook.uri.fsPath !== fsPath) {
      continue;
    }
    const cells = notebook.getCells().filter((cell) => cell.kind === vscode.NotebookCellKind.Code);
    const position = codeCellPosition(cellIndex, cells.length);
    return position < 0 ? undefined : cells[position];
  }
  return undefined;
}

function toRange(location: QxlintLocation, document?: vscode.TextDocument): vscode.Range {
  const box = toZeroBasedRange(location);
  const range = new vscode.Range(
    box.startLine,
    box.startCharacter,
    box.endLine,
    box.endCharacter,
  );
  // The document may have moved on while qxlint was running. Clamping keeps the
  // squiggle inside the file instead of dropping it somewhere invisible.
  return document ? document.validateRange(range) : range;
}
