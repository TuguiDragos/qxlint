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

/**
 * A code point offset turned into the UTF-16 offset vscode.Position counts.
 *
 * qxlint counts characters, so an emoji is one column. VS Code counts UTF-16
 * code units, where the same emoji is two. Without this the squiggle slides one
 * unit left per astral character earlier on the line.
 */
export function utf16Offset(lineText: string, codePointOffset: number): number {
  let offset = 0;
  let seen = 0;
  while (seen < codePointOffset && offset < lineText.length) {
    offset += (lineText.codePointAt(offset) ?? 0) > 0xffff ? 2 : 1;
    seen += 1;
  }
  return offset + Math.max(codePointOffset - seen, 0);
}

/** The same range, with both ends measured the way the editor measures them. */
export function toUtf16Range(
  box: ZeroBasedRange,
  lineText: (line: number) => string | undefined,
): ZeroBasedRange {
  const start = lineText(box.startLine);
  const end = lineText(box.endLine);
  return {
    startLine: box.startLine,
    startCharacter:
      start === undefined ? box.startCharacter : utf16Offset(start, box.startCharacter),
    endLine: box.endLine,
    endCharacter: end === undefined ? box.endCharacter : utf16Offset(end, box.endCharacter),
  };
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
  // A payload without `findings` is not a lint payload. `--statistics` emits one
  // that carries schemaVersion and a rule histogram instead, and treating it as
  // zero findings made every file read clean for anyone who put that flag in
  // qxlint.args.
  if (!Array.isArray(payload.findings)) {
    return undefined;
  }
  return {
    findings: payload.findings as QxlintFinding[],
    toolVersion: typeof payload.toolVersion === "string" ? payload.toolVersion : undefined,
  };
}

export type RunOutcome =
  | { kind: "ok"; findings: QxlintFinding[]; toolVersion?: string }
  | { kind: "failed"; message: string; engineMissing: boolean };

/** Python's own words when the interpreter has no qxlint in it. */
const ENGINE_MISSING = /No module named qxlint/;

/** A summary payload, which carries no findings and must not read as clean. */
export function looksLikeStatistics(stdout: string): boolean {
  try {
    const parsed = JSON.parse(stdout.trim()) as Record<string, unknown>;
    return (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof parsed.schemaVersion === "string" &&
      !Array.isArray(parsed.findings) &&
      Array.isArray(parsed.rules)
    );
  } catch {
    return false;
  }
}

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
  if (looksLikeStatistics(stdout)) {
    return {
      kind: "failed",
      message:
        "qxlint returned a summary rather than findings. Remove --statistics " +
        "from qxlint.args: it reports counts, and the extension needs the findings.",
      engineMissing: false,
    };
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
