"""Writes the small files around qxlint's page: manifest, robots, sitemap, llms.txt, CNAME and .nojekyll."""
import json
import re
import tomllib
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
site, rules = WEB / "_site", json.loads((WEB / "_build/rules.json").read_text())
classifiers = tomllib.loads((WEB.parent / "pyproject.toml").read_text())["project"]["classifiers"]
pythons = sorted((c.rsplit(":: ", 1)[1] for c in classifiers if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)),
                 key=lambda v: int(v.split(".")[1]))
SITE = "https://qxlint.tuguidragos.com/"
(site / "site.webmanifest").write_text(json.dumps({
    "name": "qxlint", "short_name": "qxlint",
    "description": "Static checks for Qiskit Primitives V2 code.",
    "start_url": "/", "display": "browser", "background_color": "#0c1016", "theme_color": "#0c1016",
    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/icon-256.png", "sizes": "256x256", "type": "image/png"}],
}, indent=2) + "\n")
(site / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n")
(site / "sitemap.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/css" href="/sitemap.css"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE}</loc>
    <lastmod>{(WEB / "_build/modified.txt").read_text()}</lastmod>
  </url>
</urlset>
""")
(site / "CNAME").write_text("qxlint.tuguidragos.com\n")
(site / ".nojekyll").write_text("")
american = lambda s: s.replace("analyser", "analyzer").replace("cancelling", "canceling").replace("unmodelled", "unmodeled")
rule_lines = "\n".join(f"- {r['code']} ({r['tier']}, {r['severity']}{', library API' if r['library'] else ''}): {american(r['title'])}" for r in rules)
(site / "llms.txt").write_text(f"""# qxlint

> qxlint is a free, open source linter for Python code that uses Qiskit. It finds the mistakes the move from the V1 to the V2 primitives introduced: counts read off the wrong object, a V1 field on a V2 result, a circuit sampled without a measurement, and a channel value a qiskit-ibm-runtime release has removed. It reads source without importing or running it, makes no network requests, and needs no quantum hardware.

A rule fires only on what the analyzer can prove, and every rule page documents when the pattern it catches is legitimate. Run it with `uvx qxlint .`, or install it with `pip install qxlint`. It needs Python {pythons[0]} to {pythons[-1]}; Qiskit is optional and only the checks on circuits in memory need it. It is free software under the MIT License, by Țugui Dragoș.

## Rules

{rule_lines}

## Install

- [PyPI](https://pypi.org/project/qxlint/): the analyzer, `pip install qxlint`
- [npm](https://www.npmjs.com/package/@tuguidragos/qxlint): a launcher for JavaScript toolchains, `npx @tuguidragos/qxlint .`, which still needs Python
- [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=tuguidragos.qxlint): the editor extension
- [Open VSX](https://open-vsx.org/extension/tuguidragos/qxlint): the same extension, for editors that install from Open VSX

## Docs

- [README](https://raw.githubusercontent.com/TuguiDragos/qxlint/main/README.md): what qxlint checks, how it decides, and how it is tested
- [Rules](https://raw.githubusercontent.com/TuguiDragos/qxlint/main/docs/rules/index.md): every rule, with its tier and severity, linking to the page that says when it is legitimate
- [Configuration](https://raw.githubusercontent.com/TuguiDragos/qxlint/main/docs/configuration.md): every option
- [Release gate](https://raw.githubusercontent.com/TuguiDragos/qxlint/main/docs/release-gate.md): what is claimed and what is not

## Optional

- [Source code](https://github.com/TuguiDragos/qxlint)
- [Sponsor](https://github.com/sponsors/TuguiDragos): GitHub Sponsors
- [Author](https://tuguidragos.com/about/): Țugui Dragoș
""")
print("extras written")
