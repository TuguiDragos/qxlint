# Notebooks

`.ipynb` files are analysed directly. There is no temporary `.py` round trip and
no dependency on nbqa, though the nbqa path also works if you prefer it.

```bash
qxlint analysis.ipynb
```

```
analysis.ipynb:cell3:2:10: QXL103 circuit has no measurement instructions but is passed to a SamplerV2
```

## What is analysed

- Code cells only, in textual order, with a **1-based** `cell_index` counting
  code cells and skipping markdown and raw cells. This matches nbqa.
- Semantic facts carry across cells, so a circuit built in one cell and sampled
  in another is understood.
- A cell that does not parse is reported as QXL000 and the run continues with
  every fact invalidated, rather than abandoning the notebook.

## Magics

Blanking a magic keeps the parser happy and lies to the analyser. `%run` can
rebind any name, so treating it as a no-op leaves stale facts and produces a
false positive. Magics are classified by what they can actually do.

| Class | Examples | Handling |
| --- | --- | --- |
| Display or configuration | `%matplotlib`, `%config`, `%load_ext`, `%pip`, `%cd` | line dropped, facts kept |
| Shell escape | `!pip install x`, `!./run.sh`, `!/usr/bin/env python x.py`, `!$HOME/tool` | dropped; it cannot reach the Python namespace |
| Shell capture | `out = !ls` | binds `out` to an unknown value |
| Python body cell magic | `%%time`, `%%capture`, `%%prun` | header dropped, body analysed |
| Unwrappable line magic | `%time y = f(x)` | rewritten to the statement |
| Namespace mutating | `%run`, `%load`, `%paste`, `%pylab`, `%store`, `%reset`, and any unrecognised magic | semantic barrier |
| Non Python body | `%%bash`, `%%sh`, `%%script`, `%%sql`, `%%html`, `%%writefile` | whole cell dropped, plus a barrier |
| Help syntax | `qc?`, `??obj` | dropped |

A **semantic barrier** sets every data binding to unknown and invalidates every
object fact. Import bindings survive: a magic could in principle rebind an
imported name, but dropping imports would silence every later cell, and the
facts rules depend on are invalidated either way.

`get_ipython().run_line_magic(...)`, `run_cell_magic`, `system` and `getoutput`
are recognised in that call form too, because nbconvert writes them into
exported notebooks.

## Line numbers

Every rewrite preserves the line count, so a reported line is the line you see
in the cell. A cell that already parses is left completely untouched, which is
what keeps valid Python such as

```python
x = (1
     % 2)
```

safe from the magic rewriter. In a cell that does not parse the rewriter does
run, and a line starting with `!=` is still left alone, because a comparison
split across two lines is far more likely there than a shell command named `=`.

## Limits, stated plainly

- **Automagic is not detected.** A bare `ls` is valid Python syntax and
  indistinguishable from a variable reference. nbqa has the same limitation.
- **Out-of-order execution cannot be reconstructed.** Analysis assumes cells run
  top to bottom. `execution_count` is not used to reorder them.
- **SARIF has no region for notebook findings.** The `.ipynb` artifact is JSON,
  and a cell line does not correspond to a line in that file. Notebook findings
  are emitted with the artifact plus a logical location, which is valid SARIF but
  will not produce an inline pull request annotation.
- Top level `await` is accepted, since notebooks allow it.
- **A notebook must be UTF-8.** That is what nbformat reads, so a file written
  as cp1252 or UTF-16, or carrying a UTF-8 BOM, is rejected there too. Verified
  against nbformat 5.11.0. qxlint reports it as QXL000 rather than accepting a
  file Jupyter itself cannot open.

## Under flake8

The flake8 plugin covers `.py` only. Use the qxlint CLI directly, or nbqa:

```bash
nbqa flake8 analysis.ipynb --select=QXL
```
