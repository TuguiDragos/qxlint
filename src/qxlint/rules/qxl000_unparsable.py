"""QXL000: the file or cell could not be parsed.

Emitted by the engine, not by the rule pipeline. It is registered so it appears
in the generated docs and in the SARIF rule index like any other code.
"""

from __future__ import annotations

from qxlint.diagnostics import Severity, Tier
from qxlint.registry import register
from qxlint.rules.base import Rule, RuleMeta

CODE = "QXL000"


@register
class Unparsable(Rule):
    meta = RuleMeta(
        code=CODE,
        name="unparsable-source",
        summary="source could not be parsed",
        tier=Tier.DEFAULT,
        severity=Severity.ERROR,
        rationale=(
            "The file is not valid Python for the interpreter running qxlint, or "
            "the notebook is not valid nbformat JSON. Nothing downstream can run. "
            "An interpreter cannot parse syntax newer than itself, so code using "
            "3.14 only syntax needs qxlint to run on 3.14."
        ),
        when_legitimate=(
            "Never as a finding to ignore, though a file that is intentionally not "
            "Python should be excluded rather than suppressed."
        ),
        bad_example="def f(\n",
        good_example="def f():\n    pass\n",
    )
