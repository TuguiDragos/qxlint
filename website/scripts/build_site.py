"""Builds qxlint's website from the repository it sits in: the rule pages, the output qxlint printed for each
example, the test suite, the model check, and the corpus run. Every figure is read here, on every build, so the page
grows with the project; a sentence the page quotes from the docs is checked against them, and a build whose claim no
longer holds stops rather than publishing it."""
import csv
import datetime
import html
import json
import re
import subprocess
import urllib.request
import tomllib
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
WORK, out_dir = WEB / "_build", WEB / "_site"
rules_file = WORK / "rules.json"
THEME = WEB / "theme/quantum-dark.json"

SITE = "https://qxlint.tuguidragos.com/"
REPO = "https://github.com/TuguiDragos/qxlint"
PYPI = "https://pypi.org/project/qxlint/"
NPM = "https://www.npmjs.com/package/@tuguidragos/qxlint"
MARKETPLACE = "https://marketplace.visualstudio.com/items?itemName=tuguidragos.qxlint"
OPENVSX = "https://open-vsx.org/extension/tuguidragos/qxlint"
SPONSOR = "https://github.com/sponsors/TuguiDragos"
COMMAND = "uvx qxlint ."
TITLE = "qxlint: Static Checks for Qiskit Primitives V2 Code"
DESCRIPTION = ("Static checks for Qiskit Primitives V2 code. qxlint reads your code without running it, offline, "
               "with no quantum hardware, and flags only what it can prove.")

esc = lambda s: html.escape(s, quote=True)
AMERICAN = {"analyser": "analyzer", "cancelling": "canceling", "unmodelled": "unmodeled",
            "characterisation": "characterization", "randomised": "randomized"}
american = lambda s: re.sub(r"\b(" + "|".join(AMERICAN) + r")\b", lambda m: AMERICAN[m.group(1)], s)
# The rule pages mark code with backticks; on the page it is set as code, so it reads as code and can wrap.
prose = lambda s: re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(american(s))).replace(" -&gt; ", " → ")
# Titles keep the rule pages' words. A title that opens with code, like get_counts() or service=, stays lowercase,
# and the code in it is set as code.
CODE_WORD = re.compile(r'^[a-z_][\w.]*(?:\(\)|=(?:"[^"]*")?)$')


def heading(title):
    words = title.split(" ")
    if re.fullmatch(r"[a-z]+", words[0]):
        words[0] = words[0].capitalize()
    return " ".join(f"<code>{esc(w)}</code>" if CODE_WORD.match(w) else esc(w) for w in words)



rules = json.loads(rules_file.read_text())
by_code = {r["code"]: r for r in rules}
FIRST_RULE = "QXL103"
assert FIRST_RULE in by_code

# The project's own numbers, as this build finds them.
pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
VERSION = pyproject["project"]["version"]
pythons = sorted((c.rsplit(":: ", 1)[1] for c in pyproject["project"]["classifiers"]
                  if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)), key=lambda v: int(v.split(".")[1]))
PYTHON_RANGE = f"Python {pythons[0]} to {pythons[-1]}"
assert pyproject["project"]["requires-python"] == f">={pythons[0]}"
python_list = ", ".join(pythons[:-1]) + f" and {pythons[-1]}"
ci = (ROOT / ".github/workflows/ci.yml").read_text()
assert f'python: [{", ".join(chr(34) + p + chr(34) for p in pythons)}]' in ci, "the CI matrix is the classifiers' list"
TESTS = sum(int(n) for n in re.findall(r": (\d+)$", (WORK / "collect.txt").read_text(), re.M))
MODEL_CHECKS = int(re.search(r"all (\d+) model checks agree", (WORK / "model.txt").read_text()).group(1))
assert "fail_under = 100" in (ROOT / "pyproject.toml").read_text()
assert '- cron: "0 6 1,15 * *"' in (ROOT / ".github/workflows/scheduled.yml").read_text()
assert "scripts/verify_model.py" in (ROOT / ".github/workflows/scheduled.yml").read_text()

# The corpus, from the files the run left: what was scanned, by whom it was chosen, and what was read by hand.
scan = json.loads((ROOT / "corpus/scan.json").read_text())
manifest = json.loads((ROOT / "corpus/manifest.json").read_text())
labelled = list(csv.DictReader((ROOT / "corpus/findings.csv").open()))
CORPUS = {
    "repos": scan["repositories"], "owners": manifest["distinct_owners"], "py": scan["python_files"],
    "notebooks": scan["notebooks"], "failed": scan["exit_code_2"], "findings": scan["findings"],
    "outside": scan["findings"] - scan["totals"]["QXL205"], "read": len(labelled),
    "version": scan["qxlint_version"].removeprefix("qxlint "), "on": datetime.date.fromisoformat(scan["scanned_on"]),
}
assert CORPUS["repos"] == len(scan["records"]) == manifest["repository_count"]
assert all("pending confirmation" in row["reviewer"] for row in labelled), "the page says no label is confirmed yet"
fmt = lambda n: f"{n:,}"
date = lambda d: f"{d:%B} {d.day}, {d.year}"

