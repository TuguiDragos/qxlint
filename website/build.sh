#!/usr/bin/env bash
# Builds the website into website/_site from the repository it sits in. It needs the project's environment
# (uv sync --extra circuit) and the website's own packages (npm ci --prefix website), and stops at the first figure or
# quoted sentence that no longer holds, so a page that would say something untrue is never written.
set -euo pipefail
web="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$web/.."
rm -rf "$web/_build" "$web/_site"
mkdir -p "$web/_build" "$web/_site"

# What the page quotes, measured on this tree: the test suite run as CI runs it, the model check, and what qxlint says
# about a path that is not there, which is what the 404 page shows. A failing test stops the build here.
uv run --no-sync pytest -p no:cacheprovider > "$web/_build/tests.txt"
uv run --no-sync python scripts/verify_model.py > "$web/_build/model.txt"
status=0
uv run --no-sync qxlint "$web/_build/no-such-path" > "$web/_build/missing.txt" 2>&1 || status=$?
echo "exit $status" >> "$web/_build/missing.txt"

uv run --no-sync python "$web/scripts/extract_rules.py" "$web/_build/rules.json"
cp -R "$web/static/." "$web/_site/"
uv run --no-sync python "$web/scripts/build_site.py"
uv run --no-sync python "$web/scripts/make_404.py"
uv run --no-sync python "$web/scripts/make_extras.py"
echo "built $web/_site"
