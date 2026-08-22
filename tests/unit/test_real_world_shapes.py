"""Shapes real Qiskit code is written in, read from three points of view.

The unit tests elsewhere isolate one analyser behaviour each. These read whole
workflows the way they appear in a repository: an engineer's production module,
a student following a tutorial, a beginner making the mistakes the rules exist
for. A shape that only appears when several features combine belongs here.
"""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

SAMPLER = "from qiskit import QuantumCircuit\nfrom qiskit.primitives import StatevectorSampler\n"
ESTIMATOR = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorEstimator\n"
    "from qiskit.quantum_info import SparsePauliOp\n"
)


# The engineer ------------------------------------------------------------


def test_a_local_circuit_inside_a_method_is_an_ordinary_local() -> None:
    source = SAMPLER + (
        "class Runner:\n"
        "    def go(self):\n"
        "        qc = QuantumCircuit(2, 2)\n"
        "        qc.h(0)\n"
        "        StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_circuit_kept_on_the_instance_is_out_of_reach() -> None:
    # No class attribute tracking, which is a documented limit rather than a gap
    # the rules paper over.
    source = SAMPLER + (
        "class Runner:\n"
        "    def __init__(self):\n"
        "        self.circuit = QuantumCircuit(2, 2)\n"
        "    def go(self):\n"
        "        StatevectorSampler().run([self.circuit])\n"
    )
    assert codes(lint(source)) == []


def test_a_decorator_does_not_hide_the_body() -> None:
    source = SAMPLER + (
        "class Runner:\n"
        "    @staticmethod\n"
        "    def go():\n"
        "        qc = QuantumCircuit(2, 2)\n"
        "        StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_session_context_manager_is_correct_and_the_circuit_is_not() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime import Session, SamplerV2\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.h(0)\n"
        "with Session(backend=backend) as session:\n"
        "    sampler = SamplerV2(mode=session)\n"
        "    sampler.run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_batch_takes_a_backend_and_the_primitive_takes_a_mode() -> None:
    source = (
        "from qiskit_ibm_runtime import Batch, SamplerV2\n"
        "with Batch(backend=backend) as batch:\n"
        "    sampler = SamplerV2(mode=batch)\n"
    )
    assert codes(lint(source)) == []


def test_an_async_body_is_walked_like_any_other() -> None:
    source = SAMPLER + (
        "async def main():\n"
        "    qc = QuantumCircuit(2, 2)\n"
        "    qc.h(0)\n"
        "    StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_type_checking_block_does_not_disturb_the_analysis() -> None:
    source = (
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n" + SAMPLER + "if TYPE_CHECKING:\n"
        "    from qiskit.providers import Backend\n"
        "qc = QuantumCircuit(2, 2)\n"
        "StatevectorSampler().run([qc])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_match_case_body_is_walked() -> None:
    source = SAMPLER + (
        "qc = QuantumCircuit(2, 2)\n"
        "match mode:\n"
        "    case 'run':\n"
        "        StatevectorSampler().run([qc])\n"
        "    case _:\n"
        "        pass\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_walrus_inside_a_comprehension_still_builds_the_circuit() -> None:
    source = SAMPLER + (
        "sampler = StatevectorSampler()\n"
        "results = [(r := sampler.run([QuantumCircuit(2, 2)])) for _ in range(2)]\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_a_pass_manager_result_carries_the_circuit_into_the_run() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "from qiskit.transpiler import generate_preset_pass_manager\n"
        "pm = generate_preset_pass_manager(optimization_level=1, backend=backend)\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.h(0)\n"
        "StatevectorSampler().run([pm.run(qc)])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


def test_the_whole_correct_v2_workflow_is_silent() -> None:
    source = SAMPLER + (
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "qc.cx(0, 1)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc], shots=1024).result()\n"
        "counts = result[0].data.meas.get_counts()\n"
        "print(counts)\n"
    )
    assert codes(lint(source)) == []


def test_walking_the_pubs_and_reading_the_register_is_silent() -> None:
    source = SAMPLER + (
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "for pub in result:\n"
        "    print(pub.data.meas.get_counts())\n"
    )
    assert codes(lint(source)) == []


# The student -------------------------------------------------------------


def test_the_tutorial_bell_state_read_the_v1_way() -> None:
    source = SAMPLER + (
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "qc.cx(0, 1)\n"
        "qc.measure_all()\n"
        "job = StatevectorSampler().run([qc], shots=1024)\n"
        "counts = job.result().get_counts()\n"
    )
    assert codes(lint(source)) == ["QXL101"]


def test_the_defect_inside_a_plotting_call_is_still_the_defect() -> None:
    source = SAMPLER + (
        "from qiskit.visualization import plot_histogram\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "plot_histogram(result.get_counts())\n"
    )
    assert codes(lint(source)) == ["QXL101"]


@pytest.mark.parametrize(
    ("measurement", "expected"),
    [("qc.measure(0, 0)\n", []), ("", ["QXL103"])],
)
def test_a_parameter_sweep_is_judged_on_its_measurement(
    measurement: str, expected: list[str]
) -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.circuit import Parameter\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "import numpy as np\n"
        "theta = Parameter('theta')\n"
        "qc = QuantumCircuit(1, 1)\n"
        "qc.rx(theta, 0)\n" + measurement + "values = np.linspace(0, np.pi, 10)\n"
        "StatevectorSampler().run([(qc, values)])\n"
    )
    assert codes(lint(source)) == expected


def test_only_the_unmeasured_circuit_in_a_batch_is_a_defect() -> None:
    source = SAMPLER + (
        "first = QuantumCircuit(2)\n"
        "first.measure_all()\n"
        "second = QuantumCircuit(2, 2)\n"
        "second.h(0)\n"
        "StatevectorSampler().run([first, second])\n"
    )
    assert codes(lint(source)) == ["QXL103"]


# The beginner ------------------------------------------------------------


def test_four_defects_in_six_lines() -> None:
    # Reported in source order, which is the order the reader meets them in.
    source = SAMPLER + (
        "qc = QuantumCircuit(2, 2)\n"
        "qc.h(0)\n"
        "qc.compose(other)\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "counts = result.get_counts()\n"
        "dists = result.quasi_dists\n"
    )
    findings = lint(source)
    assert codes(findings) == ["QXL104", "QXL103", "QXL101", "QXL102"]
    assert [finding.location.line for finding in findings] == [5, 6, 7, 8]


def test_the_same_mistake_pasted_twice_is_two_findings() -> None:
    source = SAMPLER + (
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "counts = result.get_counts()\n"
        "again = result.get_counts()\n"
    )
    assert codes(lint(source)) == ["QXL101", "QXL101"]


def test_the_oldest_style_of_all_is_correct() -> None:
    source = (
        "from qiskit import QuantumCircuit, transpile\n"
        "from qiskit_aer import AerSimulator\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.h(0)\n"
        "qc.measure([0, 1], [0, 1])\n"
        "backend = AerSimulator()\n"
        "result = backend.run(transpile(qc, backend), shots=1024).result()\n"
        "counts = result.get_counts()\n"
    )
    assert codes(lint(source)) == []


def test_the_local_v1_primitive_keeps_its_own_api() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import Sampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.measure_all()\n"
        "job = Sampler().run([qc])\n"
        "dists = job.result().quasi_dists\n"
    )
    # quasi_dists is the right spelling for a V1 result, so the V2 result rules
    # stay quiet. On a target that still has the V1 Sampler nothing fires at all.
    assert codes(lint(source, qiskit="1.4")) == []
    # Without such a target the reading is current, where the import itself is
    # dead: qiskit.primitives.Sampler was removed in Qiskit 2.0.
    assert codes(lint(source)) == ["QXL205"]


def test_a_measured_circuit_reused_for_an_estimator() -> None:
    source = ESTIMATOR + (
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "qc.measure_all()\n"
        "StatevectorEstimator().run([(qc, SparsePauliOp('ZZ'))])\n"
    )
    assert codes(lint(source)) == ["QXL105"]
