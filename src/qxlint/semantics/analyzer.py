"""The abstract interpreter over Python source.

Design notes that matter for correctness:

* **Aliasing.** A name binds to an object identity, not to facts, so
  ``alias = qc; alias.measure_all()`` updates what ``qc`` sees.
* **Local containers are not escapes.** ``pubs = [qc]`` followed by
  ``sampler.run(pubs)`` keeps ``qc`` local and analysable, because that is how
  most Sampler code is written.
* **Effects are scoped.** ``print("hi")`` cannot reach ``qc`` and leaves it
  alone. A call that does receive ``qc`` marks it escaped, since unmodelled code
  may keep the reference and mutate it later.
* **Branches join, they do not pick.** Anything a join cannot decide becomes
  MAYBE or UNKNOWN, and rules stay silent on both.

There is no interprocedural analysis in v0.1. A function body is analysed in its
own scope, and calling a function defined in the same module invalidates every
mutable fact, because that call can reach module level objects.
"""

from __future__ import annotations

import ast

from qxlint.rules.base import (
    AttributeEvent,
    CallEvent,
    MethodCallEvent,
    PrimitiveRunEvent,
    PubArgument,
    RuleContext,
    RuleSet,
)
from qxlint.semantics import model
from qxlint.semantics.objects import (
    PUB_RESULT_KINDS,
    Escape,
    ObjectFacts,
    ObjectKind,
    Provenance,
    TriState,
)
from qxlint.semantics.state import State, import_only_env, merge_states
from qxlint.semantics.values import (
    NONE,
    UNKNOWN,
    AbstractValue,
    ConstBool,
    ConstInt,
    ConstStr,
    ImportedSymbol,
    ObjectRef,
    Sequence,
    Unbound,
    Union,
    is_definite,
    iter_options,
    join,
)
from qxlint.source import SourceFile

BARRIER_NAME = "__qxlint_barrier__"
UNKNOWN_NAME = "__qxlint_unknown__"

LOOP_PASSES = 2
MAX_DEPTH = 60

# Builtins that cannot retain or mutate what they are given. Passing a circuit to
# one of these must not cost the facts about it, since `print(qc)` is common.
PURE_BUILTINS = frozenset(
    {
        "abs",
        "bool",
        "display",
        "float",
        "format",
        "hash",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "len",
        "max",
        "min",
        "print",
        "range",
        "repr",
        "round",
        "str",
        "sum",
        "type",
    }
)

# IPython call forms that nbconvert leaves behind, and that IPython's own cell
# transformer produces. A magic that can rebind names is a barrier.
NAMESPACE_MUTATING_MAGICS = frozenset(
    {
        "run",
        "load",
        "paste",
        "cpaste",
        "recall",
        "rerun",
        "macro",
        "store",
        "reset",
        "reset_selective",
        "pylab",
        "edit",
        "code_wrap",
        "autocall",
    }
)