# Every code sample on the page, colored by Tapetum Quantum through the same engine VS Code uses.
SNIPPETS = {}
for r in rules:
    SNIPPETS[f"{r['code']}-flagged"] = (r["flagged"], "python")
    SNIPPETS[f"{r['code']}-clean"] = (r["clean"], "python")
DECIDES = [
    ("Names point at objects, not at facts.", "So an alias carries what was done through it.",
     "qc = QuantumCircuit(1)\nalias = qc\nalias.measure_all()\nsampler.run([qc])          # silent, the measurement is on the same object"),
    ("A local container is not an escape.", "This is how most Sampler code is written, so it has to be analyzable.",
     "circuits = []\ncircuits.append(qc)\nsampler.run(circuits)      # the circuit is still tracked"),
    ("Effects are scoped.", "A call that cannot reach a circuit does not affect it; a call that receives it does.",
     "qc = QuantumCircuit(2)\nqc.h(0)\nprint(\"running\")           # cannot touch qc\nsampler.run([qc])          # QXL103 fires\n\nqc2 = QuantumCircuit(2)\nhelper(qc2)                # may keep and mutate it\nsampler.run([qc2])         # silent"),
    ("Proof, or silence.", "A rule fires only on what the analyzer can prove, never on maybe and never on unknown.",
     "qc = QuantumCircuit(1)\nif condition:\n    qc.measure_all()\nsampler.run([qc])          # QXL103 stays silent: measured on some paths"),
]
for i, (_, _, code) in enumerate(DECIDES):
    SNIPPETS[f"decides-{i}"] = (code, "python")
INTEGRATIONS = [
    ("pre-commit", "Two hooks, one for Python files and one for notebooks.",
     "repos:\n  - repo: https://github.com/TuguiDragos/qxlint\n    rev: v" + VERSION + "\n    hooks:\n      - id: qxlint\n      - id: qxlint-notebook", "yaml"),
    ("GitHub Actions", f"SARIF for code scanning. The tag pins the analyzer too, so @v{VERSION} installs qxlint {VERSION}.",
     f"- uses: TuguiDragos/qxlint@v{VERSION}\n  with:\n    paths: .\n    format: sarif\n    output: qxlint.sarif", "yaml"),
    ("VS Code", "Diagnostics in .py files and in notebook cells, from the same CLI and the same configuration as CI.",
     "pip install qxlint", "bash"),
    ("flake8", "A plugin for .py files. Use the CLI or nbqa for notebooks.",
     "pip install qxlint flake8\nflake8 --select=QXL .", "bash"),
    ("A baseline", "Adopt it on a project that already has findings: record them once, then gate on what is added.",
     "qxlint --baseline-write qxlint-baseline.json\nqxlint --baseline qxlint-baseline.json", "bash"),
    ("Configuration", "In pyproject.toml. Silence one line with <code>#&nbsp;noqa:&nbsp;QXL101</code>.",
     '[tool.qxlint]\nselect = ["QXL1", "QXL2"]\nignore = ["QXL102"]\ntarget-runtime = "0.48"', "toml"),
]
for i, (_, _, code, lang) in enumerate(INTEGRATIONS):
    SNIPPETS[f"integration-{i}"] = (code, lang)

source = WORK / "snippets.json"
source.write_text(json.dumps([{"id": k, "code": c, "lang": l} for k, (c, l) in SNIPPETS.items()]))
subprocess.run(["node", str(WEB / "scripts/highlight.mjs"), str(THEME), str(source), str(WORK / "colored.json")], check=True,
               capture_output=True)
COLORED = json.loads((WORK / "colored.json").read_text())


def output_html(text):
    """qxlint's own output, verbatim, with the location and the rule code picked out."""
    lines = []
    for line in text.splitlines():
        m = re.match(r"^(\S+?:(?:\d+:\d+:|)|circuit-\d+(?:\[[^\]]*\])*(?:\.block\[\d+\]\[\d+\])*:)\s*(QXL\d+)(.*)$", line)
        lines.append(f'<span class="loc">{esc(m.group(1))}</span> <span class="code-id">{m.group(2)}</span>{esc(m.group(3))}'
                     if m else esc(line))
    return lines


def output_pre(first, lines, extra=""):
    """A terminal block whose long lines wrap under themselves, not under the prompt."""
    return f'<pre class="output{extra}">' + "".join(f'<span class="line">{line}</span>' for line in [first, *lines]) + "</pre>"


GROUPS = [
    ("QXL0", "Parsing"),
    ("QXL1", "Results and circuits"),
    ("QXL2", "Runtime and API"),
    ("QXL3", "Circuits in memory"),
]
assert all(any(r["code"].startswith(prefix) for prefix, _ in GROUPS) for r in rules), "a new rule family needs a group name"


