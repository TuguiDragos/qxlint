# Security policy

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/TuguiDragos/qxlint/security/advisories/new)
on this repository, or by email to <contact@tuguidragos.com>. Please do not open
a public issue for a security problem.

Expect an acknowledgement within seven days, and an assessment within fourteen.
If a fix is warranted it ships in the next release, and the advisory is
published with credit unless you ask otherwise.

## Supported versions

| Version | Supported |
| --- | --- |
| latest minor release | yes |
| anything older | no |

Fixes land on the latest minor release. There are no long term support branches.

## Threat model

qxlint reads source files and **never imports or executes the code it
analyses**. That is a design constraint, not an implementation detail:

- Engine A uses the standard library `ast` module. There is no `import`, no
  `exec`, no `eval`, and no subprocess of the analysed project.
- There is no `--import-circuits` flag and there will not be one. Importing a
  user module executes arbitrary code, and a subprocess with a timeout is a
  mitigation rather than a sandbox.
- Engine B works on circuit objects the caller already constructed in their own
  process. qxlint does not construct them.
- qxlint makes no network requests, reads no credentials, and writes nothing
  outside the output stream you point it at.
- The only files it opens are regular files with a `.py` or `.ipynb` suffix. A
  named pipe, device or socket is reported rather than opened, because opening
  a pipe blocks with no timeout.

The realistic risks are therefore **denial of service from a pathological input
file** and **incorrect output**. Both are treated as bugs; only the first is
treated as a security issue.

### What is already hardened

Each of these is covered by a test, and by a scan over 244 external
repositories:

| Input | Behaviour |
| --- | --- |
| A file the parser cannot finish | reported as QXL000, the run continues |
| A notebook that is not UTF-8, or whose JSON is broken | reported as QXL000, the run continues |
| A named pipe or device named `.py` or `.ipynb` | reported, never opened |
| A directory that cannot be traversed | skipped, the run continues |
| A symlink loop or a symlink to an ancestor | terminates |
| Anything unforeseen on one file | named on stderr, the run continues, exit code 2 |

## Supply chain

- Runtime dependencies: `packaging` only. Qiskit is optional and is needed only
  by the circuit checks.
- Releases are published from a tagged workflow. PyPI uses trusted publishing
  with OpenID Connect, so no long lived token exists for it.
- The npm package is a launcher that spawns the Python tool. It bundles no
  Python and no analyser code.
- The composite GitHub Action passes every input through the environment rather
  than interpolating it into a shell script, so an input value cannot become a
  command.
