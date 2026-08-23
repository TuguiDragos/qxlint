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

## The line in the `.ipynb`

A reported line is the line inside the cell, which is what you want in an editor.
It is not the line in the `.ipynb` file, because that file is JSON and the cell
source lives inside it as a quoted, escaped array of strings.

qxlint works that correspondence out anyway and publishes it as `physicalLine` on
every notebook finding in the JSON output:

```json
{
  "kind": "notebook",
  "path": "analysis.ipynb",
  "cellIndex": 1,
  "line": 3,
  "column": 9,
  "physicalLine": 5
}
```

`physicalLine` is the line of the `.ipynb` holding that source line, which is what
a tool needs to annotate the file on disk. In the usual shape, one JSON string per
line, it is the exact line. In a minified notebook there is only one line to
point at, so every source line of a cell resolves to the line where that cell's
source begins, which is still where an annotation belongs.

The block is located by matching a run of consecutive encoded lines, so a line
that also occurs elsewhere cannot pull the mapping out of step, and a repeated
cell resolves to its own copy rather than to the first match. A file whose shape
defeats that yields null rather than a plausible wrong number, so a consumer has
to handle its absence.

The text form does not print it. It shows `analysis.ipynb:cell3:2:10`, because a
cell coordinate is what a person reads a notebook by.

## Limits, stated plainly

- **Automagic is read only where it is decidable.** `pip install qiskit` is not
  valid Python, so a line naming a known magic that does not parse is read as the
  magic IPython would run, and the rest of the cell is analysed. A bare `ls` is
  valid Python syntax and indistinguishable from a variable reference, so it is
  left alone. nbqa has the same limitation on that half.
- **Out-of-order execution cannot be reconstructed.** Analysis assumes cells run
  top to bottom. `execution_count` is not used to reorder them.
- **SARIF has no region for notebook findings.** Notebook findings are emitted
  with the artifact plus a logical location, which is valid SARIF but will not
  produce an inline pull request annotation. The line in the `.ipynb` is known,
  see `physicalLine` below; it is simply not carried into SARIF yet.
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
