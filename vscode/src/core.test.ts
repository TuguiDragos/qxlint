import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SEVERITY_ERROR,
  SEVERITY_INFORMATION,
  SEVERITY_WARNING,
  codeCellPosition,
  isFailure,
  messageWithFix,
  parseFindings,
  placeable,
  ruleDocumentationUrl,
  severityOf,
  toZeroBasedRange,
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

test("empty output is not an error", () => {
  assert.deepEqual(parseFindings(""), []);
  assert.deepEqual(parseFindings("   \n"), []);
});

test("a payload without findings is not an error", () => {
  assert.deepEqual(parseFindings('{"schemaVersion":"1"}'), []);
});

test("findings are read out of the payload", () => {
  const findings = parseFindings(
    JSON.stringify({
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
  assert.equal(findings.length, 1);
  assert.equal(findings[0].rule, "QXL101");
});

test("malformed json throws so the caller can log it", () => {
  assert.throws(() => parseFindings("not json"));
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

test("findings are not a failure but exit two is", () => {
  assert.equal(isFailure(0), false);
  assert.equal(isFailure(1), false);
  assert.equal(isFailure(2), true);
  assert.equal(isFailure(null), false);
});
