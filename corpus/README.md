# External corpus

qxlint is checked against code it has never seen. The corpus is 244 public
repositories, selected and pinned to commit SHAs on 2026-08-09 **before** the
linter was run on any of them, so a repository cannot be added after seeing what
a rule does to it. Everything needed to reproduce the run is in this directory.

| | |
| --- | --- |
| Repositories | **244**, from 243 distinct owners |
| Files read | **51,711**: 50,385 `.py` and 1,326 `.ipynb` |
| Crashes, timeouts, exit code 2 | **0** |
| Non deterministic results | **0** |
| Findings read and labelled individually | **379** |
| QXL205 findings, counted in aggregate, 24 of them sampled and read | **5,845** |
| of which false positives, three defects, all since fixed | **35** |
| Findings the current tree reports | **6,165**, of which 320 outside QXL205 |
| Defects the corpus found in qxlint, all fixed | **10** |
| Wall clock | 77 s for all 244 in one process; the largest repository, 5,874 files, takes 5.6 s and peaks at 98 MB |

## Files

| File | What it is |
| --- | --- |
| [manifest.json](manifest.json) | the selection: every stratum with its query and the pool it drew from, every repository pinned to a SHA with its licence |
| [findings.csv](findings.csv) | one row per finding, with the line it was reported on and a reviewer's label |

## Who labelled these

All 379 labels were written by an AI reviewer, `claude-opus-5`, and **none has
been confirmed by a human**. Every row says so in its `reviewer` column, and no
row claims otherwise.

What that does and does not support:

- **Supported.** Robustness and determinism. 244 repositories were read twice
  with zero crashes, zero timeouts and zero differing results, and none of that
  depends on a label being right.
- **Not supported.** Precision. A precision figure needs a reviewer independent
  of the tool, and one AI reviewer whose work nobody has checked is not that.
  No precision figure is published anywhere in this project, and none should be
  quoted from this directory until the labels have been reviewed by hand.
| [scan.json](scan.json) | the machine output of the current run, per repository |
| [bugs-found.json](bugs-found.json) | the nine defects this corpus exposed in qxlint, each with its regression test |
| [candidates.json](candidates.json) | the pool each stratum drew from, so the selection rule can be checked |

## How the selection works

Fixed before the linter ran, so it cannot be bent afterwards:

- state the search query and the selection date;
- pin every repository to a commit SHA and record its licence;
- one repository per owner, no forks, no archived repositories, under 200 MB;
- exclude the author's own repositories;
- stratify, so the sample is not all Sampler-free code;
- take the alphabetically first entries that survive the filters, never a choice
  made after seeing the findings;
- keep the labels in a versioned file with a rationale per row.

Twenty nine strata are declared and twenty six produced a repository; the other
three found only repositories an earlier stratum had already taken. They reach
deliberately past the popular projects: some strata take repositories with one
to five stars or with none at all, some take only those last pushed in 2023 and
2024, some take only notebook repositories. Three further strata were planned
against GitHub's code search endpoint, which returned HTTP 503 throughout the
selection; they were dropped rather than quietly replaced.

One owner, `Qiskit`, holds two entries. The rest hold one each, and the
exception is recorded in the manifest rather than smoothed over.

## Results

Zero crashes. Zero timeouts. No exit code 2 anywhere. Two consecutive passes
produce byte identical output, and so do Python 3.13 and 3.14.

| Rule | Labelled | Reported today | True positive | False positive |
| --- | --- | --- | --- | --- |
| QXL000 | 168 | 135 | 135 | 33 |
| QXL101 | 7 | 7 | 7 | 0 |
| QXL102 | 12 | 12 | 12 | 0 |
| QXL103 | 9 | 9 | 9 | 0 |
| QXL104 | 47 | 45 | 45 | 2 |
| QXL201 | 79 | 79 | 79 | 0 |
| QXL202 | 21 | 21 | 21 | 0 |
| QXL203 | 4 | 4 | 4 | 0 |
| QXL204 | 8 | 8 | 8 | 0 |
| QXL205 | 24 sampled | 5,845 | 24 sampled | 0 |

The scan supplies `--target-runtime 0.48` so the version gated rules are pinned
to a stated version rather than to whatever the reading of the day is. Since
every one of them now reads an undeclared target as current, the total without
the flag is the same 6,165.

