"""Paths that do not run, and paths that leave a loop early.

Both are read out through QXL103, which fires only on a circuit proven to carry
no measurement on any path. So `fires` is True exactly when the analyser
concluded the measurement never happened, and False when it concluded it
happened or could not decide.
"""

from __future__ import annotations

import time

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"
RUN = "StatevectorSampler().run([qc])\n"
BUILD = "qc = QuantumCircuit(1)\n"


def fires(body: str) -> bool:
    return "QXL103" in codes(lint(HEADER + body))


# Short circuit ----------------------------------------------------------


def test_and_stops_at_a_constant_false_so_the_call_never_runs() -> None:
    # Python never calls measure_all here, so the circuit reaches the Sampler
    # unmeasured and the rule has to say so.
    assert fires(f"{BUILD}False and qc.measure_all()\n{RUN}")


def test_and_continues_past_a_constant_true() -> None:
    assert not fires(f"{BUILD}True and qc.measure_all()\n{RUN}")


def test_a_zero_is_falsy_so_and_stops() -> None:
    assert fires(f"{BUILD}0 and qc.measure_all()\n{RUN}")


def test_a_non_empty_string_is_truthy_so_and_continues() -> None:
    assert not fires(f'{BUILD}"go" and qc.measure_all()\n{RUN}')


def test_none_is_falsy_so_and_stops() -> None:
    assert fires(f"{BUILD}None and qc.measure_all()\n{RUN}")


def test_or_stops_at_a_truthy_constant() -> None:
    assert fires(f"{BUILD}1 or qc.measure_all()\n{RUN}")


def test_or_continues_past_a_falsy_constant() -> None:
    assert not fires(f'{BUILD}"" or qc.measure_all()\n{RUN}')


def test_an_undecidable_operand_leaves_the_effect_undecided() -> None:
    # The measurement happens on some executions only, which is neither proof
    # nor absence of proof, so the rule stays silent.
    assert not fires(f"{BUILD}flag and qc.measure_all()\n{RUN}")


def test_a_ternary_with_a_constant_true_test_runs_only_its_body() -> None:
    assert not fires(f"{BUILD}_ = qc.measure_all() if True else None\n{RUN}")


def test_a_ternary_with_a_constant_false_test_runs_only_its_else() -> None:
    assert fires(f"{BUILD}_ = qc.measure_all() if False else None\n{RUN}")


def test_a_ternary_with_an_undecidable_test_leaves_the_effect_undecided() -> None:
    assert not fires(f"{BUILD}_ = qc.measure_all() if flag else None\n{RUN}")


def test_a_comprehension_body_may_never_run() -> None:
    assert not fires(f"{BUILD}[qc.measure_all() for _ in range(n)]\n{RUN}")


def test_a_comprehension_target_does_not_leak_into_the_enclosing_scope() -> None:
    # Python scopes the target to the comprehension, so the run below still
    # sees the circuit built above and not the elements of `others`.
    assert fires(f"{BUILD}others = [1, 2]\n[qc for qc in others]\n{RUN}")


# Loops left early -------------------------------------------------------


def test_a_measurement_before_a_break_survives_the_loop() -> None:
    assert not fires(f"{BUILD}while True:\n    qc.measure_all()\n    break\n{RUN}")


def test_a_measurement_before_a_continue_survives_the_loop() -> None:
    assert not fires(f"{BUILD}for _ in range(3):\n    qc.measure_all()\n    continue\n{RUN}")


def test_a_measurement_under_a_conditional_break_survives_the_loop() -> None:
    assert not fires(
        f"{BUILD}for _ in range(3):\n    if flag:\n        qc.measure_all()\n        break\n{RUN}"
    )


def test_a_break_outside_a_loop_is_analysed_without_a_loop_to_leave() -> None:
    # ast.parse accepts this and only compile() rejects it, so the analyser can
    # reach a break with no loop on the stack.
    assert fires(f"{BUILD}{RUN}break\n")


def test_a_continue_outside_a_loop_is_analysed_without_a_loop_to_leave() -> None:
    assert fires(f"{BUILD}{RUN}continue\n")


def test_a_break_inside_a_function_does_not_escape_to_the_loop_around_it() -> None:
    # CPython rejects this break, ast.parse does not. If it reached the loop
    # frame it would merge a function scope into module state and lose the
    # circuit.
    assert fires(f"{BUILD}for _ in range(2):\n    def helper():\n        break\n{RUN}")


# Cost -------------------------------------------------------------------


def nested_loops(levels: int, innermost: str) -> str:
    lines = ["    " * level + f"for i{level} in range(2):" for level in range(levels)]
    lines.append("    " * levels + innermost)
    return "\n".join(lines) + "\n"


def test_a_loop_nested_past_the_two_pass_limit_stays_sound() -> None:
    assert fires(BUILD + nested_loops(6, "pass") + RUN)


def test_a_measurement_deep_inside_nested_loops_is_never_reported_as_absent() -> None:
    assert not fires(BUILD + nested_loops(6, "qc.measure_all()") + RUN)


def test_deeply_nested_loops_do_not_cost_exponential_time() -> None:
    # Two passes at every level walked the innermost body 2^levels times: this
    # file took seventeen seconds. The bound is loose so only the exponential
    # behaviour coming back can trip it.
    started = time.monotonic()
    lint(HEADER + BUILD + nested_loops(20, "pass") + RUN)
    assert time.monotonic() - started < 10.0