def rule_article(r):
    code = r["code"]
    slug = code.lower()
    badges = [f"<li>{esc(r['tier'])} tier</li>", f'<li data-severity="{esc(r["severity"])}">{esc(r["severity"])}</li>']
    if r["gated"]:
        badges.append("<li>version gated</li>")
    if r["library"]:
        badges.append("<li>library API</li>")
    if r["library"]:
        run = f'<span class="prompt">&gt;&gt;&gt;</span> {esc(r["call"])}'
        flagged_out = (output_pre(run, output_html(r["flaggedOutput"])) if r["flaggedOutput"]
                       else '<p class="output sketch">The rule page sketches this circuit rather than building it, so no output is shown.</p>')
        clean_out = (output_pre(run, ["No findings"], " none") if r["cleanOutput"] == ""
                     else '<p class="output sketch">The rule page sketches this circuit rather than building it, so no output is shown.</p>')
    else:
        flagged_out = output_pre('<span class="prompt">$</span> qxlint example.py', output_html(r["flaggedOutput"]))
        clean_out = output_pre('<span class="prompt">$</span> qxlint example.py', ["No findings"], " none")
    active = " active" if code == FIRST_RULE else ""
    return f"""<article class="rule{active}" id="{slug}" aria-labelledby="{slug}-title">
            <p class="rule-code">{code}</p>
            <h3 id="{slug}-title">{heading(r["title"])}</h3>
            <ul class="badges" aria-label="About this rule">{''.join(badges)}</ul>
            <h4>Why it is a problem</h4>
            <p>{prose(r['why'])}</p>
            <h4>When it is legitimate</h4>
            <p>{prose(r['legit'])}</p>
            <div class="pair">
              <figure class="code flagged"><figcaption><b>Flagged</b></figcaption><pre><code>{COLORED[code + '-flagged']}</code></pre>{flagged_out}</figure>
              <figure class="code clean"><figcaption><b>Not flagged</b></figcaption><pre><code>{COLORED[code + '-clean']}</code></pre>{clean_out}</figure>
            </div>
            <p class="rule-link"><a class="more" href="{REPO}/blob/main/docs/rules/{slug}.md">The full rule page, with how to silence it</a></p>
          </article>"""


chip_groups = []
for prefix, name in GROUPS:
    items = "".join(
        f'<li><button type="button" data-rule="{r["code"].lower()}" aria-pressed="{"true" if r["code"] == FIRST_RULE else "false"}" '
        f'aria-controls="{r["code"].lower()}">{r["code"]}</button></li>'
        for r in rules if r["code"].startswith(prefix))
    chip_groups.append(f'<div class="group"><p class="group-name">{prefix} · {name}</p><ul class="chips">{items}</ul></div>')

file_rules = sum(not r["library"] for r in rules)
preview = sum(r["tier"] == "preview" for r in rules)
assert all(r["library"] for r in rules if r["tier"] == "preview"), "the tile says the preview rules are circuit rules"

decides_html = "".join(f"""<article class="example reveal">
            <h3>{esc(t)}</h3>
            <p>{esc(d)}</p>
            <figure class="code"><pre><code>{COLORED[f'decides-{i}']}</code></pre></figure>
          </article>""" for i, (t, d, _) in enumerate(DECIDES))

integrations_html = "".join(f"""<li class="reveal"><h3>{esc(t)}</h3><p>{d}</p><pre><code>{COLORED[f'integration-{i}']}</code></pre></li>"""
                            for i, (t, d, _, _) in enumerate(INTEGRATIONS))

DEMO = [
    ("app.py:31:10:", "QXL101", " get_counts() on a PrimitiveResult; counts live on the BitArray in PrimitiveResult -> PubResult -> .data (DataBin) -> <classical register> (BitArray)"),
    ("app.py:44:1: ", "QXL103", " circuit has no measurement instructions but is passed to a SamplerV2; the result carries no counts"),
    ("service.py:7:31:", "QXL201", ' channel="ibm_quantum" was removed in qiskit-ibm-runtime 0.41; omit the channel argument'),
]
for _, rule_code, message in DEMO:
    assert message.strip() in by_code[rule_code]["flaggedOutput"], rule_code
demo_html = '<span class="line"><span class="prompt">$</span> uvx qxlint .</span>' + "".join(
    f'<span class="line"><span class="loc">{esc(loc.strip())}</span> <span class="code-id">{c}</span>{esc(m)}</span>' for loc, c, m in DEMO)