class Analyzer:
    """Walks one module or one notebook cell, emitting events to the rules."""

    def __init__(self, source: SourceFile, ruleset: RuleSet, ctx: RuleContext) -> None:
        self.source = source
        self.ruleset = ruleset
        self.ctx = ctx
        self.local_callables: set[str] = set()
        self._depth = 0
        self._seq_token = 0
        # The call currently being evaluated as a bare statement, so a rule can
        # spot a no-op. This holds the node itself rather than its id(): an id is
        # a memory address, it is reused once the node is collected, and a stale
        # entry then makes an unrelated call look discarded.
        self._discarded_call: ast.Call | None = None
        # Depth inside an exception assertion, where discarding is the point.
        self._raises_depth = 0

    # Statements ---------------------------------------------------------

    def run(self, tree: ast.Module, state: State) -> State:
        self._exec_body(tree.body, state)
        return state

    def _exec_body(self, body: list[ast.stmt], state: State) -> None:
        for stmt in body:
            if not state.reachable:
                return
            self._exec(stmt, state)

    def _exec(self, node: ast.stmt, state: State) -> None:
        handler = getattr(self, f"_stmt_{type(node).__name__}", None)
        if handler is None:
            self._generic_stmt(node, state)
            return
        handler(node, state)

    def _generic_stmt(self, node: ast.stmt, state: State) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._eval(child, state)
            elif isinstance(child, ast.stmt):  # pragma: no cover
                # Unreachable today: every statement kind that has statement
                # children has its own handler. Kept so a future grammar
                # addition degrades to a walk rather than to silence.
                self._exec(child, state)

    def _stmt_Expr(self, node: ast.Expr, state: State) -> None:
        # Inside `with assertRaises(...)` the call is expected to raise before it
        # returns anything, so a discarded result is intentional, not a no-op.
        if isinstance(node.value, ast.Call) and self._raises_depth == 0:
            previous = self._discarded_call
            self._discarded_call = node.value
            try:
                self._eval(node.value, state)
            finally:
                self._discarded_call = previous
            return
        self._eval(node.value, state)

    def _stmt_Pass(self, node: ast.Pass, state: State) -> None:
        del node, state

    def _stmt_Import(self, node: ast.Import, state: State) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            state.bind(bound, ImportedSymbol(model.canonical(target)))

    def _stmt_ImportFrom(self, node: ast.ImportFrom, state: State) -> None:
        if node.level:
            for alias in node.names:
                state.bind(alias.asname or alias.name, UNKNOWN)
            return
        module = node.module or ""
        for alias in node.names:
            qualified = f"{module}.{alias.name}" if module else alias.name
            state.bind(alias.asname or alias.name, ImportedSymbol(model.canonical(qualified)))

    def _stmt_Assign(self, node: ast.Assign, state: State) -> None:
        value = self._eval(node.value, state)
        for target in node.targets:
            self._assign(target, value, state)

    def _stmt_AnnAssign(self, node: ast.AnnAssign, state: State) -> None:
        if node.value is None:
            return
        value = self._eval(node.value, state)
        self._assign(node.target, value, state)

    def _stmt_AugAssign(self, node: ast.AugAssign, state: State) -> None:
        current = self._eval(node.target, state) if isinstance(node.target, ast.Name) else UNKNOWN
        addition = self._eval(node.value, state)
        if (
            isinstance(node.op, ast.Add)
            and isinstance(current, Sequence)
            and current.local
            and current.elements is not None
            and isinstance(addition, Sequence)
            and addition.elements is not None
        ):
            merged = Sequence(current.elements + addition.elements, local=True)
            self._assign(node.target, merged, state)
            return
        state.escape_reachable(addition)
        self._assign(node.target, UNKNOWN, state)

    def _stmt_Delete(self, node: ast.Delete, state: State) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                state.unbind(target.id)
            else:
                self._eval(target, state)

    def _stmt_Return(self, node: ast.Return, state: State) -> None:
        if node.value is not None:
            state.escape_reachable(self._eval(node.value, state))
        state.reachable = False

    def _stmt_Raise(self, node: ast.Raise, state: State) -> None:
        self._generic_stmt(node, state)
        state.reachable = False

    def _stmt_Break(self, node: ast.Break, state: State) -> None:
        del node
        state.reachable = False

    def _stmt_Continue(self, node: ast.Continue, state: State) -> None:
        del node
        state.reachable = False

    def _stmt_Global(self, node: ast.Global, state: State) -> None:
        for name in node.names:
            state.escape_reachable(state.lookup(name))
            state.bind(name, UNKNOWN)

    def _stmt_Nonlocal(self, node: ast.Nonlocal, state: State) -> None:
        for name in node.names:
            state.escape_reachable(state.lookup(name))
            state.bind(name, UNKNOWN)

    def _stmt_If(self, node: ast.If, state: State) -> None:
        self._eval(node.test, state)
        body_state = state.copy()
        else_state = state.copy()
        self._exec_body(node.body, body_state)
        self._exec_body(node.orelse, else_state)
        self._replace(state, merge_states([body_state, else_state]))

    def _stmt_For(self, node: ast.For, state: State) -> None:
        self._loop(node, state, node.iter)

    def _stmt_AsyncFor(self, node: ast.AsyncFor, state: State) -> None:
        self._loop(node, state, node.iter)

    def _stmt_While(self, node: ast.While, state: State) -> None:
        self._eval(node.test, state)
        self._loop(node, state, None)

    def _loop(self, node: ast.stmt, state: State, iterable: ast.expr | None) -> None:
        """Loops merge with the zero iteration path, so a body mutation is MAYBE.

        The body is walked twice so a fact created on the first pass is visible
        on the second, which is enough to reach a fixed point for the facts this
        analyser tracks.
        """
        iter_value = self._eval(iterable, state) if iterable is not None else UNKNOWN
        target = getattr(node, "target", None)
        if target is not None:
            self._assign(target, self._element_of(iter_value), state)

        body = getattr(node, "body", [])
        orelse = getattr(node, "orelse", [])

        accumulated = state.copy()
        for _ in range(LOOP_PASSES):
            pass_state = accumulated.copy()
            pass_state.reachable = True
            self._exec_body(body, pass_state)
            accumulated = merge_states([accumulated, pass_state])
        self._exec_body(orelse, accumulated)
        self._replace(state, accumulated)

    def _stmt_Try(self, node: ast.Try, state: State) -> None:
        self._try(node, state)

    def _stmt_TryStar(self, node: ast.Try, state: State) -> None:
        self._try(node, state)

    def _try(self, node: ast.Try, state: State) -> None:
        """A handler can start anywhere in the body, so it starts from the join."""
        body_state = state.copy()
        # A guarded body is written to survive an exception, so a call there whose
        # result is dropped is being exercised for what it raises, exactly like
        # one inside assertRaises. Reporting a no-op in it would be wrong.
        guarded = bool(node.handlers)
        if guarded:
            self._raises_depth += 1
        try:
            self._exec_body(node.body, body_state)
        finally:
            if guarded:
                self._raises_depth -= 1

        entry = merge_states([state.copy(), body_state.copy()])
        ends = [body_state]
        for handler in node.handlers:
            handler_state = entry.copy()
            handler_state.reachable = True
            if handler.name:
                handler_state.bind(handler.name, UNKNOWN)
            self._exec_body(handler.body, handler_state)
            ends.append(handler_state)

        if node.orelse:
            self._exec_body(node.orelse, body_state)

        merged = merge_states(ends)
        if node.finalbody:
            merged.reachable = True
            self._exec_body(node.finalbody, merged)
        self._replace(state, merged)

    def _stmt_With(self, node: ast.With, state: State) -> None:
        self._with(node, state)

    def _stmt_AsyncWith(self, node: ast.AsyncWith, state: State) -> None:
        self._with(node, state)

    def _with(self, node: ast.With | ast.AsyncWith, state: State) -> None:
        asserts_raise = any(_is_raises_context(item.context_expr) for item in node.items)
        for item in node.items:
            value = self._eval(item.context_expr, state)
            if item.optional_vars is not None:
                self._assign(item.optional_vars, value, state)
        if asserts_raise:
            self._raises_depth += 1
        try:
            self._exec_body(node.body, state)
        finally:
            if asserts_raise:
                self._raises_depth -= 1

    def _stmt_Match(self, node: ast.Match, state: State) -> None:
        self._eval(node.subject, state)
        branches: list[State] = []
        has_wildcard = False
        for case in node.cases:
            case_state = state.copy()
            self._bind_pattern(case.pattern, case_state)
            if case.guard is not None:
                self._eval(case.guard, case_state)
            self._exec_body(case.body, case_state)
            branches.append(case_state)
            if isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None:
                has_wildcard = True
        if not has_wildcard:
            branches.append(state.copy())
        self._replace(state, merge_states(branches))

    def _bind_pattern(self, pattern: ast.pattern, state: State) -> None:
        for node in ast.walk(pattern):
            if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
                state.bind(node.name, UNKNOWN)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                state.bind(node.rest, UNKNOWN)

    def _stmt_FunctionDef(self, node: ast.FunctionDef, state: State) -> None:
        self._function(node, state)

    def _stmt_AsyncFunctionDef(self, node: ast.AsyncFunctionDef, state: State) -> None:
        self._function(node, state)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, state: State) -> None:
        for decorator in node.decorator_list:
            self._eval(decorator, state)
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self._eval(default, state)

        inner = State(env=import_only_env(state.env))
        for arg in self._arg_names(node.args):
            inner.bind(arg, UNKNOWN)
        self._exec_body(node.body, inner)

        state.bind(node.name, UNKNOWN)
        self.local_callables.add(node.name)

    def _stmt_ClassDef(self, node: ast.ClassDef, state: State) -> None:
        for decorator in node.decorator_list:
            self._eval(decorator, state)
        for base in node.bases:
            self._eval(base, state)
        inner = State(env=import_only_env(state.env))
        self._exec_body(node.body, inner)
        state.bind(node.name, UNKNOWN)
        self.local_callables.add(node.name)

    @staticmethod
    def _arg_names(args: ast.arguments) -> list[str]:
        collected = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        names = [arg.arg for arg in collected]
        if args.vararg:
            names.append(args.vararg.arg)
        if args.kwarg:
            names.append(args.kwarg.arg)
        return names

    # Assignment ---------------------------------------------------------

    def _assign(self, target: ast.expr, value: AbstractValue, state: State) -> None:
        if isinstance(target, ast.Name):
            state.bind(target.id, value)
            return
        if isinstance(target, ast.Tuple | ast.List):
            element = self._element_of(value)
            for item in target.elts:
                if isinstance(item, ast.Starred):
                    self._assign(item.value, Sequence(None, local=False), state)
                else:
                    self._assign(item, element, state)
            return
        if isinstance(target, ast.Attribute):
            self._eval(target.value, state)
            state.escape_reachable(value)
            return
        if isinstance(target, ast.Subscript):
            container = self._eval(target.value, state)
            self._eval(target.slice, state)
            if isinstance(container, Sequence) and container.local:
                state.escape_reachable(value)
                return
            state.escape_reachable(value)
            return
        # Unreachable from parsed source: an assignment target is always a
        # Name, Attribute, Subscript, Tuple, List or Starred, and each is
        # handled above. Kept so an unexpected target escapes rather than
        # silently keeping a stale fact.
        self._eval(target, state)  # pragma: no cover
        state.escape_reachable(value)  # pragma: no cover

    @staticmethod
    def _element_of(value: AbstractValue) -> AbstractValue:
        """Value obtained by iterating or unpacking a container."""
        if isinstance(value, Sequence):
            if value.elements is None:
                return UNKNOWN
            if not value.elements:
                return UNKNOWN
            merged = value.elements[0]
            for element in value.elements[1:]:
                merged = join(merged, element)
            return merged
        return UNKNOWN

    @staticmethod
    def _replace(state: State, merged: State) -> None:
        state.env = merged.env
        state.store = merged.store
        state.reachable = merged.reachable

    # Expressions --------------------------------------------------------

    def _eval(self, node: ast.expr | None, state: State) -> AbstractValue:
        if node is None:
            return UNKNOWN
        if self._depth > MAX_DEPTH:
            return UNKNOWN
        self._depth += 1
        try:
            handler = getattr(self, f"_expr_{type(node).__name__}", None)
            if handler is None:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.expr):
                        self._eval(child, state)
                return UNKNOWN
            result: AbstractValue = handler(node, state)
            return result
        finally:
            self._depth -= 1

    def _expr_Name(self, node: ast.Name, state: State) -> AbstractValue:
        return state.lookup(node.id)

    def _expr_Constant(self, node: ast.Constant, state: State) -> AbstractValue:
        del state
        value = node.value
        if isinstance(value, bool):
            return ConstBool(value)
        if isinstance(value, str):
            return ConstStr(value)
        if isinstance(value, int):
            return ConstInt(value)
        if value is None:
            return NONE
        return UNKNOWN

    def _expr_List(self, node: ast.List, state: State) -> AbstractValue:
        return self._sequence_literal(node.elts, state, mutable=True)

    def _expr_Tuple(self, node: ast.Tuple, state: State) -> AbstractValue:
        return self._sequence_literal(node.elts, state, mutable=False)

    def _expr_Set(self, node: ast.Set, state: State) -> AbstractValue:
        for element in node.elts:
            state.escape_reachable(self._eval(element, state))
        return UNKNOWN

    def _expr_Dict(self, node: ast.Dict, state: State) -> AbstractValue:
        for key in node.keys:
            self._eval(key, state)
        for value in node.values:
            state.escape_reachable(self._eval(value, state))
        return UNKNOWN

    def _sequence_literal(
        self, elements: list[ast.expr], state: State, *, mutable: bool
    ) -> AbstractValue:
        values: list[AbstractValue] = []
        complete = True
        for element in elements:
            if isinstance(element, ast.Starred):
                inner = self._eval(element.value, state)
                if isinstance(inner, Sequence) and inner.elements is not None:
                    values.extend(inner.elements)
                else:
                    complete = False
                continue
            values.append(self._eval(element, state))
        self._seq_token += 1
        token = self._seq_token
        if not complete or len(values) > 64:
            return Sequence(None, local=True, mutable=mutable, token=token)
        return Sequence(tuple(values), local=True, mutable=mutable, token=token)

    def _expr_Starred(self, node: ast.Starred, state: State) -> AbstractValue:
        return self._eval(node.value, state)

    def _expr_NamedExpr(self, node: ast.NamedExpr, state: State) -> AbstractValue:
        value = self._eval(node.value, state)
        self._assign(node.target, value, state)
        return value

    def _expr_IfExp(self, node: ast.IfExp, state: State) -> AbstractValue:
        self._eval(node.test, state)
        return join(self._eval(node.body, state), self._eval(node.orelse, state))

    def _expr_BoolOp(self, node: ast.BoolOp, state: State) -> AbstractValue:
        values = [self._eval(value, state) for value in node.values]
        merged = values[0]
        for value in values[1:]:
            merged = join(merged, value)
        return merged

    def _expr_Await(self, node: ast.Await, state: State) -> AbstractValue:
        self._eval(node.value, state)
        return UNKNOWN

    def _expr_Lambda(self, node: ast.Lambda, state: State) -> AbstractValue:
        inner = State(env=import_only_env(state.env))
        for arg in self._arg_names(node.args):
            inner.bind(arg, UNKNOWN)
        self._eval(node.body, inner)
        return UNKNOWN

    def _expr_ListComp(self, node: ast.ListComp, state: State) -> AbstractValue:
        return self._comprehension(node.generators, [node.elt], state, sequence=True)

    def _expr_SetComp(self, node: ast.SetComp, state: State) -> AbstractValue:
        return self._comprehension(node.generators, [node.elt], state, sequence=False)

    def _expr_GeneratorExp(self, node: ast.GeneratorExp, state: State) -> AbstractValue:
        return self._comprehension(node.generators, [node.elt], state, sequence=True)

    def _expr_DictComp(self, node: ast.DictComp, state: State) -> AbstractValue:
        return self._comprehension(node.generators, [node.key, node.value], state, sequence=False)

    def _comprehension(
        self,
        generators: list[ast.comprehension],
        elements: list[ast.expr],
        state: State,
        *,
        sequence: bool,
    ) -> AbstractValue:
        for generator in generators:
            iter_value = self._eval(generator.iter, state)
            self._assign(generator.target, self._element_of(iter_value), state)
            for condition in generator.ifs:
                self._eval(condition, state)
        for element in elements:
            self._eval(element, state)
        return Sequence(None, local=True) if sequence else UNKNOWN

    def _expr_Subscript(self, node: ast.Subscript, state: State) -> AbstractValue:
        container = self._eval(node.value, state)
        index = self._eval(node.slice, state)
        return self._index(container, index, state)

    def _index(self, container: AbstractValue, index: AbstractValue, state: State) -> AbstractValue:
        if isinstance(container, Sequence):
            if container.elements is None:
                return UNKNOWN
            if isinstance(index, ConstInt) and -len(container.elements) <= index.value < len(
                container.elements
            ):
                return container.elements[index.value]
            return self._element_of(container)

        results = [self._index_object(option, state) for option in iter_options(container)]
        merged = results[0]
        for result in results[1:]:
            merged = join(merged, result)
        return merged

    def _index_object(self, value: AbstractValue, state: State) -> AbstractValue:
        facts = state.facts(value)
        if facts is None:
            return UNKNOWN
        if facts.kind is ObjectKind.PRIMITIVE_RESULT_V2:
            kind = (
                ObjectKind.SAMPLER_PUB_RESULT_V2
                if facts.provenance is Provenance.SAMPLER
                else ObjectKind.PUB_RESULT_V2
            )
            return state.allocate(
                ObjectFacts(
                    kind=kind,
                    provenance=facts.provenance,
                    registers=facts.registers,
                    escape=facts.escape,
                )
            )
        return UNKNOWN

    def _expr_Attribute(self, node: ast.Attribute, state: State) -> AbstractValue:
        receiver = self._eval(node.value, state)

        if isinstance(receiver, ImportedSymbol):
            return ImportedSymbol(model.canonical(f"{receiver.qualified_name}.{node.attr}"))

        facts = state.facts(receiver)
        self._emit_attribute(node, receiver, facts, state)
        return self._attribute_value(receiver, facts, node.attr, state)

    def _attribute_value(
        self,
        receiver: AbstractValue,
        facts: ObjectFacts | None,
        attribute: str,
        state: State,
    ) -> AbstractValue:
        del receiver
        if facts is None:
            return UNKNOWN

        if facts.kind in PUB_RESULT_KINDS and attribute == "data":
            return state.allocate(
                ObjectFacts(
                    kind=ObjectKind.DATA_BIN,
                    provenance=facts.provenance,
                    registers=facts.registers,
                    escape=facts.escape,
                )
            )

        if facts.kind is ObjectKind.DATA_BIN:
            # DataBin field types are primitive specific. Only a Sampler field
            # whose name is a proven classical register is a BitArray; anything
            # else stays unknown so no rule can fire on it.
            if (
                facts.provenance is Provenance.SAMPLER
                and facts.registers is not None
                and attribute in facts.registers
            ):
                return state.allocate(ObjectFacts(kind=ObjectKind.BIT_ARRAY))
            return UNKNOWN

        return UNKNOWN

    def _emit_attribute(
        self,
        node: ast.Attribute,
        receiver: AbstractValue,
        facts: ObjectFacts | None,
        state: State,
    ) -> None:
        if isinstance(node.ctx, ast.Store | ast.Del):
            return
        event = AttributeEvent(
            node=node,
            attribute=node.attr,
            receiver=receiver,
            receiver_facts=facts,
            state=state,
        )
        for rule in self.ruleset.for_hook("on_attribute"):
            rule.on_attribute(event, self.ctx)

    # Calls --------------------------------------------------------------

    def _expr_Call(self, node: ast.Call, state: State) -> AbstractValue:
        args: list[AbstractValue] = []
        complete = True
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                inner = self._eval(arg.value, state)
                if isinstance(inner, Sequence) and inner.elements is not None:
                    args.extend(inner.elements)
                else:
                    complete = False
                continue
            args.append(self._eval(arg, state))

        kwargs: dict[str, AbstractValue] = {}
        keyword_nodes: dict[str, ast.expr] = {}
        for keyword in node.keywords:
            value = self._eval(keyword.value, state)
            if keyword.arg is None:
                complete = False
                continue
            kwargs[keyword.arg] = value
            keyword_nodes[keyword.arg] = keyword.value

        func = node.func

        if isinstance(func, ast.Name):
            if func.id == BARRIER_NAME:
                self._barrier(state)
                return UNKNOWN
            if func.id == UNKNOWN_NAME:
                return UNKNOWN

        magic = _ipython_magic(node)
        if magic is not None:
            method, name = magic
            if method == "run_cell_magic" or name in NAMESPACE_MUTATING_MAGICS:
                self._barrier(state)
            return UNKNOWN

        # The receiver is evaluated exactly once. Evaluating it twice would run
        # the side effects of an expression like `build().measure_all()` twice.
        callee: AbstractValue = UNKNOWN
        receiver: AbstractValue | None = None
        if isinstance(func, ast.Name):
            callee = state.lookup(func.id)
        elif isinstance(func, ast.Attribute):
            base = self._eval(func.value, state)
            if isinstance(base, ImportedSymbol):
                callee = ImportedSymbol(model.canonical(f"{base.qualified_name}.{func.attr}"))
            else:
                receiver = base
        else:
            callee = self._eval(func, state)

        if isinstance(callee, ImportedSymbol):
            return self._call_symbol(
                node, callee, tuple(args), kwargs, keyword_nodes, complete, state
            )

        if receiver is not None and isinstance(func, ast.Attribute):
            return self._call_method(
                node, func, receiver, func.attr, tuple(args), kwargs, complete, state
            )

        if isinstance(func, ast.Name):
            if func.id in self.local_callables:
                self._invalidate_everything(state)
                for value in args:
                    state.escape_reachable(value)
                return UNKNOWN
            if func.id in PURE_BUILTINS and isinstance(state.lookup(func.id), Unbound):
                return UNKNOWN

        for value in [*args, *kwargs.values()]:
            state.escape_reachable(value)
        return UNKNOWN

    def _call_symbol(
        self,
        node: ast.Call,
        callee: ImportedSymbol,
        args: tuple[AbstractValue, ...],
        kwargs: dict[str, AbstractValue],
        keyword_nodes: dict[str, ast.expr],
        complete: bool,
        state: State,
    ) -> AbstractValue:
        name = callee.qualified_name
        event = CallEvent(
            node=node,
            callee=callee,
            qualified_name=name,
            args=args,
            kwargs=kwargs,
            keyword_nodes=keyword_nodes,
            state=state,
        )
        for rule in self.ruleset.for_hook("on_call"):
            rule.on_call(event, self.ctx)

        spec = model.constructor_for(name)
        if spec is not None:
            return state.allocate(
                ObjectFacts(
                    kind=spec.kind,
                    measurement=spec.measurement,
                    control_flow=spec.control_flow,
                    provenance=spec.provenance,
                    registers=self._initial_registers(name, args, kwargs, complete),
                    origin=name,
                )
            )

        if name in model.CIRCUIT_PRESERVING_FUNCTIONS and args:
            return self._derive_circuit(args[0], state)

        if name in model.MEASURING_OPERATIONS or name in model.NON_MEASURING_OPERATIONS:
            # A constructed operation instance, so `qc.append(XGate(), [0])`
            # keeps its facts instead of falling back to unknown.
            return state.allocate(ObjectFacts(kind=ObjectKind.OPAQUE, origin=name))

        for value in [*args, *kwargs.values()]:
            state.escape_reachable(value)
        return UNKNOWN

    @staticmethod
    def _initial_registers(
        name: str,
        args: tuple[AbstractValue, ...],
        kwargs: dict[str, AbstractValue],
        complete: bool,
    ) -> frozenset[str] | None:
        """Classical registers a freshly built circuit starts with.

        ``QuantumCircuit(2)`` has none and ``QuantumCircuit(2, 2)`` has one named
        ``c``, both verified against Qiskit. Anything built from register objects
        is left unknown.
        """
        if name != model.QISKIT_CIRCUIT or not complete or kwargs:
            return None
        if not args:
            return frozenset()
        if all(isinstance(arg, ConstInt) for arg in args):
            return frozenset({"c"}) if len(args) >= 2 else frozenset()
        return None

    def _derive_circuit(self, source: AbstractValue, state: State) -> AbstractValue:
        """A new circuit that keeps the measurement facts of the one it came from."""
        facts = state.facts(source)
        if facts is None or facts.kind is not ObjectKind.CIRCUIT:
            return UNKNOWN
        return state.allocate(
            ObjectFacts(
                kind=ObjectKind.CIRCUIT,
                measurement=facts.read_measurement(),
                control_flow=facts.read_control_flow(),
                provenance=facts.provenance,
                registers=facts.registers,
            )
        )

    def _call_method(
        self,
        node: ast.Call,
        attribute_node: ast.Attribute,
        receiver: AbstractValue,
        method: str,
        args: tuple[AbstractValue, ...],
        kwargs: dict[str, AbstractValue],
        complete: bool,
        state: State,
    ) -> AbstractValue:
        facts = state.facts(receiver)
        event = MethodCallEvent(
            node=node,
            attribute_node=attribute_node,
            method=method,
            receiver=receiver,
            receiver_facts=facts,
            args=args,
            kwargs=kwargs,
            state=state,
            result_discarded=node is self._discarded_call,
        )
        for rule in self.ruleset.for_hook("on_method_call"):
            rule.on_method_call(event, self.ctx)

        if isinstance(receiver, Sequence):
            return self._container_method(receiver, method, args, node, state)

        if facts is None:
            for value in [*args, *kwargs.values()]:
                state.escape_reachable(value)
            return UNKNOWN

        handled = self._apply_effect(node, receiver, facts, method, args, kwargs, complete, state)
        if handled is not None:
            return handled

        # Unmodelled method on a tracked object: its own facts die, and anything
        # handed to it may be retained by code we cannot see.
        state.invalidate_reachable(receiver)
        for value in [*args, *kwargs.values()]:
            state.escape_reachable(value)
        return UNKNOWN

    def _container_method(
        self,
        container: Sequence,
        method: str,
        args: tuple[AbstractValue, ...],
        node: ast.Call,
        state: State,
    ) -> AbstractValue:
        """append and extend on a local list keep their contents trackable."""
        del node
        if not container.local or container.elements is None:
            for value in args:
                state.escape_reachable(value)
            return UNKNOWN

        if method == "append" and len(args) == 1:
            self._rebind_sequence(container, (*container.elements, args[0]), state)
            return NONE
        if method == "extend" and len(args) == 1 and isinstance(args[0], Sequence):
            other = args[0]
            if other.elements is not None:
                self._rebind_sequence(container, container.elements + other.elements, state)
                return NONE
        if method in ("clear", "pop", "remove", "insert", "sort", "reverse"):
            self._rebind_sequence(container, None, state)
            return UNKNOWN

        for value in args:
            state.escape_reachable(value)
        return UNKNOWN

    @staticmethod
    def _rebind_sequence(
        container: Sequence, elements: tuple[AbstractValue, ...] | None, state: State
    ) -> None:
        """Rebind every name holding this container.

        Matching is by token, so two lists that merely happen to hold equal
        contents are not confused for one another. A container whose token was
        lost in a join is left alone, which loses a later element rather than
        inventing one.
        """
        if container.token is None:
            return
        updated = Sequence(
            elements,
            local=container.local,
            mutable=container.mutable,
            token=container.token,
        )
        for name, value in list(state.env.items()):
            if isinstance(value, Sequence) and value.token == container.token:
                state.bind(name, updated)

    def _apply_effect(
        self,
        node: ast.Call,
        receiver: AbstractValue,
        facts: ObjectFacts,
        method: str,
        args: tuple[AbstractValue, ...],
        kwargs: dict[str, AbstractValue],
        complete: bool,
        state: State,
    ) -> AbstractValue | None:
        """Modelled method effects. Returns None when the method is unmodelled."""
        kind = facts.kind

        if kind is ObjectKind.CIRCUIT:
            return self._circuit_method(receiver, facts, method, args, kwargs, complete, state)

        if model.is_primitive_kind(kind) and method == "run":
            return self._primitive_run(node, facts, args, state)

        if kind is ObjectKind.PRIMITIVE_JOB_V2 and method in ("result", "block_until_ready"):
            return state.allocate(
                ObjectFacts(
                    kind=ObjectKind.PRIMITIVE_RESULT_V2,
                    provenance=facts.provenance,
                    registers=facts.registers,
                )
            )

        if kind is ObjectKind.SAMPLER_PUB_RESULT_V2 and method == "join_data":
            # Documented return type is BitArray or ndarray, so keep both.
            return Union(
                frozenset(
                    {
                        state.allocate(ObjectFacts(kind=ObjectKind.BIT_ARRAY)),
                        state.allocate(ObjectFacts(kind=ObjectKind.NDARRAY)),
                    }
                )
            )

        if kind is ObjectKind.LEGACY_BACKEND and method == "run":
            return state.allocate(
                ObjectFacts(kind=ObjectKind.LEGACY_JOB, provenance=Provenance.LEGACY)
            )

        if kind is ObjectKind.LEGACY_JOB and method == "result":
            return state.allocate(
                ObjectFacts(kind=ObjectKind.LEGACY_RESULT, provenance=Provenance.LEGACY)
            )

        if kind is ObjectKind.RUNTIME_SERVICE and method in ("backend", "least_busy"):
            return state.allocate(
                ObjectFacts(kind=ObjectKind.LEGACY_BACKEND, provenance=Provenance.LEGACY)
            )

        is_pass_manager = (
            kind is ObjectKind.OPAQUE and facts.origin == model.GENERATE_PRESET_PASS_MANAGER
        )
        if is_pass_manager and method == "run" and args:
            return self._derive_from_pubs(args[0], state)

        return None

    def _derive_from_pubs(self, value: AbstractValue, state: State) -> AbstractValue:
        """A pass manager returns one circuit per circuit it was given."""
        if isinstance(value, Sequence) and value.elements is not None:
            derived = tuple(self._derive_circuit(element, state) for element in value.elements)
            return Sequence(derived, local=True)
        return self._derive_circuit(value, state)

    def _circuit_method(
        self,
        receiver: AbstractValue,
        facts: ObjectFacts,
        method: str,
        args: tuple[AbstractValue, ...],
        kwargs: dict[str, AbstractValue],
        complete: bool,
        state: State,
    ) -> AbstractValue | None:
        ref = receiver if isinstance(receiver, ObjectRef) else None
        inplace = kwargs.get("inplace")
        wants_copy = isinstance(inplace, ConstBool) and inplace.value is False

        if method in model.CIRCUIT_READ_METHODS:
            return UNKNOWN

        if method == "measure":
            self._update(ref, state, measurement=TriState.DEFINITELY_PRESENT)
            return UNKNOWN

        if method in ("measure_all", "measure_active"):
            registers = self._with_register(facts.registers, model.MEASURE_ALL_REGISTER)
            if wants_copy:
                return state.allocate(
                    ObjectFacts(
                        kind=ObjectKind.CIRCUIT,
                        measurement=TriState.DEFINITELY_PRESENT,
                        control_flow=facts.read_control_flow(),
                        registers=registers,
                    )
                )
            self._update(
                ref,
                state,
                measurement=TriState.DEFINITELY_PRESENT,
                registers=registers,
            )
            return NONE

        if method == "remove_final_measurements":
            if wants_copy:
                return state.allocate(
                    ObjectFacts(
                        kind=ObjectKind.CIRCUIT,
                        measurement=TriState.DEFINITELY_ABSENT,
                        control_flow=facts.read_control_flow(),
                        registers=facts.registers,
                    )
                )
            self._update(ref, state, measurement=TriState.DEFINITELY_ABSENT)
            return NONE

        if method == "clear":
            self._update(
                ref,
                state,
                measurement=TriState.DEFINITELY_ABSENT,
                control_flow=TriState.DEFINITELY_ABSENT,
            )
            return NONE

        if method in model.GATE_METHODS:
            for value in args:
                state.escape_reachable(value)
            return UNKNOWN

        if method in model.CONTROL_FLOW_BUILDERS:
            self._update(ref, state, control_flow=TriState.DEFINITELY_PRESENT)
            return UNKNOWN

        if method == "append":
            return self._circuit_append(ref, args, complete, state)

        if method in model.CIRCUIT_DERIVING_METHODS:
            measurement = (
                TriState.DEFINITELY_ABSENT
                if method == "copy_empty_like"
                else facts.read_measurement()
            )
            control_flow = (
                TriState.DEFINITELY_ABSENT
                if method == "copy_empty_like"
                else facts.read_control_flow()
            )
            return state.allocate(
                ObjectFacts(
                    kind=ObjectKind.CIRCUIT,
                    measurement=measurement,
                    control_flow=control_flow,
                    registers=facts.registers,
                )
            )

        if method in ("compose", "tensor"):
            other = state.facts(args[0]) if args else None
            other_measurement = other.read_measurement() if other is not None else TriState.UNKNOWN
            combined = self._combine_measurement(facts.read_measurement(), other_measurement)
            if wants_copy or (method == "compose" and inplace is None):
                return state.allocate(
                    ObjectFacts(
                        kind=ObjectKind.CIRCUIT,
                        measurement=combined,
                        control_flow=TriState.UNKNOWN,
                        registers=None,
                    )
                )
            self._update(
                ref,
                state,
                measurement=combined,
                control_flow=TriState.UNKNOWN,
                registers=None,
            )
            return NONE

        return None

    @staticmethod
    def _combine_measurement(left: TriState, right: TriState) -> TriState:
        """Composition adds instructions, so a measurement on either side lands."""
        if TriState.DEFINITELY_PRESENT in (left, right):
            return TriState.DEFINITELY_PRESENT
        if left is TriState.DEFINITELY_ABSENT and right is TriState.DEFINITELY_ABSENT:
            return TriState.DEFINITELY_ABSENT
        return TriState.UNKNOWN

    def _circuit_append(
        self,
        ref: ObjectRef | None,
        args: tuple[AbstractValue, ...],
        complete: bool,
        state: State,
    ) -> AbstractValue:
        """Keep facts only when the appended operation is a proven standard op."""
        operand = args[0] if args and complete else None
        origin: str | None = None
        if isinstance(operand, ImportedSymbol):
            origin = operand.qualified_name
        else:
            facts = state.facts(operand) if operand is not None else None
            origin = facts.origin if facts is not None else None

        if origin in model.MEASURING_OPERATIONS:
            self._update(ref, state, measurement=TriState.DEFINITELY_PRESENT)
            return UNKNOWN
        if origin in model.NON_MEASURING_OPERATIONS:
            return UNKNOWN

        self._update(ref, state, measurement=TriState.UNKNOWN, control_flow=TriState.UNKNOWN)
        for value in args:
            state.escape_reachable(value)
        return UNKNOWN

    @staticmethod
    def _with_register(registers: frozenset[str] | None, name: str) -> frozenset[str] | None:
        return None if registers is None else registers | {name}

    @staticmethod
    def _update(ref: ObjectRef | None, state: State, **changes: object) -> None:
        """Apply a modelled mutation. An escaped object keeps UNKNOWN facts.

        ``ref`` is never None in practice: the caller only reaches here once
        facts were resolved, and facts exist only for an object reference. The
        guard stays so a future caller cannot silently write nothing.
        """
        if ref is None:  # pragma: no cover
            return
        current = state.store.get(ref.id)
        if current is None or current.escape is Escape.ESCAPED:
            return
        state.store.update(ref.id, **changes)

    def _primitive_run(
        self,
        node: ast.Call,
        facts: ObjectFacts,
        args: tuple[AbstractValue, ...],
        state: State,
    ) -> AbstractValue:
        """A modelled consumer: circuits reaching it do not escape."""
        pubs, complete = self._extract_pubs(args[0] if args else UNKNOWN, state)
        event = PrimitiveRunEvent(
            node=node,
            primitive_facts=facts,
            pubs=pubs,
            pubs_complete=complete,
            state=state,
        )
        for rule in self.ruleset.for_hook("on_primitive_run"):
            rule.on_primitive_run(event, self.ctx)

        registers = pubs[0].facts.registers if pubs and pubs[0].facts is not None else None
        return state.allocate(
            ObjectFacts(
                kind=ObjectKind.PRIMITIVE_JOB_V2,
                provenance=facts.provenance,
                registers=registers,
            )
        )

    def _extract_pubs(
        self, value: AbstractValue, state: State
    ) -> tuple[tuple[PubArgument, ...], bool]:
        """Pull circuits out of the pub argument.

        A pub is a circuit, or a tuple whose first element is a circuit. A pub
        list whose contents are unknown yields no pubs and a False completeness
        flag, so a rule knows it did not see everything.
        """
        if not isinstance(value, Sequence) or value.elements is None:
            return (), False

        out: list[PubArgument] = []
        complete = True
        for element in value.elements:
            circuit = element
            if isinstance(element, Sequence):
                if element.elements is None or not element.elements:
                    complete = False
                    continue
                circuit = element.elements[0]
            facts = state.facts(circuit)
            if facts is None or facts.kind is not ObjectKind.CIRCUIT:
                complete = False
                continue
            out.append(PubArgument(value=circuit, facts=facts))
        return tuple(out), complete

    # Barriers -----------------------------------------------------------

    def _barrier(self, state: State) -> None:
        """A namespace mutating magic. Every data binding and every fact is void.

        Import bindings survive. A magic could in principle rebind an imported
        name, but that is vanishingly rare, while dropping imports would silence
        every later cell in the notebook. The facts that rules actually depend on
        are invalidated either way.
        """
        for name, value in list(state.env.items()):
            if not isinstance(value, ImportedSymbol):
                state.bind(name, UNKNOWN)
        state.widen_all()

    @staticmethod
    def _invalidate_everything(state: State) -> None:
        state.widen_all()


def _is_raises_context(expr: ast.expr) -> bool:
    """Is this `assertRaises(...)`, `assertRaisesRegex(...)` or `pytest.raises(...)`?

    A statement inside one of those is written to raise, so throwing its result
    away is deliberate and reporting a no-op there would be wrong.
    """
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name.startswith("assertRaises") or name == "raises"


def _ipython_magic(node: ast.Call) -> tuple[str, str] | None:
    """Detect ``get_ipython().run_line_magic('name', ...)`` and its siblings.

    nbconvert writes this form into exported notebooks, and IPython's own cell
    transformer produces it, so it has to be understood rather than treated as
    an ordinary unknown call. Returns the IPython method and the magic name.
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr
    if method not in ("run_line_magic", "run_cell_magic", "system", "getoutput"):
        return None
    base = func.value
    if not (
        isinstance(base, ast.Call)
        and isinstance(base.func, ast.Name)
        and base.func.id == "get_ipython"
    ):
        return None
    name = ""
    if node.args and isinstance(node.args[0], ast.Constant):
        raw = node.args[0].value
        if isinstance(raw, str):
            name = raw.strip().lstrip("%").lower()
    return method, name


__all__ = ["Analyzer", "is_definite"]
