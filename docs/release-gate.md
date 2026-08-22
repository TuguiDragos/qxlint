# Release gate

What qxlint claims, what it does not, and what has to be true before a tag.

Every line under "Met" is checked by something that runs, not by review.

## Met

### The analysis

- The semantic layer has a dedicated test suite covering every cell of the
  tri-state merge table, every invalidation and escape rule, the container
  model, and each control flow construct in the policy.
- Every default tier source rule has one positive fixture and at least two
  negative fixtures, one of which is a realistic case where the pattern is
  correct. For QXL101 that is `BitArray.get_counts()`.
- Every rule documents when the pattern is legitimate. The test suite fails if
  that text is missing.
- Rule documentation is generated from the rule modules. The test suite fails if
  a page is stale, if a documented flagged example does not produce its rule, or
  if a documented clean example produces anything.
- Notebook fixtures pass, including magics, a non Python cell magic, a namespace
  mutating magic and an unparsable cell.
- Output is deterministic, verified by repeat run tests and by rescanning the
  external corpus.

### The suite

- **1125 tests**, green on Python 3.11, 3.12, 3.13 and 3.14.
- **100% coverage of statements and branches**, enforced as a CI gate rather
  than reported as a number. Branch coverage is on because a guard whose false
  side never runs is exactly where a linter hides a wrong answer.
- `mypy --strict` and `ruff check` plus `ruff format --check`, clean.
- Engine A runs with **no Qiskit installed at all**, verified in a separate CI
  job rather than asserted in a README.
- The declared Qiskit floor is a CI job of its own, so the claim stays a
  regression test once the latest release moves past it.
- 46 hand written mutations, each changing one documented behaviour: 44 were
  caught by the suite, and the two survivors were each verified to be equivalent
  mutants rather than gaps.

### The API model

- The tables in `semantics/model.py` were built by introspecting an installed
  Qiskit, not from documentation prose. The self inverse gate list was built by
  squaring operator matrices, and the library circuit table was built by
  constructing each entry and reading what it contained.
- `scripts/verify_model.py` re-checks **371 claims** against the installed
  packages. A scheduled workflow runs it on the 1st and the 15th of each month
  against the latest released Qiskit and qiskit-ibm-runtime, so an upstream
  change surfaces as a failing job rather than as a user report.

### Unseen code

244 public repositories, selected and pinned to commit SHAs before the linter
was run on any of them. See [../corpus/](../corpus/).

| | |
| --- | --- |
| Repositories | 244, from 243 owners |
| Files read | 51,711: 50,385 `.py` and 1,326 `.ipynb` |
| Crashes, timeouts, exit code 2 | 0 |
| Non deterministic results | 0 |
| Findings, read and labelled | 342 |
| False positives, three defects, all since fixed | 35 |
| Findings the current tree reports | 307 |
| Defects the corpus found in qxlint | 10 |

Every finding is labelled in a versioned CSV carrying the line it was reported
on, so a row can be checked without cloning anything. The 35 false positives are
kept in that file, relabelled with the reason, because a corpus that only
records what the linter currently gets right is not evidence.

### Hostile input

One file qxlint cannot handle never costs the rest of the run. Covered by tests:
undeclared and wrong encodings, UTF-16 and cp1252 notebooks, BOMs, null bytes,
CRLF and lone CR, symlink loops, symlinks to ancestors, broken symlinks, named
pipes, unreadable directories, deep directory trees, expressions nested deeper
than the parser can follow, very large cells, and notebooks whose JSON is broken
or absent.

## Not met, and not claimed

- **No precision figure.** Every finding across the corpus was read and
  labelled, but a single reviewer on 342 findings is not an independent
  precision measurement, and none is published. Thirty of those labels turned
  out to be wrong, which is the honest illustration of why one reviewer is not a
  measurement. QXL105 has still fired zero times on external code, so the corpus
  is evidence it does not fire wrongly, not evidence it finds things.
- **Recall is measured for one rule only.** For the removed `ibm_quantum`
  channel, where the textual pattern is precise enough to build a trustworthy
  denominator, qxlint reports **79 of the 81** live call sites in the corpus,
  counted by parsing every call that passes `channel="ibm_quantum"` as a
  keyword. The two it does not report are behind an import that is commented
  out, or one whose `except ImportError` branch rebinds the name, where silence
  is the designed behaviour. No denominator exists for the other rules without
  labelling every candidate by hand.
- **Reach is bounded, and now separated by cause.** Of the 307 Sampler `run()`
  calls the corpus resolves to a V2 primitive, 199 carry no provable fact about
  the circuit, so no rule can look at them. The causes, counted per call: 58.4%
  are a name assigned in the same function whose value the analyser still cannot
  follow, 15.2% cross a function boundary, 10.5% are bound in another file, and
  the rest are containers and expressions the model does not cover. The often
  quoted fix, interprocedural analysis, addresses the 15.2%: a prototype of it
  changed no finding anywhere in the corpus.
- **The author's own exercise corpus demonstrates regression safety, not
  precision on unseen code**, because it was written by the same author around
  these scenarios.

## Corpus rules, fixed in advance

- State the search query used and record the selection date.
- Pin every repository to a commit SHA and record its license.
- One repository per owner, no forks, no archived repositories.
- Exclude the author's own repositories.
- Select before running the linter. Never add a repository because a rule is
  already known to fire on it.
- Stratify before scanning, so the sample is not all Sampler-free code.
- Keep manual labels in a versioned file: repository, commit, file, line, the
  source line, rule, label, rationale, reviewer.

A repairable false positive is repaired and the corpus rescanned. A false
positive that cannot be repaired without losing the rule's value means the rule
ships as preview.

## Compatibility

| | Verified in CI | Supported |
| --- | --- | --- |
| Python | 3.11, 3.12, 3.13, 3.14 | 3.11 to 3.14 |
| Qiskit, Engine A | not required, and a job proves it | any, including absent |
| Qiskit, Engine B | 2.0.3 and 2.5.2 | 2.0 and later |
| qiskit-ibm-runtime | 0.49.0 | rules are version gated, not import gated |

Engine A never imports Qiskit, so its rules apply to any target version the
profile can establish, including projects still on Qiskit 1.x. The floor above
constrains only the optional `circuit` extra.
