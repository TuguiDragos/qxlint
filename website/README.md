# qxlint.tuguidragos.com

The website is built from this repository, so its figures follow the code instead of being typed into the page:

| On the page | Read from |
| --- | --- |
| The rules, their examples and what qxlint printed for each | `docs/rules/*.md`, and qxlint run on every example |
| Tests | the suite run on this tree as CI runs it: the tests that pass, which is what the README quotes |
| API checks | `scripts/verify_model.py`, run during the build |
| The corpus run, and the version and date it was scanned with | `corpus/scan.json`, `corpus/manifest.json`, `corpus/findings.csv` |
| Version, supported Pythons | `pyproject.toml`, checked against the CI matrix |
| The "How it decides" examples | qxlint run on each, which must report exactly where the comments say it does |
| The QXL201 table | qxlint run on the rule's example under every target the table names |
| The integration cards | the hook ids, the Action's inputs, the CLI's flags and the flake8 entry point, looked up where they are defined, and the configuration block, which qxlint must accept |
| The 404 terminal | qxlint run on a path that does not exist |

Every figure is checked for consistency with the files it comes from, and every claim in the table above is run or
looked up. When one no longer holds, the build stops with the reason instead of publishing a page that says something
untrue, and the site already online stays as it was.

The rest is written by hand: the opening statement, the notebook table, the limits, the FAQ and the wording around
the cards. The build cannot tell when those stop being true, so a change to what qxlint does should be read against
them too.

The page is dated by what it says, not by when it was built: the build compares the page with the one already
online and keeps that page's date unless something on it changed, so `dateModified` and the sitemap's `lastmod` only
move when the page does. `sitemap.css` gives `sitemap.xml` a readable look in a browser; it is CSS rather than XSLT,
which Chrome removes on November 17, 2026.

## How it is published

`.github/workflows/website.yml` builds the site on every push to `main` and publishes it to GitHub Pages. Once, in the
repository's **Settings > Pages**: set **Source** to **GitHub Actions**, and **Custom domain** to
`qxlint.tuguidragos.com`. At the DNS provider, `qxlint` is a `CNAME` to `tuguidragos.github.io`.

## Building it locally

```bash
uv sync --extra circuit
npm ci --prefix website
website/build.sh
```

The page is then in `website/_site`. Serve it with `python -m http.server -d website/_site` and open
<http://localhost:8000>.

## What lives where

| Path | What it is |
| --- | --- |
| `scripts/` | the build: rule extraction, the page, the 404, `llms.txt`, robots, sitemap |
| `static/` | copied as is: the stylesheet, the script, the icon at every size, the share image |
| `theme/` | Tapetum Quantum, which colors every code sample |
| `tools/` | run by hand, only when the icon or the share image should change |

`tools/make_images.py` remakes the icons from `readme-assets/png/qxlint-icon-256.png`
(`uv run --with pillow python website/tools/make_images.py`), and `tools/make_card.mjs` remakes the share image and
`_build/github-social-preview.png`, the picture to upload in **Settings > Social preview**. It needs Playwright once:
`npm install --no-save --prefix website playwright@1`, then `npx --prefix website playwright install chromium`.
