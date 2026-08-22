"""Engine B against real Qiskit objects.

Skipped when Qiskit is absent, which is the point: Engine A must not need it.
"""

from __future__ import annotations

import pytest

import qxlint
from qxlint.diagnostics import CircuitLocation

pytestmark = pytest.mark.requires_qiskit

qiskit = pytest.importorskip("qiskit")


@pytest.fixture
def target() -> object:
    runtime = pytest.importorskip("qiskit_ibm_runtime")
    return runtime.fake_provider.FakeManilaV2().target


def bell() -> object:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def test_untranspiled_circuit_reports_unsupported_operations(target: object) -> None:
    findings = qxlint.check_target(bell(), target)
    assert {f.rule for f in findings} == {"QXL301"}
    assert any("'h'" in f.message for f in findings)


def test_transpiled_circuit_is_clean(target: object) -> None:
    from qiskit import transpile
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    isa = transpile(bell(), FakeManilaV2(), seed_transpiler=11)
    assert qxlint.check_target(isa, target) == []


def test_barrier_is_never_reported(target: object) -> None:
    from qiskit import QuantumCircuit, transpile
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.barrier()
    isa = transpile(qc, FakeManilaV2(), seed_transpiler=3)
    findings = qxlint.check_target(isa, target)
    assert [f for f in findings if f.context.get("operation") == "barrier"] == []


def test_circuit_wider_than_the_target(target: object) -> None:
    from qiskit import QuantumCircuit

    findings = qxlint.check_target(QuantumCircuit(99), target)
    assert len(findings) == 1
    assert "99 qubits" in findings[0].message


def test_narrower_circuit_is_allowed(target: object) -> None:
    from qiskit import QuantumCircuit

    assert qxlint.check_target(QuantumCircuit(1), target) == []


def test_control_flow_blocks_are_recursed_into(target: object) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2, 2)
    qc.measure(0, 0)
    with qc.if_test((qc.clbits[0], 1)):
        qc.cy(0, 1)

    findings = qxlint.check_target(qc, target)
    nested = [f for f in findings if len(f.location.path) > 1]
    assert nested, "expected a finding inside the control flow block"
    location = nested[0].location
    assert isinstance(location, CircuitLocation)
    assert location.path[0].block is not None
    assert location.operation == "cy"


def test_instruction_path_disambiguates_blocks(target: object) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2, 2)
    qc.measure(0, 0)
    with qc.if_test((qc.clbits[0], 1)):
        qc.cy(0, 1)
    with qc.if_test((qc.clbits[0], 1)):
        qc.cy(0, 1)

    paths = {f.location.render() for f in qxlint.check_target(qc, target)}
    assert len(paths) == len(qxlint.check_target(qc, target))


def test_preview_self_inverse_pair() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(1)
    qc.h(0)
    qc.h(0)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"]
    assert len(findings) == 1


