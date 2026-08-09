"""Output formats: text, json, sarif."""

from __future__ import annotations

from qxlint.output.json_format import render_json
from qxlint.output.sarif import render_sarif
from qxlint.output.text import render_text

FORMATS = {"text": render_text, "json": render_json, "sarif": render_sarif}

__all__ = ["FORMATS", "render_json", "render_sarif", "render_text"]
