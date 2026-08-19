import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SEVERITY_ERROR,
  SEVERITY_INFORMATION,
  SEVERITY_WARNING,
  childEnvironment,
  codeCellPosition,
  interpretRun,
  lacksStdinSupport,
  messageWithFix,
  notebookPayload,
  parsePayload,
  placeable,
  ruleDocumentationUrl,
  severityOf,
  toUtf16Range,
  toZeroBasedRange,
  utf16Offset,
  type QxlintFinding,
} from "./core.js";

// Coordinates -----------------------------------------------------------
// qxlint is 1-based on both axes with an exclusive end column; VS Code is
// zero-based on both. Getting this wrong puts every squiggle on the wrong line
// and nothing else in the extension would notice.

test("the first character of the first line maps to the origin", () => {
  const range = toZeroBasedRange({ kind: "source", line: 1, column: 1 });
  assert.equal(range.startLine, 0);
  assert.equal(range.startCharacter, 0);
});

test("both axes lose exactly one", () => {
  const range = toZeroBasedRange({
    kind: "source",
    line: 31,
    column: 10,
    endLine: 31,
    endColumn: 27,
  });
  assert.deepEqual(range, {
    startLine: 30,
    startCharacter: 9,
    endLine: 30,
    endCharacter: 26,
  });
});

test("an exclusive end column stays the same width after conversion", () => {
  const range = toZeroBasedRange({
    kind: "source",
    line: 5,
    column: 10,
    endLine: 5,
    endColumn: 27,
  });
  assert.equal(range.endCharacter - range.startCharacter, 17);
});

test("a missing end falls back to a single character", () => {
  const range = toZeroBasedRange({ kind: "source", line: 4, column: 7 });
  assert.equal(range.startCharacter, 6);
  assert.equal(range.endCharacter, 7);
  assert.equal(range.endLine, 3);
});

test("a null end is treated as missing", () => {
  const range = toZeroBasedRange({
    kind: "source",
    line: 2,
    column: 3,
    endLine: null,
    endColumn: null,
  });
  assert.equal(range.endLine, 1);
  assert.equal(range.endCharacter, 3);
});

test("the range never runs backwards", () => {
  const range = toZeroBasedRange({
    kind: "source",
    line: 9,
    column: 20,
    endLine: 4,
    endColumn: 2,
  });
  assert.ok(range.endLine >= range.startLine);
  assert.ok(range.endCharacter > range.startCharacter);
});

test("degenerate coordinates never go negative", () => {
  const range = toZeroBasedRange({ kind: "source", line: 0, column: 0 });
  assert.equal(range.startLine, 0);
  assert.equal(range.startCharacter, 0);
});

test("a multi line range keeps both lines", () => {
  const range = toZeroBasedRange({
    kind: "source",
    line: 10,
    column: 5,
    endLine: 12,
    endColumn: 3,
  });
  assert.equal(range.startLine, 9);
  assert.equal(range.endLine, 11);
});

// Severity --------------------------------------------------------------

test("severities map onto the vscode numbering", () => {
  assert.equal(severityOf("error"), SEVERITY_ERROR);
  assert.equal(severityOf("warning"), SEVERITY_WARNING);
  assert.equal(severityOf("note"), SEVERITY_INFORMATION);
});

test("an unknown severity degrades to a warning rather than throwing", () => {
  assert.equal(severityOf("whatever"), SEVERITY_WARNING);
});

// Parsing ---------------------------------------------------------------
// An engine that never ran produces no payload, and the extension must not
// read that as a project with no findings.

test("empty output is not a payload", () => {
  assert.equal(parsePayload(""), undefined);
  assert.equal(parsePayload("   \n"), undefined);
});

test("malformed json is not a payload", () => {
  assert.equal(parsePayload("not json"), undefined);
});

test("json that is not a qxlint payload is rejected", () => {
  assert.equal(parsePayload("[1, 2]"), undefined);
  assert.equal(parsePayload("null"), undefined);
  assert.equal(parsePayload('{"findings": []}'), undefined);
});

