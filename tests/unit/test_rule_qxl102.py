"""QXL102: quasi_dists on a V2 result."""

from __future__ import annotations

from tests.conftest import codes, lint

HEADER = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(1)\n"
    "qc.measure_all()\n"
    "result = StatevectorSampler().run([qc]).result()\n"
)


def test_positive_on_v2_result() -> None:
    assert codes(lint(HEADER + "dists = result.quasi_dists\n")) == ["QXL102"]


def test_negative_on_v1_sampler_result() -> None:
    # SamplerResult still exists in Qiskit 2.x and still has quasi_dists.
    source = (
        "from qiskit.primitives import SamplerResult\n"
        "result = SamplerResult(quasi_dists=[], metadata=[])\n"
        "dists = result.quasi_dists\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_an_unknown_object() -> None:
    assert codes(lint("dists = something.quasi_dists\n")) == []


def test_negative_on_a_variable_merely_named_result() -> None:
    assert codes(lint("result = helper()\ndists = result.quasi_dists\n")) == []


def test_negative_on_a_pub_result() -> None:
    assert codes(lint(HEADER + "dists = result[0].quasi_dists\n")) == []


def test_attribute_store_is_not_a_read() -> None:
    assert codes(lint(HEADER + "result.quasi_dists = 1\n")) == []


def test_negative_on_a_runtime_v1_result_when_the_target_predates_the_rebinding() -> None:
    # `Sampler` is SamplerV1 before 0.28, and quasi_dists is the correct V1
    # spelling on the result it returns.
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit_ibm_runtime import Sampler\n"
        "qc = QuantumCircuit(1)\n"
        "qc.measure_all()\n"
        "result = Sampler().run(circuits=qc).result()\n"
        "dists = result.quasi_dists\n"
    )
    assert codes(lint(source, runtime="0.27")) == []
    assert codes(lint(source, runtime="0.28")) == ["QXL102"]
