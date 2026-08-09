# Prior art

Everything on this page was checked against a primary source on 2026-08-09.
Adoption numbers are volatile snapshots, not durable project facts.

## flake8-qiskit-migration

The incumbent for migration checking, and the closest neighbour.

- Version 0.5.0, uploaded 2026-02-24. Apache-2.0. Only dependency: flake8.
- Repository: `github.com/qiskit-community/flake8-qiskit-migration`. The PyPI
  metadata still points at `frankharkins/*`, which HTTP 301 redirects there; the
  package was authored by Frank Harkins and the repository was transferred.
- Released 0.1.0 to 0.4.0 in February 2024, then nothing for two years, then
  0.5.0 in February 2026 adding Qiskit 2.0 coverage.
- Roughly 83 downloads in the last month (pypistats.org, 2026-08-09).
- Error code prefix `QKT`, so no collision with `QXL`.

Complete coverage, read from source:

| Code | Data | Entries | Mechanism |
| --- | --- | --- | --- |
| QKT100 | `DEPRECATED_PATHS` | 97 + 4 exceptions | dotted import path prefix match, Qiskit 1.0 removals |
| QKT101 | `DEPRECATED_METHODS_V1` | 16 | bare method name match, gated only on "file imports qiskit" |
| QKT102 | `DEPRECATED_METHOD_KWARGS_V1` | 2 | (method, kwarg) pair match |
| QKT200 | `DEPRECATED_PATHS_V2` | 43 + 10 exceptions | path prefix match, Qiskit 2.0 removals |
| QKT201 | `DEPRECATED_METHODS_V2` | 13 | bare method name match |
| QKT202 | `DEPRECATED_KWARGS_V2` | 36 | (import path, kwarg) match with alias resolution |

Six checks, 207 rule data entries. **Every one is a deprecated or removed name
lookup.** There is no workflow analysis: nothing checks the PUB shape, the result
shape, observables, layout, or Session and Batch usage. Its own README notes that
the method-name checks are heuristic and can produce false positives without type
inference.

**qxlint implements no migration rules.** The two tools answer different
questions. flake8-qiskit-migration answers "does this code still import and call
things that exist". qxlint answers "is this a correct Primitives V2 workflow".
Run both.

## LintQ

Paltenghi and Pradel, "Analyzing Quantum Programs with LintQ: A Static Analysis
Framework for Qiskit", Proc. ACM Softw. Eng. 1, FSE (2024), 2144-2166,
DOI 10.1145/3660802, arXiv 2310.00718.

- Ten analyses, a corpus of 7,568 real-world Qiskit programs, **91.0% precision
  in the default configuration with the six best performing analyses** (121 true
  positives of 133 warnings), and 92.1% of the problems it found missed by the
  prior work compared against.
- The arXiv v1 preprint reported nine analyses and 80.5%. That figure is
  superseded and is not the headline.
- Requires CodeQL and a Docker database build. Reported at about 1.3 seconds per
  program, with full corpus runs in hours. Accurate framing: impractical for
  fast per-commit linting, usable in scheduled or heavyweight CI.
- 9 GitHub stars, last pushed February 2025.

Its six default analyses are GhostComposition, ConditionalGateWithoutMeas,
DoubleMeasurement, MeasureAll, OpAfterMeasurement and OpAfterOptimization. None
of its ten evaluated analyses touches Primitives V2 PUBs, observables, layout, or
Session and Batch usage. The repository does ship further untagged queries that
are adjacent to ISA checking, so the accurate claim is "none of LintQ's ten
evaluated analyses", not "nothing in the LintQ repository".

## LLM based linting

- LintQ-LLM, arXiv 2504.05204 (April 2025).
- "Beyond Rules: LLM-Powered Linting for Quantum Programs", arXiv 2605.03943
  (May 2026). Introduces LintQ-LLM+CoT and +RAG, evaluated on 55 Qiskit
  programs, F1 0.70 and 0.68 against LintQ's 0.41. Argues that rule-based
  quantum linters struggle to keep pace with rapidly evolving APIs.

The README answers that argument directly rather than ignoring it.

## Others

- **QChecker**, arXiv 2304.04387, Q-SE 2023. AST based bug detector evaluated on
  Bugs4Q. No maintained public tool repository found.
- **QSmell**, `github.com/jose/qsmell`. Hybrid static and dynamic code smell
  detection; only two of its eight metrics are static. Last pushed January 2023.
- **lique**, `github.com/sarulab-ou/lique`. A general quantum program linter in
  Rust. Adjacent, different target, not on PyPI.
- **qasmtools**, `github.com/orangekame3/qasmtools`. An OpenQASM 3 toolkit with
  a linter, in Go. Targets OpenQASM 3, not the Qiskit Python API.

Earlier drafts of this project's brief listed a tool called **Q-Spire**. No
primary source for it exists and it is deliberately not cited.

## Ruff

Ruff does not currently support third-party plugins. Its FAQ states that a
plugin system is within scope for the future (astral-sh/ruff#283, still open).
qxlint ships a flake8 plugin instead, and would revisit a ruff plugin if one
becomes possible.

## On adoption

LintQ has 9 GitHub stars, flake8-qiskit-migration 2 stars and roughly 83
downloads per month. The honest reading is that **the product category is
immature and weakly adopted**. That is not evidence the problem is real: low
adoption is equally consistent with a small market, low awareness, or a need
already met by documentation and runtime errors. What supports the problem being
real is the research literature and the scale of the Qiskit API change. Demand
for a separate linter is not yet validated.
