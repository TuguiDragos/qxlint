"""QXL103: unmeasured circuit passed to a Sampler."""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"


def test_positive_plain_case() -> None:
    source = HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == ["QXL103"]


def test_positive_with_a_classical_register_but_no_measure() -> None:
    # This is the quiet one: Qiskit emits no warning and every shot reads zero.
    source = HEADER + "qc = QuantumCircuit(2, 2)\nqc.h(0)\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == ["QXL103"]


# Circuits from qiskit.circuit.library -----------------------------------
#
# Only QuantumCircuit was modelled, so every ansatz and feature map was an
# unknown object and no rule could reach it. That was 11.8% of all circuit
# construction across a 113 repository corpus.

LIBRARY_HEADER = (
    "from qiskit.circuit.library import "
    "RealAmplitudes, EfficientSU2, TwoLocal, ZFeatureMap, ZZFeatureMap, QFT\n"
    "from qiskit.circuit.library import real_amplitudes, efficient_su2, z_feature_map\n"
    "from qiskit.primitives import StatevectorSampler\n"
)


@pytest.mark.parametrize(
    "constructor",
    [
        "RealAmplitudes(2)",
        "EfficientSU2(2)",
        "TwoLocal(2)",
        "ZFeatureMap(2)",
        "ZZFeatureMap(2)",
        "QFT(3)",
        "real_amplitudes(2)",
        "efficient_su2(2)",
        "z_feature_map(2)",
    ],
)
def test_positive_on_an_unmeasured_library_circuit(constructor: str) -> None:
    source = LIBRARY_HEADER + f"qc = {constructor}\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == ["QXL103"]


def test_negative_when_a_library_circuit_is_measured() -> None:
    source = LIBRARY_HEADER + (
        "qc = RealAmplitudes(2)\nqc.measure_all()\nStatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_random_circuit_because_measure_is_an_argument() -> None:
    # random_circuit takes measure=, so whether it contains one depends on the
    # call. Only its kind is modelled, which keeps this silent either way.
    source = (
        "from qiskit.circuit.random import random_circuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = random_circuit(3, 2)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_a_local_class_with_a_library_name() -> None:
    source = (
        "from qiskit.primitives import StatevectorSampler\n"
        "class RealAmplitudes:\n"
        "    pass\n"
        "qc = RealAmplitudes()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_negative_measure_all() -> None:
    source = HEADER + "qc = QuantumCircuit(2)\nqc.measure_all()\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == []


def test_negative_explicit_measure() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2, 2)\nqc.measure(0, 0)\nStatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_negative_estimator_with_an_unmeasured_circuit_is_correct_code() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorEstimator\n"
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "StatevectorEstimator().run([(qc, obs)])\n"
    )
    assert codes(lint(source)) == []


def test_negative_when_the_circuit_came_from_elsewhere() -> None:
    source = HEADER + "qc = build_circuit()\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == []


def test_negative_when_the_pub_list_contents_are_unknown() -> None:
    source = HEADER + "StatevectorSampler().run(load_pubs())\n"
    assert codes(lint(source)) == []


def test_measure_active_counts_as_a_measurement() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nqc.measure_active()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_remove_final_measurements_brings_it_back() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\nqc.measure_all()\nqc.remove_final_measurements()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_measure_all_not_in_place_leaves_the_original_alone() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\ncopy = qc.measure_all(inplace=False)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_measure_all_not_in_place_returns_a_measured_circuit() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\ncopy = qc.measure_all(inplace=False)\n"
        "StatevectorSampler().run([copy])\n"
    )
    assert codes(lint(source)) == []


def test_clear_removes_measurements() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\nqc.measure_all()\nqc.clear()\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_transpile_preserves_the_absence() -> None:
    source = (
        "from qiskit import QuantumCircuit, transpile\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "StatevectorSampler().run([transpile(qc, backend)])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_pass_manager_run_preserves_the_measurement() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "from qiskit.transpiler import generate_preset_pass_manager\n"
        "pm = generate_preset_pass_manager(optimization_level=1, backend=backend)\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "StatevectorSampler().run(pm.run([qc]))\n"
    )
    assert codes(lint(source)) == []


