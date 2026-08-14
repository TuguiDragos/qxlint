// Pure logic, deliberately free of any `vscode` import so it can be tested
// without launching an editor. The coordinate conversion lives here because it
// is the one thing that silently ruins every diagnostic when it is wrong:
// qxlint emits 1-based lines and 1-based character columns with an exclusive
// end column, and vscode.Position is zero-based on both axes.

export type Severity = "error" | "warning" | "note";
export type LocationKind = "source" | "notebook" | "circuit";

export interface QxlintLocation {
  kind: LocationKind;
  path?: string;
  line?: number;
  column?: number;
  endLine?: number | null;
  endColumn?: number | null;
  cellIndex?: number;
}

export interface QxlintFinding {
  rule: string;
  message: string;
  severity: Severity;
  location: QxlintLocation;
  fixHint?: string;
}

/** Zero-based, half open, ready to become a vscode.Range. */
export interface ZeroBasedRange {
  startLine: number;
  startCharacter: number;
  endLine: number;
  endCharacter: number;
}

// Mirrors vscode.DiagnosticSeverity, which is not importable here.
export const SEVERITY_ERROR = 0;
export const SEVERITY_WARNING = 1;
export const SEVERITY_INFORMATION = 2;

export function severityOf(value: string): number {
  switch (value) {
    case "error":
      return SEVERITY_ERROR;
    case "note":
      return SEVERITY_INFORMATION;
    default:
      return SEVERITY_WARNING;
  }
}

export function toZeroBasedRange(location: QxlintLocation): ZeroBasedRange {
  const line = Math.max((location.line ?? 1) - 1, 0);
  const character = Math.max((location.column ?? 1) - 1, 0);
  const endLine = Math.max((location.endLine ?? location.line ?? 1) - 1, line);
  const endCharacter = Math.max(
    (location.endColumn ?? (location.column ?? 1) + 1) - 1,
    character + 1,
  );
  return { startLine: line, startCharacter: character, endLine, endCharacter };
}

export interface QxlintPayload {
  findings: QxlintFinding[];
  toolVersion?: string;
}

/**
 * A qxlint JSON payload, or undefined when the text is not one.
 *
 * Undefined is the important case. `python -m qxlint` exits 1 with an empty
 * stdout when the module is not installed, and treating that as a payload with
 * no findings told the user their project was clean when nothing had run.
 */
export function parsePayload(stdout: string): QxlintPayload | undefined {
  const trimmed = stdout.trim();
  if (!trimmed) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return undefined;
  }
  if (typeof parsed !== "object" || parsed === null) {
    return undefined;
  }
  const payload = parsed as Record<string, unknown>;
  if (typeof payload.schemaVersion !== "string") {
    return undefined;
  }
  return {
    findings: Array.isArray(payload.findings) ? (payload.findings as QxlintFinding[]) : [],
    toolVersion: typeof payload.toolVersion === "string" ? payload.toolVersion : undefined,
  };
}

export type RunOutcome =
  | { kind: "ok"; findings: QxlintFinding[]; toolVersion?: string }
  | { kind: "failed"; message: string; engineMissing: boolean };

/** Python's own words when the interpreter has no qxlint in it. */
const ENGINE_MISSING = /No module named qxlint/;

/** True when the engine rejected the flag, so an older qxlint is installed. */
export function lacksStdinSupport(stderr: string): boolean {
  return /unrecognized arguments:.*--stdin-filename/.test(stderr);
}

/**
 * What a finished qxlint process actually said.
 *
 * A valid payload is the only evidence that the analyser ran. Exit 0 and exit 1
 * both carry one, exit 1 with nothing on stdout carries none, and the exit code
 * alone cannot tell those apart.
 */
export function interpretRun(code: number | null, stdout: string, stderr: string): RunOutcome {
  const payload = parsePayload(stdout);
  if (payload) {
    return { kind: "ok", findings: payload.findings, toolVersion: payload.toolVersion };
  }
  if (ENGINE_MISSING.test(stderr)) {
    return {
      kind: "failed",
      message:
        "qxlint is not installed in the selected Python environment. " +
        "Install it with: pip install qxlint",
      engineMissing: true,
    };
  }
  const reason = stderr.trim() || `qxlint exited with code ${code ?? "unknown"} and produced no output`;
  return { kind: "failed", message: reason, engineMissing: false };
}

/** Findings that can be placed in a document. Circuit findings have no file. */
export function placeable(findings: QxlintFinding[]): QxlintFinding[] {
  return findings.filter((finding) => finding.location.kind !== "circuit" && finding.location.path);
}

export function messageWithFix(finding: QxlintFinding): string {
  return finding.fixHint ? `${finding.message}\nFix: ${finding.fixHint}` : finding.message;
}

/** Documentation URL for a rule code, used as the clickable diagnostic code. */
export function ruleDocumentationUrl(rule: string, base: string): string {
  return `${base}/${rule.toLowerCase()}.md`;
}

/**
 * qxlint numbers code cells from one and skips markdown cells, so a cell index
 * has to be resolved against code cells only. Returns -1 when it is out of
 * range, which happens if the notebook changed while qxlint was running.
 */
export function codeCellPosition(cellIndex: number | undefined, codeCellCount: number): number {
  const index = (cellIndex ?? 1) - 1;
  return index >= 0 && index < codeCellCount ? index : -1;
}

/**
 * Environment for the analyser process.
 *
 * The working directory is the user's project, so `python -m qxlint` would
 * import a qxlint package sitting in it and run that instead. PYTHONSAFEPATH
 * keeps the working directory off sys.path, which is what makes "qxlint never
 * executes your code" true. It is read from Python 3.11 on, which is the floor
 * the engine already requires, and an older interpreter ignores a variable it
 * does not know rather than failing on it.
 */
export function childEnvironment(base: Record<string, string | undefined>): Record<
  string,
  string | undefined
> {
  return { ...base, PYTHONSAFEPATH: "1" };
}

/** A notebook as qxlint reads it: cell kinds and sources, nothing else. */
export function notebookPayload(
  cells: { code: boolean; text: string }[],
): string {
  return JSON.stringify({
    cells: cells.map((cell) => ({
      cell_type: cell.code ? "code" : "markdown",
      source: cell.text,
      metadata: {},
      outputs: [],
      execution_count: null,
    })),
    metadata: {},
    nbformat: 4,
    nbformat_minor: 5,
  });
}
