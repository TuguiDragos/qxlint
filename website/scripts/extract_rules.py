"""Reads qxlint's generated rule pages and runs qxlint on every example, so the site shows real output."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

repo, out = Path(__file__).resolve().parents[2], Path(sys.argv[1]).resolve()
python = sys.executable
# Examples run outside the repository, so its own [tool.qxlint] settings never change what a reader would see.
scratch = tempfile.mkdtemp()
LIBRARY = {"QXL300", "QXL301", "QXL302", "QXL303"}


def section(text, title):
    m = re.search(rf"^## {re.escape(title)}\n\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def blocks(text):
    return [(lang, code.rstrip("\n")) for lang, code in re.findall(r"```(\w*)\n(.*?)```", text, re.S)]


def lint(code):
    run = subprocess.run([str(python), "-m", "qxlint", "--stdin-filename", "example.py", "--no-color"], input=code,
                         capture_output=True, text=True, cwd=scratch)
    if run.returncode not in (0, 1):
        raise SystemExit(f"qxlint could not run: {run.stderr}")
    return run.stdout.strip(), run.returncode


# The library examples name a backend; FakeFez, a Heron r2 snapshot shipped with qiskit-ibm-runtime, stands in.
PRELUDE = """import qxlint
from qiskit import QuantumCircuit
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime.fake_provider import FakeFez
backend = FakeFez()
"""


# How each circuit rule is reached, as its page says: QXL300 and QXL301 through check_target, the two preview rules
# through check_circuit with preview on.
CALLS = {"QXL300": "qxlint.check_target(qc, backend.target)", "QXL301": "qxlint.check_target(qc, backend.target)",
         "QXL302": "qxlint.check_circuit(qc, preview=True)", "QXL303": "qxlint.check_circuit(qc, preview=True)"}


def library(code, rule):
    """Runs the example exactly as its page writes it. A fragment that names something it never builds is a sketch,
    and gets no output rather than an invented one."""
    if "qxlint.check_" in code:
        body = "\n".join(f"_found += {line.split('#')[0].strip()}" if line.strip().startswith("qxlint.check_") else line
                         for line in code.splitlines())
    else:
        body = code + f"\n_found += {CALLS[rule]}"
    script = PRELUDE + "_found = []\n" + body + "\nfor f in _found:\n    print(f.render_text())\n"
    run = subprocess.run([str(python), "-c", script], capture_output=True, text=True, cwd=scratch)
    if run.returncode:
        if "NameError" in run.stderr:
            return None
        raise SystemExit(f"library example failed: {run.stderr[-800:]}\n{script}")
    return run.stdout.strip()


rules = []
for page in sorted((repo / "docs/rules").glob("qxl*.md")):
    text = page.read_text()
    head = re.search(r"^# (QXL\d+): (.+)$", text, re.M)
    meta = dict(re.findall(r"^- \*\*(\w[\w ]*)\*\*: `?([^`\n]+)`?$", text, re.M))
    code, title = head.group(1), head.group(2)
    flagged = blocks(section(text, "Flagged"))[0][1]
    clean = blocks(section(text, "Not flagged"))[0][1]
    rule = {
        "code": code, "title": title, "name": meta["Name"], "tier": meta["Tier"], "severity": meta["Severity"],
        "gated": meta["Version gated"] == "yes", "library": code in LIBRARY,
        "why": section(text, "Why this is a problem"), "legit": section(text, "When this is legitimate"),
        "flagged": flagged, "clean": clean,
        "references": re.findall(r"<(https?://[^>]+)>", section(text, "References")),
    }
    if rule["library"]:
        rule["flaggedOutput"], rule["cleanOutput"] = library(flagged, code), library(clean, code)
        rule["call"] = CALLS[code]
    else:
        rule["flaggedOutput"], flagged_exit = lint(flagged)
        rule["cleanOutput"], clean_exit = lint(clean)
        assert flagged_exit == 1, (code, "the flagged example raised nothing")
        assert clean_exit == 0, (code, "the clean example raised something", rule["cleanOutput"])
    if rule["flaggedOutput"] is not None:
        assert code in rule["flaggedOutput"] or code == "QXL000", (code, rule["flaggedOutput"])
    if rule["cleanOutput"] is not None:
        assert code not in rule["cleanOutput"], (code, rule["cleanOutput"])
    rules.append(rule)
    print(code, "flagged ->", (rule["flaggedOutput"] or "(not runnable as written)").splitlines()[0][:110], "| clean ->", repr((rule["cleanOutput"] or "")[:60]) if rule["cleanOutput"] is not None else "(not runnable as written)")
out.write_text(json.dumps(rules, indent=1))
print(len(rules), "rules")