test("a payload without findings is a payload with no findings", () => {
  assert.deepEqual(parsePayload('{"schemaVersion":"1"}'), {
    findings: [],
    toolVersion: undefined,
  });
});

test("findings and the engine version are read out of the payload", () => {
  const payload = parsePayload(
    JSON.stringify({
      schemaVersion: "1",
      toolVersion: "9.9.9",
      findings: [
        {
          rule: "QXL101",
          message: "m",
          severity: "error",
          location: { kind: "source", path: "a.py", line: 1, column: 1 },
        },
      ],
    }),
  );
  assert.equal(payload?.findings.length, 1);
  assert.equal(payload?.findings[0].rule, "QXL101");
  assert.equal(payload?.toolVersion, "9.9.9");
});

// Outcomes --------------------------------------------------------------

test("exit one with a payload is a normal result, not a failure", () => {
  const outcome = interpretRun(1, '{"schemaVersion":"1","findings":[]}', "");
  assert.equal(outcome.kind, "ok");
});

test("exit one with no payload is a failure, not a clean project", () => {
  // python -m qxlint exits 1 with an empty stdout when the module is missing.
  const outcome = interpretRun(1, "", "/usr/bin/python: No module named qxlint\n");
  assert.equal(outcome.kind, "failed");
  assert.equal(outcome.kind === "failed" && outcome.engineMissing, true);
  assert.match(outcome.kind === "failed" ? outcome.message : "", /not installed/);
});

test("a failure with no output at all still names the exit code", () => {
  const outcome = interpretRun(2, "", "");
  assert.equal(outcome.kind, "failed");
  assert.match(outcome.kind === "failed" ? outcome.message : "", /exited with code 2/);
});

test("a failure that is not a missing engine reports what was on stderr", () => {
  const outcome = interpretRun(2, "", "qxlint: --select: no rule matches 'QXL999'");
  assert.equal(outcome.kind, "failed");
  assert.equal(outcome.kind === "failed" && outcome.engineMissing, false);
  assert.match(outcome.kind === "failed" ? outcome.message : "", /no rule matches/);
});

test("an engine that predates the stdin flag is recognised", () => {
  assert.equal(
    lacksStdinSupport("usage: qxlint\nqxlint: error: unrecognized arguments: --stdin-filename a.py"),
    true,
  );
  assert.equal(lacksStdinSupport("qxlint: path does not exist: a.py"), false);
});

// Child environment ----------------------------------------------------

test("the analyser never sees its working directory on sys.path", () => {
  // Without this a qxlint package in the workspace shadows the installed one
  // and gets executed, which is exactly what the extension promises not to do.
  assert.equal(childEnvironment({}).PYTHONSAFEPATH, "1");
  assert.equal(childEnvironment({ PATH: "/usr/bin" }).PATH, "/usr/bin");
  assert.equal(childEnvironment({ PYTHONSAFEPATH: "0" }).PYTHONSAFEPATH, "1");
});

// Notebook payloads -----------------------------------------------------

test("a notebook buffer is serialised the way qxlint reads notebooks", () => {
  const raw = notebookPayload([
    { code: false, text: "# title" },
    { code: true, text: "qc = QuantumCircuit(1)" },
  ]);
  const document = JSON.parse(raw);
  assert.equal(document.nbformat, 4);
  assert.deepEqual(
    document.cells.map((cell: { cell_type: string }) => cell.cell_type),
    ["markdown", "code"],
  );
  // qxlint numbers code cells from one and skips markdown, so the markdown
  // cell has to be present for the second cell to be code cell one.
  assert.equal(document.cells[1].source, "qc = QuantumCircuit(1)");
});

// Placement -------------------------------------------------------------

const CIRCUIT: QxlintFinding = {
  rule: "QXL301",
  message: "m",
  severity: "error",
  location: { kind: "circuit" },
};
const SOURCE: QxlintFinding = {
  rule: "QXL101",
  message: "m",
  severity: "error",
  location: { kind: "source", path: "a.py", line: 1, column: 1 },
};
const NOTEBOOK: QxlintFinding = {
  rule: "QXL103",
  message: "m",
  severity: "warning",
  location: { kind: "notebook", path: "a.ipynb", cellIndex: 2, line: 1, column: 1 },
};

