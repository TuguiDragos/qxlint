"""Statement handlers, exercised through the rules they feed.

QXL103 fires only on a circuit proven to have no measurement on any path, so it
is a readout of what the analyser concluded about a statement. QXL104 fires on a
circuit result thrown away, which reads out the blocks where a discard is
deliberate.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"
RUN = "StatevectorSampler().run([qc])\n"


def fires(body: str) -> bool:
    return "QXL103" in codes(lint(HEADER + body))


# Statements with no handler of their own ---------------------------------


def test_an_assert_evaluates_its_expression() -> None:
    assert not fires(f"qc = QuantumCircuit(1)\nassert helper(qc)\n{RUN}")


def test_an_assert_that_cannot_reach_the_circuit_keeps_the_facts() -> None:
    assert fires(f"qc = QuantumCircuit(1)\nassert qc is not None\n{RUN}")


# Imports ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("importer", "expected"),
    [
        ("from qiskit import QuantumCircuit", ["QXL103"]),
        ("from . import QuantumCircuit", []),
        ("from .local import Circuit as QuantumCircuit", []),
    ],
)
def test_only_an_absolute_import_identifies_the_circuit_class(
    importer: str, expected: list[str]
) -> None:
    source = (
        f"from qiskit.primitives import StatevectorSampler\n{importer}\nqc = QuantumCircuit(1)\n"
        f"{RUN}"
    )
    assert codes(lint(source)) == expected


# Assignment forms ---------------------------------------------------------


def test_an_annotated_assignment_binds_the_new_circuit() -> None:
    assert fires(f"qc: QuantumCircuit = QuantumCircuit(1)\n{RUN}")


def test_an_annotated_assignment_from_an_unknown_value_replaces_the_circuit() -> None:
    assert not fires(f"qc = QuantumCircuit(1)\nqc: QuantumCircuit = load()\n{RUN}")


def test_a_bare_annotation_leaves_the_existing_binding_alone() -> None:
    assert fires(f"qc = QuantumCircuit(1)\nqc: QuantumCircuit\n{RUN}")


def test_adding_two_local_lists_keeps_the_circuits_visible() -> None:
    body = (
        "qc = QuantumCircuit(1)\n"
        "pubs = [qc]\n"
        "pubs += [QuantumCircuit(2)]\n"
        "StatevectorSampler().run(pubs)\n"
    )
    assert fires(body)


@pytest.mark.parametrize("statement", ["pubs += more", "pubs *= 2"])
def test_an_augmented_assignment_the_analyser_cannot_follow_drops_the_list(statement: str) -> None:
    body = f"qc = QuantumCircuit(1)\npubs = [qc]\n{statement}\nStatevectorSampler().run(pubs)\n"
    assert not fires(body)


@pytest.mark.parametrize(("addition", "expected"), [("[qc]", False), ("[1]", True)])
def test_an_augmented_assignment_to_an_attribute_escapes_what_it_adds(
    addition: str, expected: bool
) -> None:
    assert fires(f"qc = QuantumCircuit(1)\nholder.items += {addition}\n{RUN}") is expected


def test_deleting_a_name_unbinds_it() -> None:
    assert not fires(f"qc = QuantumCircuit(1)\ndel qc\n{RUN}")


def test_deleting_one_name_leaves_the_object_reachable_from_another() -> None:
    body = "qc = QuantumCircuit(1)\npubs = [qc]\ndel qc\nStatevectorSampler().run(pubs)\n"
    assert fires(body)


def test_deleting_a_subscript_is_not_a_mutation_of_the_circuit() -> None:
    assert fires(f'qc = QuantumCircuit(1)\ndel cache["qc"]\n{RUN}')


# Jumps --------------------------------------------------------------------


@pytest.mark.parametrize(("tail", "expected"), [("raise RuntimeError", True), ("pass", False)])
def test_a_raise_takes_its_branch_out_of_the_join(tail: str, expected: bool) -> None:
    body = f"qc = QuantumCircuit(1)\nif cond:\n    qc.measure_all()\n    {tail}\n{RUN}"
    assert fires(body) is expected


@pytest.mark.parametrize(
    ("jump", "expected"), [("break", True), ("continue", True), ("pass", False)]
)
def test_a_loop_body_stops_at_a_jump(jump: str, expected: bool) -> None:
    body = f"qc = QuantumCircuit(1)\nfor item in items:\n    {jump}\n    qc.measure_all()\n{RUN}"
    assert fires(body) is expected


# One problem is reported once -------------------------------------------
#
# A loop body is walked twice to reach a fixed point and rules emit on every
# walk, so a finding inside two nested loops used to arrive four times, with the
# same file, line, column and message. It reached SARIF that way too, with
# identical fingerprints.


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_a_finding_inside_nested_loops_is_reported_once(depth: int) -> None:
    body = "qc = QuantumCircuit(2)\nqc.measure_all()\n"
    body += "".join("    " * i + f"for i{i} in items:\n" for i in range(depth))
    body += "    " * depth + "c = StatevectorSampler().run([qc]).result().get_counts()\n"
    assert codes(lint(HEADER + body)) == ["QXL101"]


def test_a_finding_inside_a_while_loop_is_reported_once() -> None:
    body = (
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "while cond:\n"
        "    c = StatevectorSampler().run([qc]).result().get_counts()\n"
    )
    assert codes(lint(HEADER + body)) == ["QXL101"]


def test_a_first_iteration_only_finding_survives_deduplication() -> None:
    # The circuit really has no measurement on the first iteration, and only the
    # first walk of the body can see that. Emitting on the last walk only would
    # drop this, which is why repeats are collapsed instead.
    body = (
        "sampler = StatevectorSampler()\n"
        "qc = QuantumCircuit(2)\n"
        "for item in items:\n"
        "    sampler.run([qc])\n"
        "    qc.measure_all()\n"
    )
    assert codes(lint(HEADER + body)) == ["QXL103"]


def test_two_findings_on_one_line_are_not_collapsed_into_one() -> None:
    body = (
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "for item in items:\n"
        "    c = StatevectorSampler().run([qc]).result().get_counts()\n"
    )
    findings = lint(HEADER + body)
    assert codes(findings) == ["QXL101", "QXL103"]
    assert len({(f.rule, f.location.line) for f in findings}) == 2


def test_a_nonlocal_declaration_makes_the_captured_name_known() -> None:
    # `print` is no longer the builtin, so the circuit handed to it escapes.
    source = (
        HEADER + "def outer():\n"
        "    def inner():\n"
        "        nonlocal print\n"
        "        qc = QuantumCircuit(1)\n"
        "        print(qc)\n"
        "        StatevectorSampler().run([qc])\n"
        "    print = logger.info\n"
    )
    assert codes(lint(source)) == []


def test_a_nonlocal_name_can_still_be_rebound_to_a_new_circuit() -> None:
    source = (
        HEADER + "def outer():\n"
        "    def inner():\n"
        "        nonlocal qc\n"
        "        qc = QuantumCircuit(1)\n"
        "        StatevectorSampler().run([qc])\n"
        "    qc = None\n"
    )
    assert codes(lint(source)) == ["QXL103"]


# Async statements ---------------------------------------------------------


@pytest.mark.parametrize(("call", "expected"), [("qc.measure_all()", False), ("qc.h(0)", True)])
def test_an_async_for_body_joins_with_the_zero_iteration_path(call: str, expected: bool) -> None:
    source = (
        HEADER + "async def main():\n"
        "    qc = QuantumCircuit(1)\n"
        "    async for item in stream:\n"
        f"        {call}\n"
        "    StatevectorSampler().run([qc])\n"
    )
    assert ("QXL103" in codes(lint(source))) is expected


@pytest.mark.parametrize(("call", "expected"), [("qc.measure_all()", False), ("qc.h(0)", True)])
def test_an_async_with_body_runs_unconditionally(call: str, expected: bool) -> None:
    source = (
        HEADER + "async def main():\n"
        "    qc = QuantumCircuit(1)\n"
        "    async with Session(backend) as session:\n"
        f"        {call}\n"
        "    StatevectorSampler().run([qc])\n"
    )
    assert ("QXL103" in codes(lint(source))) is expected


@pytest.mark.parametrize(("item", "expected"), [("session", True), ("session as qc", False)])
def test_a_with_item_binds_its_optional_variable(item: str, expected: bool) -> None:
    assert fires(f"qc = QuantumCircuit(1)\nwith {item}:\n    pass\n{RUN}") is expected


# Try ----------------------------------------------------------------------


@pytest.mark.parametrize(("call", "expected"), [("qc.measure_all()", False), ("qc.h(0)", True)])
def test_an_except_star_group_is_analysed_like_a_plain_handler(call: str, expected: bool) -> None:
    body = f"qc = QuantumCircuit(1)\ntry:\n    {call}\nexcept* ValueError:\n    pass\n{RUN}"
    assert fires(body) is expected


@pytest.mark.parametrize(
    ("clause", "expected"), [("except Exception:", True), ("except Exception as qc:", False)]
)
def test_a_handler_binding_replaces_the_name_it_captures(clause: str, expected: bool) -> None:
    # The handler deliberately shadows the circuit: the name must come out of
    # the join as unknown rather than as the circuit it held before.
    body = f"qc = QuantumCircuit(1)\ntry:\n    work()\n{clause}\n    pass\n{RUN}"
    assert fires(body) is expected


@pytest.mark.parametrize(
    ("body_call", "else_call", "expected"),
    [("qc.compose(other)", "pass", []), ("pass", "qc.compose(other)", ["QXL104"])],
)
def test_an_else_block_is_not_guarded_by_the_handler(
    body_call: str, else_call: str, expected: list[str]
) -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(2)\n"
        "other = QuantumCircuit(2)\n"
        "try:\n"
        f"    {body_call}\n"
        "except TypeError:\n"
        "    pass\n"
        "else:\n"
        f"    {else_call}\n"
    )
    assert codes(lint(source)) == expected


# Match --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [("[1]", True), ("[qc]", False), ("[*qc]", False), ("{**qc}", False)],
)
def test_a_capture_pattern_rebinds_the_name_it_captures(pattern: str, expected: bool) -> None:
    body = f"qc = QuantumCircuit(1)\nmatch value:\n    case {pattern}:\n        pass\n{RUN}"
    assert fires(body) is expected


@pytest.mark.parametrize(("guard", "expected"), [("", True), (" if helper(qc)", False)])
def test_a_case_guard_is_evaluated(guard: str, expected: bool) -> None:
    body = f"qc = QuantumCircuit(1)\nmatch value:\n    case 1{guard}:\n        pass\n{RUN}"
    assert fires(body) is expected


# Definitions --------------------------------------------------------------


@pytest.mark.parametrize(("decorator", "expected"), [("@memoize", True), ("@memoize(qc)", False)])
def test_a_function_decorator_expression_is_evaluated(decorator: str, expected: bool) -> None:
    assert fires(f"qc = QuantumCircuit(1)\n{decorator}\ndef build():\n    pass\n{RUN}") is expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("class Job:", True),
        ("class Job(Base):", True),
        ("@attach(qc)\nclass Job:", False),
        ("class Job(wrapper(qc)):", False),
    ],
)
def test_a_class_definition_evaluates_its_decorators_and_bases(header: str, expected: bool) -> None:
    assert fires(f"qc = QuantumCircuit(1)\n{header}\n    pass\n{RUN}") is expected


@pytest.mark.parametrize(
    ("signature", "expected"),
    [("", True), ("print", False), ("*print", False), ("**print", False)],
)
def test_a_parameter_shadowing_a_builtin_stops_the_pure_builtin_shortcut(
    signature: str, expected: bool
) -> None:
    source = (
        HEADER + f"def f({signature}):\n"
        "    qc = QuantumCircuit(1)\n"
        "    print(qc)\n"
        "    StatevectorSampler().run([qc])\n"
    )
    assert ("QXL103" in codes(lint(source))) is expected