def test_self_inverse_respects_qubit_order() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.cx(0, 1)
    qc.cx(1, 0)
    assert [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"] == []


@pytest.mark.parametrize("gate", ["s", "t", "sx", "iswap", "dcx"])
def test_gates_that_are_not_self_inverse_are_never_paired(gate: str) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    method = getattr(qc, gate)
    args = (0, 1) if gate in {"iswap", "dcx"} else (0,)
    method(*args)
    method(*args)
    assert [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"] == []


@pytest.mark.parametrize("gate", ["x", "y", "z", "h", "cx", "cz", "swap", "ecr"])
def test_verified_self_inverse_gates_are_paired(gate: str) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    method = getattr(qc, gate)
    args = (0, 1) if gate in {"cx", "cz", "swap", "ecr"} else (0,)
    method(*args)
    method(*args)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"]
    assert len(findings) == 1


def test_intervening_gate_breaks_the_pair() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.x(1)
    qc.h(0)
    assert [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"] == []


@pytest.mark.parametrize(("count", "expected"), [(2, 1), (3, 1), (4, 2), (5, 2), (6, 3)])
def test_a_run_of_the_same_gate_reports_pairs_that_do_not_overlap(
    count: int, expected: int
) -> None:
    # Three h in a row contain one cancellation, not two. Each instruction can
    # only cancel against one neighbour, so a reported pair consumes both.
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(1)
    for _ in range(count):
        qc.h(0)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"]
    assert len(findings) == expected


def test_unused_qubit_preview() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL303"]
    assert len(findings) == 1
    assert findings[0].location.qubits == (2,)


def test_a_whole_circuit_finding_renders_without_an_instruction_index() -> None:
    # It used to render as circuit-1[-1], inventing an instruction the reader
    # would then look for.
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL303"]
    assert len(findings) == 1
    rendered = findings[0].render_text()
    assert "[-1]" not in rendered
    assert rendered.startswith(f"{qc.name}: QXL303")
    assert findings[0].location.path == ()


def test_a_circuit_wider_than_the_target_renders_without_an_instruction_index() -> None:
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import HGate
    from qiskit.transpiler import Target

    narrow = Target(num_qubits=1)
    narrow.add_instruction(HGate(), {(0,): None})
    qc = QuantumCircuit(3)
    qc.h(0)
    findings = qxlint.check_target(qc, narrow)
    assert len(findings) == 1
    assert "[-1]" not in findings[0].render_text()
    assert findings[0].location.path == ()


def test_check_circuit_without_target_or_preview_is_empty() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3)
    qc.h(0)
    qc.h(0)
    assert qxlint.check_circuit(qc) == []


def test_engine_b_findings_have_no_file_location(target: object) -> None:
    for finding in qxlint.check_target(bell(), target):
        assert isinstance(finding.location, CircuitLocation)
        assert finding.engine == "B"


# Control flow operations ------------------------------------------------
#
# qiskit-ibm-runtime checks every instruction against the target before it
# recurses, the control flow operation included. Skipping it reported a circuit
# as compatible that the service rejects.


def toy_target(*, control_flow: bool) -> object:
    from qiskit.circuit import Measure
    from qiskit.circuit.controlflow import IfElseOp
    from qiskit.circuit.library import CXGate, HGate, XGate
    from qiskit.transpiler import Target

    target = Target(num_qubits=2)
    target.add_instruction(HGate(), {(0,): None, (1,): None})
    target.add_instruction(XGate(), {(0,): None, (1,): None})
    target.add_instruction(CXGate(), {(0, 1): None})
    target.add_instruction(Measure(), {(0,): None, (1,): None})
    if control_flow:
        target.add_instruction(IfElseOp, name="if_else")
    return target


def conditional_x() -> object:
    """One if_else whose body holds nothing the target could object to."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.controlflow import IfElseOp

    qc = QuantumCircuit(2, 1)
    body = QuantumCircuit(1, 1)
    body.x(0)
    qc.append(IfElseOp((qc.clbits[0], 1), body), [0], [0])
    return qc


def nested_conditionals(depth: int) -> object:
    from qiskit import QuantumCircuit
    from qiskit.circuit.controlflow import IfElseOp

    block = QuantumCircuit(1, 1)
    block.x(0)
    for _ in range(depth):
        outer = QuantumCircuit(1, 1)
        outer.append(IfElseOp((outer.clbits[0], 1), block), [0], [0])
        block = outer
    return block


def test_a_control_flow_operation_the_target_lacks_is_reported() -> None:
    findings = qxlint.check_target(conditional_x(), toy_target(control_flow=False))
    assert [f.context.get("operation") for f in findings] == ["if_else"]


def test_a_control_flow_operation_the_target_supports_is_not_reported() -> None:
    assert qxlint.check_target(conditional_x(), toy_target(control_flow=True)) == []


@pytest.mark.parametrize("control_flow", [False, True])
def test_the_verdict_matches_qiskit_ibm_runtime(control_flow: bool) -> None:
    # The rule claims to mirror is_isa_circuit. This is that claim as a test.
    runtime = pytest.importorskip("qiskit_ibm_runtime.utils.utils")
    target = toy_target(control_flow=control_flow)
    circuit = conditional_x()
    rejected_by_upstream = bool(runtime.is_isa_circuit(circuit, target))
    assert bool(qxlint.check_target(circuit, target)) is rejected_by_upstream


# Analysis depth ---------------------------------------------------------


def test_nesting_past_the_walk_depth_is_reported_as_incomplete() -> None:
    findings = qxlint.check_target(nested_conditionals(13), toy_target(control_flow=True))
    assert [f.rule for f in findings] == ["QXL300"]
    assert "incomplete" in findings[0].message


def test_a_circuit_within_the_walk_depth_reports_nothing_incomplete() -> None:
    findings = qxlint.check_target(nested_conditionals(5), toy_target(control_flow=True))
    assert [f.rule for f in findings] == []


def test_preview_checks_also_report_an_incomplete_analysis() -> None:
    findings = qxlint.check_circuit(nested_conditionals(13), preview=True)
    assert "QXL300" in {f.rule for f in findings}


# Silencing a circuit finding -------------------------------------------


def test_ignore_drops_a_circuit_finding() -> None:
    # A circuit finding has no source line, so `# noqa` cannot reach it and the
    # library API reads no configuration file. This argument is the only way.
    from qiskit import QuantumCircuit
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    target = FakeManilaV2().target
    assert [f.rule for f in qxlint.check_circuit(qc, target=target)] == ["QXL301"]
    assert qxlint.check_circuit(qc, target=target, ignore=["QXL301"]) == []
    assert qxlint.check_target(qc, target, ignore=["QXL301"]) == []


def test_ignore_matches_a_prefix_and_ignores_case_and_spacing() -> None:
    from qiskit import QuantumCircuit
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    target = FakeManilaV2().target
    for spelling in (["QXL3"], [" qxl301 "], ["qxl3"]):
        assert qxlint.check_circuit(qc, target=target, ignore=spelling) == []


def test_an_empty_or_absent_ignore_changes_nothing() -> None:
    from qiskit import QuantumCircuit
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    target = FakeManilaV2().target
    for spelling in (None, [], ["  "], ["QXL999"]):
        assert [f.rule for f in qxlint.check_circuit(qc, target=target, ignore=spelling)] == [
            "QXL301"
        ]


def test_qxl303_skips_a_transpiled_circuit() -> None:
    # Measured on FakeSherbrooke before this: a 2 qubit circuit transpiles to
    # 127 wide and the rule fired 125 times, one per idle physical qubit, on the
    # one circuit shape QXL301 is meaningful on.
    from qiskit import QuantumCircuit, transpile
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    backend = FakeManilaV2()
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    isa = transpile(qc, backend, optimization_level=1)
    assert isa.layout is not None
    assert qxlint.check_circuit(isa, target=backend.target, preview=True) == []


def test_qxl303_still_reports_a_hand_written_circuit() -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3)
    qc.h(0)
    assert qc.layout is None
    assert [f.rule for f in qxlint.check_circuit(qc, preview=True)] == ["QXL303", "QXL303"]
