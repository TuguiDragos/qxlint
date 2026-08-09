# qxlint documentation

Deterministic static checks for Qiskit Primitives V2 workflows.

## For users

- [Rules](rules/index.md), generated from the rule modules
- [Configuration](configuration.md), every option, the resolution order and the
  exit codes
- [Notebooks](notebooks.md), what is analysed in an `.ipynb` and what is not
- [The semantic layer](semantic-layer.md), the analysis contract: what qxlint
  can prove, and what makes it stay silent

## Evidence

- [External corpus](../corpus/), 244 unseen repositories, with every finding
  labelled
- [Release gate](release-gate.md), what is claimed, what is not, and how each
  claim is checked
- [Prior art](prior-art.md), the neighbouring tools and where qxlint differs

## Two engines

**Engine A** reads source. It uses the standard library `ast` module, never
imports and never executes the analysed code, and works with no Qiskit
installed. It backs the CLI, the flake8 plugin, pre-commit, the GitHub Action
and the VS Code extension.

**Engine B** inspects an in-memory circuit. It needs Qiskit, is reachable only
through the library API, and its findings have no `file:line`; they carry a
circuit name and an instruction path instead.

## Coordinates

| Surface | Line | Column | End column |
| --- | --- | --- | --- |
| text and JSON output | 1-based | 1-based character | exclusive |
| SARIF | 1-based | 1-based character | exclusive |
| flake8 plugin | 1-based | 0-based **byte**, matching flake8 | not reported |

`ast` reports columns as 0-based UTF-8 byte offsets, so every column is
converted before it is reported. The flake8 plugin converts back, because flake8
and pyflakes are byte based and a mixed convention inside one flake8 run would
be worse than either.

## Robustness contract

One file qxlint cannot handle never costs the rest of the run.

| Input | Result |
| --- | --- |
| Source the interpreter cannot parse | QXL000 for that file |
| A notebook that is not UTF-8, or whose JSON is broken | QXL000 for that file |
| An expression nested deeper than the parser can follow | QXL000 for that file |
| A named pipe, device or directory named `.py` | QXL000 for that path, never opened |
| A directory that cannot be traversed | skipped |
| Anything unforeseen | named on stderr, the run continues, exit code 2 |

Every one of those is covered by a test, and the whole set is exercised against
[the external corpus](../corpus/) before a release.