FAQ = [
    ("What is qxlint?",
     "qxlint is a free, open source linter for Python code that uses Qiskit. It finds the mistakes the move from the V1 "
     "to the V2 primitives introduced, such as reading counts off the wrong object or sampling a circuit that has no "
     "measurements, by reading your source. It never imports or runs it."),
    ("How do I run qxlint?",
     "Run <code>uvx qxlint .</code> in your project without installing anything, or install it with "
     "<code>uv tool install qxlint</code>, <code>pipx install qxlint</code>, or <code>pip install qxlint</code>. "
     f"It needs {PYTHON_RANGE}."),
    ("Does qxlint need Qiskit or a quantum computer?",
     "No. The source linter needs no Qiskit at all, makes no network requests, and needs no quantum hardware. Only the "
     "checks on circuits in memory need Qiskit, installed with <code>pip install 'qxlint[circuit]'</code>."),
    ("Does qxlint work on Jupyter notebooks?",
     "Yes. It reads .ipynb files directly and carries what it knows across cells in order. Each magic is handled by what "
     "it can do: display magics are dropped, cell magics with a Python body are analyzed, and magics that can rebind "
     "names stop the analysis from trusting what came before."),
    ("Will qxlint report something that is fine?",
     "It tries hard not to. A rule fires only on facts the analyzer can prove, never on maybe and never on unknown, and "
     "every rule page says when the pattern it catches is legitimate. If that cannot be written, the rule does not ship."),
    ("How do I silence a finding?",
     "Add <code>#&nbsp;noqa:&nbsp;QXL101</code> to the line, or list the rule under <code>ignore</code> in "
     "<code>[tool.qxlint]</code> in pyproject.toml. On a project that already has findings, record them once with "
     "<code>--baseline-write</code> and gate on what is added with <code>--baseline</code>."),
    ("Can I use qxlint in CI and in my editor?",
     "Yes: as a pre-commit hook, as a GitHub Action that writes SARIF for code scanning, as a flake8 plugin, and as a VS "
     "Code extension that runs the same CLI with the same configuration, so the editor and CI agree."),
    ("Is qxlint free?", "Yes. qxlint is free and open source under the MIT License."),
]
faq_html = "\n".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in FAQ)
plain = lambda text: html.unescape(re.sub(r"<[^>]+>", "", text))

PERSON = "https://tuguidragos.com/#person"
SAME_AS = [
    "https://www.linkedin.com/in/tuguidragos/", "https://github.com/TuguiDragos", "https://x.com/TuguiDragos",
    "https://www.facebook.com/TuguiDragos/", "https://www.instagram.com/tuguidragos/",
    "https://n8n.io/creators/tuguidragos/", "https://www.credly.com/users/tuguidragos",
    "https://tuguidragos.gumroad.com", "https://bsky.app/profile/tuguidragos.com", "https://mastodon.social/@tuguidragos",
    "https://www.threads.com/@tuguidragos", "https://www.tiktok.com/@tuguidragos", "https://www.youtube.com/@TuguiDragos",
]
PROFILES = [
    ("GitHub", "https://github.com/TuguiDragos"), ("LinkedIn", "https://www.linkedin.com/in/tuguidragos/"),
    ("X", "https://x.com/TuguiDragos"), ("Bluesky", "https://bsky.app/profile/tuguidragos.com"),
    ("Mastodon", "https://mastodon.social/@tuguidragos"), ("Threads", "https://www.threads.com/@tuguidragos"),
    ("Instagram", "https://www.instagram.com/tuguidragos/"), ("YouTube", "https://www.youtube.com/@TuguiDragos"),
]
MIT = "https://spdx.org/licenses/MIT.html"
ld = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "@id": SITE + "#website", "url": SITE, "name": "qxlint", "inLanguage": "en-US",
         "publisher": {"@id": PERSON}},
        {"@type": "WebPage", "@id": SITE + "#webpage", "url": SITE, "name": TITLE, "description": DESCRIPTION,
         "inLanguage": "en-US", "isPartOf": {"@id": SITE + "#website"}, "about": {"@id": SITE + "#app"},
         "mainEntity": {"@id": SITE + "#app"}, "primaryImageOfPage": SITE + "images/social.png",
         "dateModified": datetime.date.today().isoformat()},
        {"@type": "Person", "@id": PERSON, "name": "Țugui Dragoș",
         "alternateName": ["Tugui Dragos", "Țugui Dragoș-Constantin", "Tugui Dragos-Constantin", "Dragoș Țugui",
                           "Dragos Tugui"],
         "url": "https://tuguidragos.com/", "image": "https://tuguidragos.com/content/images/2026/06/Dragos-Tugui.webp",
         "jobTitle": "Automation & AI Systems Builder", "sameAs": SAME_AS},
        {"@type": "SoftwareApplication", "@id": SITE + "#app", "name": "qxlint", "url": SITE,
         "sameAs": [REPO, PYPI, NPM, MARKETPLACE, OPENVSX],
         "description": "Deterministic static checks for Qiskit Primitives V2 workflows. It reads Python files and "
                        "Jupyter notebooks without importing or running them.",
         "applicationCategory": "DeveloperApplication", "applicationSubCategory": "Linter",
         "operatingSystem": "macOS, Windows, Linux", "softwareRequirements": PYTHON_RANGE, "softwareVersion": VERSION,
         "downloadUrl": PYPI, "installUrl": PYPI, "isAccessibleForFree": True,
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}, "license": MIT,
         "author": {"@id": PERSON}, "image": SITE + "images/qxlint-icon-256.png",
         "featureList": [
             f"{len(rules)} rules: {file_rules} for Python files and notebooks, {len(rules) - file_rules} for circuits in memory",
             "Reads source without importing or running it, with no network requests and no quantum hardware",
             "Fires only on what it can prove, and documents when each pattern is legitimate",
             "Version gated rules that read the qiskit-ibm-runtime version a project declares",
             "Jupyter notebooks analyzed directly, with magics handled by what they can do",
             "pre-commit hooks, a GitHub Action with SARIF, a flake8 plugin, and a VS Code extension"]},
        {"@type": "SoftwareSourceCode", "@id": "https://tuguidragos.com/#qxlint", "name": "qxlint", "url": REPO,
         "codeRepository": REPO, "programmingLanguage": "Python", "runtimePlatform": "Qiskit", "license": MIT,
         "author": {"@id": PERSON}, "maintainer": {"@id": PERSON}, "targetProduct": {"@id": SITE + "#app"}},
        {"@type": "FAQPage", "@id": SITE + "#questions", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in FAQ]},
    ],
}
ld_json = json.dumps(ld, ensure_ascii=False, indent=2).replace("</", "<\\/")

