"""Rule registry.

Every rule registers itself here. The registry is the single source for the CLI
selection logic, the flake8 plugin and the generated documentation, so adding a
rule means adding one module and one test module and nothing else.
"""

from __future__ import annotations

from qxlint.diagnostics import Tier
from qxlint.rules.base import Rule, RuleMeta, RuleSet

_REGISTRY: dict[str, type[Rule]] = {}


def register(rule_class: type[Rule]) -> type[Rule]:
    """Class decorator that adds a rule to the registry."""
    meta = rule_class.meta
    if meta.code in _REGISTRY:
        raise RuntimeError(f"duplicate rule code {meta.code}")
    _REGISTRY[meta.code] = rule_class
    return rule_class


def _load() -> None:
    """Import rule modules for their registration side effect."""
    from qxlint.circuit import (  # noqa: F401
        qxl300_analysis_depth,
        qxl301_target,
        qxl302_self_inverse,
        qxl303_unused_qubit,
    )
    from qxlint.rules import (  # noqa: F401
        qxl000_unparsable,
        qxl101_get_counts_receiver,
        qxl102_quasi_dists,
        qxl103_unmeasured_sampler,
        qxl104_discarded_result,
        qxl105_measured_to_statevector_estimator,
        qxl201_ibm_quantum_channel,
        qxl202_runtime_primitive_mode,
        qxl203_session_service,
        qxl204_v1_run_signature,
    )


def all_rules() -> dict[str, type[Rule]]:
    _load()
    return dict(_REGISTRY)


def all_meta() -> list[RuleMeta]:
    return sorted((cls.meta for cls in all_rules().values()), key=lambda meta: meta.code)


# Circuit rules live in `qxlint.circuit` and read an in-memory circuit, so a run
# over files can never reach them however they are selected.
CIRCUIT_PACKAGE = "qxlint.circuit"


def source_reachable() -> frozenset[str]:
    """Codes a run over files can report."""
    return frozenset(
        code for code, cls in all_rules().items() if not cls.__module__.startswith(CIRCUIT_PACKAGE)
    )


def tiers() -> dict[str, Tier]:
    return {code: cls.meta.tier for code, cls in all_rules().items()}


def build_ruleset(codes: frozenset[str]) -> RuleSet:
    registry = all_rules()
    active = [registry[code]() for code in sorted(codes) if code in registry]
    return RuleSet(rules=tuple(active))
