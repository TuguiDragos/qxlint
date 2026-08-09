"""Rule contract and the events rules observe.

Rules never walk the AST. The analyser resolves values and emits typed events, so
a rule only decides whether a known shape is wrong. That keeps the aliasing,
container and control flow logic in one place instead of once per rule.

Each rule carries its own documentation. The docs pages are generated from
:class:`RuleMeta`, so a rule really is one module plus one test module.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field

from qxlint.diagnostics import Finding, Severity, Tier
from qxlint.profile import SemanticProfile
from qxlint.semantics.objects import ObjectFacts
from qxlint.semantics.state import State
from qxlint.semantics.values import AbstractValue
from qxlint.source import SourceFile


@dataclass(frozen=True, slots=True)
class RuleMeta:
    """Everything a rule must document about itself.

    ``when_legitimate`` is mandatory. A pattern nobody can defend is not a rule,
    it is a style preference.
    """

    code: str
    name: str
    summary: str
    tier: Tier
    severity: Severity
    rationale: str
    when_legitimate: str
    bad_example: str
    good_example: str
    references: tuple[str, ...] = ()
    version_gated: bool = False
    # Engine A examples are executed by the test suite: the bad one must produce
    # this rule and the good one must produce nothing. Engine B examples are
    # circuit fragments with no surrounding module, so they are not checkable.
    examples_checkable: bool = True
    example_target_runtime: str | None = None


@dataclass(frozen=True, slots=True)
class CallEvent:
    """A call whose callee resolved to a known symbol or object."""

    node: ast.Call
    callee: AbstractValue
    # Always set: the event is only raised for a callee that resolved to an
    # imported symbol, which carries its qualified name.
    qualified_name: str
    args: tuple[AbstractValue, ...]
    kwargs: dict[str, AbstractValue]
    keyword_nodes: dict[str, ast.expr]
    state: State


@dataclass(frozen=True, slots=True)
class MethodCallEvent:
    """A call of the form ``receiver.method(...)``.

    ``result_discarded`` is True when the call is a bare expression statement,
    so whatever it returned is thrown away. For a method that returns a new
    object instead of mutating the receiver, that makes the whole statement a
    silent no-op.
    """

    node: ast.Call
    attribute_node: ast.Attribute
    method: str
    receiver: AbstractValue
    receiver_facts: ObjectFacts | None
    args: tuple[AbstractValue, ...]
    kwargs: dict[str, AbstractValue]
    state: State
    result_discarded: bool = False


@dataclass(frozen=True, slots=True)
class AttributeEvent:
    """A plain attribute read, not a call."""

    node: ast.Attribute
    attribute: str
    receiver: AbstractValue
    receiver_facts: ObjectFacts | None
    state: State


@dataclass(frozen=True, slots=True)
class PubArgument:
    """One circuit reaching a primitive, with the value it came from."""

    value: AbstractValue
    facts: ObjectFacts | None


@dataclass(frozen=True, slots=True)
class PrimitiveRunEvent:
    """A ``.run(...)`` on a V2 primitive, with the circuits it received."""

    node: ast.Call
    primitive_facts: ObjectFacts
    pubs: tuple[PubArgument, ...]
    pubs_complete: bool
    state: State


@dataclass
class RuleContext:
    """What a rule may consult, and how it reports."""

    source: SourceFile
    profile: SemanticProfile
    emit: Callable[[Finding], None]


class Rule:
    """Base rule. Override only the hooks a rule needs."""

    meta: RuleMeta

    def on_call(self, event: CallEvent, ctx: RuleContext) -> None:
        """A direct call such as ``QiskitRuntimeService(...)``."""

    def on_method_call(self, event: MethodCallEvent, ctx: RuleContext) -> None:
        """A method call such as ``result.get_counts()``."""

    def on_attribute(self, event: AttributeEvent, ctx: RuleContext) -> None:
        """An attribute read such as ``result.quasi_dists``."""

    def on_primitive_run(self, event: PrimitiveRunEvent, ctx: RuleContext) -> None:
        """A sampler or estimator receiving circuits."""


@dataclass
class RuleSet:
    """Rules active for one run, indexed by the hook they use."""

    rules: tuple[Rule, ...] = ()
    _by_hook: dict[str, tuple[Rule, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        hooks = ("on_call", "on_method_call", "on_attribute", "on_primitive_run")
        for hook in hooks:
            self._by_hook[hook] = tuple(
                rule for rule in self.rules if getattr(type(rule), hook) is not getattr(Rule, hook)
            )

    def for_hook(self, hook: str) -> tuple[Rule, ...]:
        return self._by_hook.get(hook, ())