GITHUB_MARK = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M6.766 11.328c-2.063-.25-3.516-1.734-3.516-3.656 0-.781.281-1.625.75-2.188-.203-.515-.172-1.609.063-2.062.625-.078 1.468.25 1.968.703.594-.187 1.219-.281 1.985-.281.765 0 1.39.094 1.953.265.484-.437 1.344-.765 1.969-.687.218.422.25 1.515.046 2.047.5.593.766 1.39.766 2.203 0 1.922-1.453 3.375-3.547 3.64.531.344.89 1.094.89 1.954v1.625c0 .468.391.734.86.547C13.781 14.359 16 11.53 16 8.03 16 3.61 12.406 0 7.984 0 3.563 0 0 3.61 0 8.031a7.88 7.88 0 0 0 5.172 7.422c.422.156.828-.125.828-.547v-1.25c-.219.094-.5.156-.75.156-1.031 0-1.64-.562-2.078-1.609-.172-.422-.36-.672-.719-.719-.187-.015-.25-.093-.25-.187 0-.188.313-.328.625-.328.453 0 .844.281 1.25.86.313.452.64.655 1.031.655s.641-.14 1-.5c.266-.265.47-.5.657-.656"/></svg>')
HEART = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M7.655 14.916v-.001h-.002l-.006-.003-.018-.01a22.066 22.066 0 0 1-3.744-2.584C2.045 10.731 0 8.35 0 5.5 0 2.836 2.086 1 4.25 1 5.797 1 7.153 1.802 8 3.02 8.847 1.802 10.203 1 11.75 1 13.914 1 16 2.836 16 5.5c0 2.85-2.044 5.231-3.886 6.818a22.094 22.094 0 0 1-3.433 2.414 7.152 7.152 0 0 1-.31.17l-.018.01-.008.004a.75.75 0 0 1-.69 0Z"/></svg>')
CHECK = '<svg class="check" viewBox="0 0 72 56" aria-hidden="true"><path d="M8 30 22 44 64 10" fill="none" stroke="#a99fe4" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>'
profile_items = "\n".join(f'          <li><a href="{u}">{n}</a></li>' for n, u in PROFILES)