test("circuit findings have no file and are dropped", () => {
  assert.deepEqual(placeable([CIRCUIT]), []);
});

test("source and notebook findings are kept", () => {
  assert.deepEqual(placeable([SOURCE, CIRCUIT, NOTEBOOK]), [SOURCE, NOTEBOOK]);
});

test("a finding without a path is dropped", () => {
  const orphan: QxlintFinding = {
    rule: "QXL000",
    message: "m",
    severity: "error",
    location: { kind: "source" },
  };
  assert.deepEqual(placeable([orphan]), []);
});

// Presentation ----------------------------------------------------------

test("the fix hint is appended when present", () => {
  assert.equal(messageWithFix({ ...SOURCE, fixHint: "do x" }), "m\nFix: do x");
});

test("a finding without a fix hint is left alone", () => {
  assert.equal(messageWithFix(SOURCE), "m");
});

test("the rule code links to its lower case documentation page", () => {
  assert.equal(ruleDocumentationUrl("QXL101", "https://example.com/rules"),
    "https://example.com/rules/qxl101.md");
});

// Notebook cells --------------------------------------------------------

test("cell numbering is one based over code cells", () => {
  assert.equal(codeCellPosition(1, 5), 0);
  assert.equal(codeCellPosition(3, 5), 2);
});

test("a cell index past the end is rejected instead of wrapping", () => {
  assert.equal(codeCellPosition(6, 5), -1);
  assert.equal(codeCellPosition(0, 5), -1);
});

test("a missing cell index falls back to the first cell", () => {
  assert.equal(codeCellPosition(undefined, 3), 0);
});

// Exit codes ------------------------------------------------------------
//
// The exit code alone never decides the outcome. Exit 1 is findings when a
// payload came with it and a dead engine when none did.

test("every exit code that carries a payload is a result", () => {
  for (const code of [0, 1, null]) {
    assert.equal(interpretRun(code, '{"schemaVersion":"1","findings":[]}', "").kind, "ok");
  }
});

test("no exit code rescues a run that produced no payload", () => {
  for (const code of [0, 1, 2, null]) {
    assert.equal(interpretRun(code, "", "").kind, "failed");
  }
});

// Astral characters -----------------------------------------------------
// qxlint counts characters and vscode.Position counts UTF-16 code units. They
// agree until a character outside the Basic Multilingual Plane appears earlier
// on the line, and then every column after it is off by one per character.

test("an ASCII line needs no adjustment", () => {
  assert.equal(utf16Offset("counts = result.get_counts()", 9), 9);
});

test("a BMP character is one unit, like the character it is", () => {
  assert.equal(utf16Offset('psi = "\u03c8\u03c8\u03c8"; counts = x', 22), 22);
});

test("an astral character is two units", () => {
  // One emoji before the offset, so the UTF-16 offset is one further along.
  assert.equal(utf16Offset('label = "\u{1F3B2}"; x', 12), 13);
});

test("two astral characters shift by two", () => {
  assert.equal(utf16Offset('label = "\u{1F3B2}\u{1F3B2}"; counts = result', 23), 25);
});

test("an offset past the end of the line is kept, not clamped", () => {
  assert.equal(utf16Offset("ab", 5), 5);
});

test("an offset of zero is the start of the line", () => {
  assert.equal(utf16Offset("\u{1F3B2}abc", 0), 0);
});

test("a range is converted at both ends", () => {
  const line = 'label = "\u{1F3B2}\u{1F3B2}"; counts = result.get_counts()';
  const box = toZeroBasedRange({
    kind: "source",
    line: 1,
    column: 24,
    endLine: 1,
    endColumn: 41,
  });
  const converted = toUtf16Range(box, () => line);
  assert.equal(line.slice(converted.startCharacter, converted.endCharacter), "result.get_counts");
});

test("a line the document does not have leaves the range alone", () => {
  const box = toZeroBasedRange({ kind: "source", line: 9, column: 4 });
  const converted = toUtf16Range(box, () => undefined);
  assert.deepEqual(converted, box);
});
