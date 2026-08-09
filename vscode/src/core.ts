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

/** Findings from a qxlint JSON payload, tolerant of an empty or absent result. */
export function parseFindings(stdout: string): QxlintFinding[] {
  const trimmed = stdout.trim();
  if (!trimmed) {
    return [];
  }
  const parsed = JSON.parse(trimmed) as { findings?: QxlintFinding[] };
  return parsed.findings ?? [];
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

/** Exit 1 means findings, which is normal. Exit 2 means qxlint could not run. */
export function isFailure(exitCode: number | null): boolean {
  return exitCode === 2;
}