page = f"""<!DOCTYPE html>
<html lang="en-US">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{TITLE}</title>
  <meta name="description" content="{esc(DESCRIPTION)}">
  <link rel="canonical" href="{SITE}">
  <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
  <meta name="author" content="Țugui Dragoș">
  <meta name="application-name" content="qxlint">
  <meta name="apple-mobile-web-app-title" content="qxlint">
  <meta name="theme-color" content="#0c1016">
  <meta name="color-scheme" content="dark">

  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/favicon-96x96.png" type="image/png" sizes="96x96">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="manifest" href="/site.webmanifest">

  <script>document.documentElement.classList.add("js")</script>
  <link rel="stylesheet" href="style.css">
  <script src="main.js" defer></script>

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="qxlint">
  <meta property="og:locale" content="en_US">
  <meta property="og:url" content="{SITE}">
  <meta property="og:title" content="qxlint: static checks for Qiskit Primitives V2">
  <meta property="og:description" content="Finds the mistakes of the move to Qiskit's V2 primitives. It reads your code, never runs it.">
  <meta property="og:image" content="{SITE}images/social.png">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="qxlint’s icon and the words “Static checks for Qiskit Primitives V2”, above qxlint’s output in a terminal">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="qxlint: static checks for Qiskit Primitives V2">
  <meta name="twitter:description" content="Finds the mistakes of the move to Qiskit's V2 primitives. It reads your code, never runs it.">
  <meta name="twitter:image" content="{SITE}images/social.png">
  <meta name="twitter:image:alt" content="qxlint’s icon and the words “Static checks for Qiskit Primitives V2”, above qxlint’s output in a terminal">

  <script type="application/ld+json">
{ld_json}
  </script>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>

  <header class="nav">
    <div class="wrap">
      <a class="brand" href="#top" aria-label="qxlint, back to the top">
        <img src="images/qxlint-icon-84.webp" width="28" height="28" alt="">
        <span>qxlint</span>
      </a>
      <nav aria-label="Sections">
        <ul class="nav-links">
          <li><a href="#rules">Rules</a></li>
          <li><a href="#decides">How it decides</a></li>
          <li><a href="#notebooks">Notebooks</a></li>
          <li><a href="#integrations">Integrations</a></li>
          <li><a href="#tested">Tested</a></li>
          <li><a href="#questions">Questions</a></li>
        </ul>
      </nav>
      <div class="nav-actions">
        <a class="pill pill-small pill-ghost" href="{SPONSOR}" aria-label="Sponsor qxlint on GitHub">{HEART}<span class="label">Sponsor</span></a>
        <a class="pill pill-small" href="{REPO}">{GITHUB_MARK}GitHub</a>
      </div>
    </div>
  </header>

  <main id="main">
    <section class="hero" id="top">
      <div class="wrap">
        <img class="hero-icon" src="images/qxlint-icon-256.webp" srcset="images/qxlint-icon-168.webp 168w, images/qxlint-icon-256.webp 256w" sizes="(max-width: 640px) 84px, 104px" width="104" height="104" fetchpriority="high" alt="qxlint’s icon: two sliders, a lavender bar, and a check mark">
        <h1>Static checks for Qiskit Primitives V2.</h1>
        <p class="tagline"><span class="gradient">It reads your code. It never runs it.</span></p>
        <p class="lede">qxlint finds the mistakes the move from V1 to V2 primitives introduced: counts read off the wrong object, a V1 field on a V2 result, a circuit sampled without a measurement, and a channel a release has removed.</p>
        <div class="command">
          <code>{COMMAND}</code>
          <button class="copy" type="button" data-copy="{COMMAND}">Copy</button>
        </div>
        <div class="actions">
          <a class="pill pill-large" href="{REPO}">{GITHUB_MARK}View on GitHub</a>
          <a class="more" href="{MARKETPLACE}">Get the VS Code extension</a>
        </div>
        <p class="requirements">{PYTHON_RANGE} · Qiskit optional · Free, MIT License</p>
        <div class="terminal" role="img" aria-label="qxlint’s output on a project: QXL101 in app.py, QXL103 in app.py, and QXL201 in service.py">
          <div class="terminal-bar" aria-hidden="true"><i></i><i></i><i></i><span>my-project</span></div>
          <pre aria-hidden="true">{demo_html}</pre>
        </div>
      </div>
    </section>

    <section class="statement" aria-label="Why qxlint exists">
      <div class="wrap reveal">
        <p><strong>Two things fail quietly in Primitives V2 code.</strong> Calling <code>get_counts()</code> one level too high raises, but only after the job has run. And a circuit with no measurement instruction can come back as all zeros, which looks like a physics result. <strong>Both can be decided from the source, without a model, a network, or a quantum computer.</strong></p>
      </div>
    </section>

    <section class="section" aria-labelledby="highlights-title">
      <div class="wrap">
        <h2 class="headline center reveal" id="highlights-title">Get the highlights.</h2>
        <div class="highlights">
          <article class="tile span-3 reveal">
            <div class="tile-art" aria-hidden="true"><span class="figure gradient">{len(rules)}</span></div>
            <h3>{len(rules)} rules.</h3>
            <p>{file_rules} for Python files and notebooks, and {len(rules) - file_rules} for circuits in memory, {preview} of them in preview.</p>
          </article>
          <article class="tile span-3 reveal">
            <div class="tile-art" aria-hidden="true"><span class="bars"><i></i><i></i><i></i></span>{CHECK}</div>
            <h3>Reads. Never runs.</h3>
            <p>It never imports or executes your code, makes no network requests, and needs no quantum hardware.</p>
          </article>
          <article class="tile reveal">
            <div class="tile-art" aria-hidden="true"><span class="figure gradient">{fmt(TESTS)}</span></div>
            <h3>Tests.</h3>
            <p>Run in CI on Python {python_list}, with Qiskit, without it, and at its lowest version.</p>
          </article>
          <article class="tile reveal">
            <div class="tile-art" aria-hidden="true"><span class="figure gradient">100%</span></div>
            <h3>Coverage.</h3>
            <p>Of statements and branches, held by a CI gate rather than reported as a number.</p>
          </article>
          <article class="tile reveal">
            <div class="tile-art" aria-hidden="true"><span class="figure gradient">{fmt(MODEL_CHECKS)}</span></div>
            <h3>API checks.</h3>
            <p>Its model of Qiskit, checked against a real install on the 1st and 15th of every month.</p>
          </article>
        </div>
      </div>
    </section>

    <section class="section" id="rules" aria-labelledby="rules-title">
      <div class="wrap center">
        <div class="feature-head center reveal">
          <p class="eyebrow">Rules</p>
          <h2 class="headline" id="rules-title">Each one says when it is wrong.</h2>
          <p class="lede">Every rule page documents when the pattern it catches is legitimate. <strong>If that cannot be written, the rule does not ship.</strong> Pick a rule to see what it flags, what it leaves alone, and what qxlint printed for each.</p>
        </div>
        <div class="explorer">
          <div class="groups" role="group" aria-label="Rules">
            {''.join(chip_groups)}
          </div>
          <div class="rules">
          {''.join(rule_article(r) for r in rules)}
          </div>
        </div>
      </div>
    </section>

    <hr class="divider">

    <section class="section" id="decides" aria-labelledby="decides-title">
      <div class="wrap center">
        <div class="feature-head center reveal">
          <p class="eyebrow">How it decides</p>
          <h2 class="headline" id="decides-title">It asks what an object is.</h2>
          <p class="lede"><code>get_counts()</code> is right on a <code>BitArray</code> and wrong on a <code>DataBin</code>, so the question is never whether a call appears. <strong>qxlint answers it with a small abstract interpreter</strong> that follows objects through aliases, containers, Qiskit’s library circuits and the transpile pipeline.</p>
        </div>
        <div class="examples">
          {decides_html}
        </div>
        <div class="table-wrap reveal">
          <table>
            <caption>QXL201 reads the qiskit-ibm-runtime version your project declares</caption>
            <thead><tr><th scope="col">Declared target</th><th scope="col">What QXL201 reports</th></tr></thead>
            <tbody>
              <tr><td><code>0.48</code>, <code>&gt;=0.41</code></td><td>An error: removed in 0.41</td></tr>
              <tr><td><code>0.40.2</code>, <code>==0.40.*</code></td><td>A warning: deprecated since 0.40</td></tr>
              <tr><td><code>&gt;=0.38,&lt;0.43</code></td><td>An error, because the range does not prove the code is safe</td></tr>
              <tr><td>Not declared</td><td>An error, because an unstated target is read as current</td></tr>
              <tr><td><code>0.39</code></td><td>Nothing, because a pin below 0.40 predates the deprecation</td></tr>
            </tbody>
          </table>
        </div>
        <p class="note reveal">The target comes from <code>--target-runtime</code>, then <code>[tool.qxlint]</code>, then your project’s dependencies, an unambiguous <code>uv.lock</code> pin, or <code>requirements.txt</code>. Never from the Qiskit qxlint itself runs with.</p>
      </div>
    </section>

    <section class="section" id="notebooks" aria-labelledby="notebooks-title">
      <div class="wrap center">
        <div class="feature-head center reveal">
          <p class="eyebrow">Notebooks</p>
          <h2 class="headline" id="notebooks-title">Notebooks, cell by cell.</h2>
          <p class="lede">.ipynb files are read directly, and what qxlint knows carries across cells in order. <strong>Magics are not blanked out, because blanking lies to the analyzer:</strong> each is handled by what it can actually do.</p>
        </div>
        <div class="table-wrap reveal">
          <table>
            <thead><tr><th scope="col">Kind</th><th scope="col">Examples</th><th scope="col">Handling</th></tr></thead>
            <tbody>
              <tr><td>Display or configuration</td><td><code>%matplotlib</code>, <code>%pip</code>, <code>!cmd</code></td><td>Dropped, facts kept</td></tr>
              <tr><td>Python body</td><td><code>%%time</code>, <code>%%capture</code>, <code>%time</code></td><td>Header dropped, body analyzed</td></tr>
              <tr><td>Namespace changing</td><td><code>%run</code>, <code>%load</code>, <code>%pylab</code>, unknown magics</td><td>A barrier: facts before it are not trusted</td></tr>
              <tr><td>Not Python</td><td><code>%%bash</code>, <code>%%sql</code>, <code>%%html</code></td><td>Whole cell dropped, a barrier</td></tr>
            </tbody>
          </table>
        </div>
        <p class="note reveal">Every rewrite keeps the line count, so a reported line is the line you see in the cell.</p>
      </div>
    </section>

    <hr class="divider">

    <section class="section" id="integrations" aria-labelledby="integrations-title">
      <div class="wrap center">
        <div class="feature-head center reveal">
          <p class="eyebrow">Integrations</p>
          <h2 class="headline" id="integrations-title">In your editor. In your gate.</h2>
          <p class="lede">The same analyzer behind every way in, <strong>so the editor and CI cannot disagree.</strong> Exit code 0 is clean, 1 is findings, and 2 means qxlint could not run.</p>
        </div>
        <ul class="cards">
          {integrations_html}
        </ul>
      </div>
    </section>

    <section class="section" id="tested" aria-labelledby="tested-title">
      <div class="wrap center">
        <div class="feature-head center reveal">
          <p class="eyebrow">Tested</p>
          <h2 class="headline" id="tested-title">Run on code it had never seen.</h2>
          <p class="lede">{fmt(CORPUS['repos'])} public repositories, chosen and pinned to a commit <strong>before</strong> qxlint was run on any of them.</p>
        </div>
        <div class="stats">
          <div class="stat reveal"><h3>{fmt(CORPUS['py'] + CORPUS['notebooks'])} files</h3><p>{fmt(CORPUS['py'])} Python files and {fmt(CORPUS['notebooks'])} notebooks, from {fmt(CORPUS['owners'])} different owners.</p></div>
          <div class="stat reveal"><h3>{fmt(CORPUS['failed'])} failed runs</h3><p>{"No repository" if CORPUS['failed'] == 0 else f"{fmt(CORPUS['failed'])} repositories"} made qxlint exit with code 2, which means it could not run.</p></div>
          <div class="stat reveal"><h3>{fmt(CORPUS['findings'])} findings</h3><p>{fmt(CORPUS['outside'])} of them outside QXL205, the rule for names Qiskit removed.</p></div>
          <div class="stat reveal"><h3>{fmt(CORPUS['read'])} read one by one</h3><p>Each read in context and labeled. The labels are an AI reviewer’s, not yet confirmed by a person, and the write-up says so.</p></div>
        </div>
        <ul class="limits reveal">
          <li><strong>No interprocedural analysis.</strong> A circuit changed inside a helper is not tracked, and a circuit that arrives as a parameter or a return value carries no facts.</li>
          <li><strong>No published precision figure.</strong> The labels are not an independent measurement, and the release gate says exactly what is and is not claimed.</li>
          <li><strong>One interpreter’s view.</strong> qxlint parses with the Python running it, so run the same version locally and in CI.</li>
          <li><strong>Client side only.</strong> What qxlint says about IBM Runtime is about its client side validation, read from its source, never about server behavior.</li>
        </ul>
        <p class="note reveal">Scanned with qxlint {CORPUS['version']} on {date(CORPUS['on'])}. <a class="more" href="{REPO}/blob/main/docs/release-gate.md">The release gate: what is claimed, and what is not</a></p>
      </div>
    </section>

    <hr class="divider">

    <section class="section" id="questions" aria-labelledby="questions-title">
      <div class="wrap">
        <h2 class="headline center reveal" id="questions-title">Questions.</h2>
        <div class="faq reveal">
{faq_html}
        </div>
      </div>
    </section>

    <section class="closing" aria-labelledby="get-title">
      <div class="wrap reveal">
        <img class="hero-icon" src="images/qxlint-icon-256.webp" width="128" height="128" loading="lazy" decoding="async" alt="">
        <h2 class="headline" id="get-title">Get qxlint.</h2>
        <p class="lede">Free and open source, under the MIT License.</p>
        <div class="command">
          <code>{COMMAND}</code>
          <button class="copy" type="button" data-copy="{COMMAND}">Copy</button>
        </div>
        <div class="actions">
          <a class="more" href="{PYPI}">PyPI</a>
          <a class="more" href="{NPM}">npm</a>
          <a class="more" href="{MARKETPLACE}">VS Code</a>
          <a class="more" href="{OPENVSX}">Open VSX</a>
        </div>
        <a class="pill pill-ghost sponsor" href="{SPONSOR}">{HEART}Sponsor on GitHub</a>
      </div>
    </section>
  </main>

  <footer>
    <div class="wrap">
      <nav aria-label="More about qxlint">
        <ul>
          <li><a href="{REPO}">Source code</a></li>
          <li><a href="{REPO}/blob/main/docs/rules/index.md">Rules</a></li>
          <li><a href="{REPO}/blob/main/docs/configuration.md">Configuration</a></li>
          <li><a href="{REPO}/releases">Releases</a></li>
          <li><a href="{REPO}/issues">Report an issue</a></li>
          <li><a href="{SPONSOR}">Sponsor</a></li>
        </ul>
      </nav>
      <p class="maker">Made by <a href="https://tuguidragos.com/">Țugui Dragoș</a>.</p>
      <nav aria-label="Țugui Dragoș elsewhere">
        <ul>
{profile_items}
        </ul>
      </nav>
      <p>Copyright © 2026 Țugui Dragoș. qxlint is free software under the <a href="{REPO}/blob/main/LICENSE">MIT License</a>.</p>
      <p>Qiskit is a trademark of IBM Corporation. qxlint is an independent project and is not affiliated with or endorsed by IBM.</p>
    </div>
  </footer>
</body>
</html>
"""
page = "\n".join(line.rstrip() for line in page.split("\n"))
# The page is dated by what it says, not by when it was built. When the published page says exactly the same, its date
# stands, so a push that changes nothing here does not tell search engines that the page changed.
DATED = re.compile(r'"dateModified": "\d{4}-\d\d-\d\d"')
modified = datetime.date.today().isoformat()
try:
    with urllib.request.urlopen(SITE, timeout=20) as response:
        published = response.read().decode()
    if DATED.sub("", published) == DATED.sub("", page):
        modified = re.search(r'"dateModified": "(\d{4}-\d\d-\d\d)"', published).group(1)
except (OSError, ValueError, AttributeError):
    pass
page = DATED.sub(f'"dateModified": "{modified}"', page)
(WORK / "modified.txt").write_text(modified)
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "index.html").write_text(page, encoding="utf-8")
visible = re.sub(r"<[^>]+>", " ", re.sub(r"<pre.*?</pre>", "", page, flags=re.S))
british = sorted(set(re.findall(r"\b(analyse|analysed|analyser\w*|behaviour|colour\w*|licence|modell\w*|labell\w*|cancell\w*|recognis\w*|organis\w*|optimis\w*|summaris\w*|initialis\w*|normalis\w*|characteris\w*|randomis\w*|minimis\w*|maximis\w*|realis\w*|utilis\w*|centre\w*)\b", visible)))
assert not british, f"American English on the page, but it reads {british}"
print(f"index.html: {len(rules)} rules, {TESTS:,} tests, {MODEL_CHECKS} model checks, qxlint {VERSION}")