def test_compose_with_a_measured_circuit_counts() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\n"
        "other = QuantumCircuit(2)\n"
        "other.measure_all()\n"
        "qc.compose(other, inplace=True)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


@pytest.mark.parametrize("gate", ["h", "x", "cx", "barrier", "reset", "delay"])
def test_gate_methods_do_not_add_a_measurement(gate: str) -> None:
    source = HEADER + f"qc = QuantumCircuit(2)\nqc.{gate}(0)\nStatevectorSampler().run([qc])\n"
    assert codes(lint(source)) == ["QXL103"]


def test_append_of_a_known_gate_keeps_the_facts() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.circuit.library import XGate\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.append(XGate(), [0])\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_append_of_measure_adds_a_measurement() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.circuit import Measure\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.append(Measure(), [0], [0])\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_append_of_an_unknown_operation_silences_the_rule() -> None:
    source = (
        HEADER + "qc = QuantumCircuit(2)\nqc.append(mystery, [0])\nStatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == []


def test_only_one_finding_per_run_call() -> None:
    source = (
        HEADER + "a = QuantumCircuit(1)\nb = QuantumCircuit(1)\nStatevectorSampler().run([a, b])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_several_unmeasured_pubs_in_one_call_report_once() -> None:
    # The finding is anchored on the run call, so a second defective pub would
    # repeat the same diagnostic at the same line and column.
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "first = QuantumCircuit(2, 2)\n"
        "second = QuantumCircuit(2, 2)\n"
        "StatevectorSampler().run([first, second])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


# A patched run is a mock, not a primitive ---------------------------------
#
# `with mock.patch.object(SamplerV2, "run")` replaces the method, so the
# circuits never reach a sampler and no result is produced. Saying the result
# carries no counts would describe something the call never does.

PATCHED = (
    "from unittest import mock\n"
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(2, 2)\n"
    "sampler = StatevectorSampler()\n"
)


def test_a_patched_run_is_not_a_primitive_call() -> None:
    source = PATCHED + (
        'with mock.patch.object(StatevectorSampler, "run") as mock_run:\n    sampler.run([qc])\n'
    )
    assert codes(lint(source)) == []


def test_a_patch_named_by_string_counts_too() -> None:
    source = PATCHED + (
        'with mock.patch("qiskit.primitives.StatevectorSampler.run"):\n    sampler.run([qc])\n'
    )
    assert codes(lint(source)) == []


def test_patching_another_method_leaves_run_alone() -> None:
    source = PATCHED + (
        'with mock.patch.object(StatevectorSampler, "something_else"):\n    sampler.run([qc])\n'
    )
    assert codes(lint(source)) == ["QXL103"]


def test_the_patch_ends_with_its_block() -> None:
    source = PATCHED + (
        'with mock.patch.object(StatevectorSampler, "run"):\n    pass\nsampler.run([qc])\n'
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_patch_context_without_a_name_changes_nothing() -> None:
    source = (
        PATCHED + "with mock.patch.object(StatevectorSampler, attribute):\n    sampler.run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_an_estimator_run_is_patched_the_same_way() -> None:
    source = (
        "from unittest import mock\n"
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorEstimator\n"
        "from qiskit.quantum_info import SparsePauliOp\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "estimator = StatevectorEstimator()\n"
        'with mock.patch.object(StatevectorEstimator, "run"):\n'
        "    estimator.run([(qc, SparsePauliOp('ZZ'))])\n"
    )
    assert codes(lint(source)) == []


def test_nested_patches_of_the_same_method_unwind_one_at_a_time() -> None:
    source = PATCHED + (
        'with mock.patch.object(StatevectorSampler, "run"):\n'
        '    with mock.patch.object(StatevectorSampler, "run"):\n'
        "        sampler.run([qc])\n"
        "    sampler.run([qc])\n"
        "sampler.run([qc])\n"
    )
    # Silent inside both blocks, reported once the outer one ends.
    assert codes(lint(source)) == ["QXL103"]


def test_a_patch_target_that_is_not_a_literal_changes_nothing() -> None:
    source = PATCHED + "with mock.patch(target):\n    sampler.run([qc])\n"
    assert codes(lint(source)) == ["QXL103"]