Two QXL104 rows were relabelled from `true-positive` to `false-positive` on
20 August 2026, both in `ML-2-QML/QML/5514.py`. Each is
`block.assign_parameters(params, [0, 1])`, where the second positional argument
is `inplace`. A non empty list is truthy, so Qiskit mutates the receiver and
returns None, verified by running that exact call shape. The original rationale
read the method default, which this call overrides. They are no longer reported.

Three QXL000 rows were relabelled from `true-positive-unparsable` to
`false-positive` on 19 August 2026. Each is a notebook cell holding a bare
`pip install` or `pip list`. The original rationale read them as accepted by
neither CPython nor IPython; only the first half of that is true, because
IPython automagic rewrites such a line and the cell runs. They are no longer
reported.

Labels are `true-positive` for a real defect, `true-positive-intentional` where
the code is deliberate and the finding is still correct,
`true-positive-unparsable` for QXL000, and `false-positive` for a finding that
should not have been made.

Nine rows carry no source line. Each is a notebook whose JSON is broken, so
there is no line to read: one file is zero bytes and the rest have their opening
brace replaced by a colon.

A credential that appears in a scanned repository is replaced by `<redacted>` in
the `source` column. Eight rows are affected. The value is still in the public
repository the row points at; recording where a linter fired must not republish
it here.

### QXL205 is counted rather than read line by line

QXL205 contributes 5,845 of the findings, and they are not individually
labelled. The reason is that the rule makes no inference. It is a lookup in a
table of 12 names, each with the release that removed it read from the published
wheels and the absence confirmed on Qiskit 2.5.2, matched against the dotted
path of an import statement. The claim that has to be checked is the table, not
the 5,845 places the table matches.

24 of them are read and labelled anyway, 2 for each of the 12 names, drawn from
12 different repositories, so the match itself is evidenced. Every sampled line
was opened in the corpus checkout and confirmed to import the name reported.

The concentration is worth recording. 90 percent of the 5,845 come from two
repositories that are collections of legacy files rather than projects:
runtsang/Q-Bridge contributes 3,867 across 2,334 files and
LucaGandolfi77/Qiskit-QuantumComputing 1,385 across 365. The other 32
repositories that QXL205 touches receive at most 15 findings each.

Every other rule keeps the original discipline: every finding read, every label
recorded with its reason.

### The 30 false positives were one defect

They were found after the scan, and the check the scan used could not have
caught them. Every QXL000 was cross checked by handing the same file to
CPython's own `compile()`, which rejected it. For a `.py` file that settles it.
For a **notebook cell** it proves nothing: a cell holding `!pip install x` is not
valid Python either, so CPython rejects it whether or not qxlint handled the
magic correctly. The question for a cell is what **IPython** accepts, and the
scan never asked it.

The magic detector required a letter after the `!`, so a shell escape written
any other way stayed in the cell and the cell then failed to parse:

| Form | Occurrences |
| --- | --- |
| `!{sys.executable} -m pip install ...` | 18 |
| `! command`, with a space after the bang | 11 |
| `!./cloudflared ...` | 1 |

Fixed on 2026-08-09, with a regression test per form. The rows keep their place
in `findings.csv`, relabelled `false-positive` with the reason, because a
corpus that only records what the linter currently gets right is not evidence.

### What a pattern matcher would have done

The corpus contains **4,003** `.get_counts(` calls and **286** `quasi_dists`
occurrences. A linter matching those textually would have reported 4,289
findings. qxlint reports 18: seven QXL101 and eleven QXL102, each on a V2 result
object. Every one of the other 4,271 is correct legacy or V1 code, where
`get_counts()` is exactly right.

### What QXL104 found

The rule fires on a circuit method that returns a new circuit whose result is
thrown away. Three of the 47 are in Qiskit's own test suite:

```python
qc.compose(CCXGate().definition, [0, 1, 2], [])  # Unroll CCX to 2q operations.
qc.assign_parameters({theta: 3.14})
circ.inverse()
```

`compose` and `assign_parameters` default to `inplace=False` and `inverse`
always returns, so the comment on the first line describes something that does
not happen.

## Reproducing

```bash
python scripts/scan_corpus.py --target-runtime 0.48
```

The script downloads each repository at its pinned SHA, keeps only `.py` and
`.ipynb`, and scans. It never selects, so it cannot be used to add a repository
after the fact.
