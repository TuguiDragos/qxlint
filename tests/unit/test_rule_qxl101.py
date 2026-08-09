"""QXL101: get_counts() on the wrong receiver."""

from __future__ import annotations

from tests.conftest import codes, lint

HEADER = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorSampler\n"
    "qc = QuantumCircuit(2, 2)\n"
    "qc.measure_all()\n"
    "result = StatevectorSampler().run([qc]).result()\n"
)


def test_positive_on_primitive_result() -> None:
    assert codes(lint(HEADER + "counts = result.get_counts()\n")) == ["QXL101"]


def test_positive_on_pub_result() -> None:
    assert codes(lint(HEADER + "counts = result[0].get_counts()\n")) == ["QXL101"]


def test_positive_on_data_bin() -> None:
    assert codes(lint(HEADER + "counts = result[0].data.get_counts()\n")) == ["QXL101"]


def test_negative_on_bit_array_is_the_correct_v2_call() -> None:
    assert codes(lint(HEADER + "counts = result[0].data.meas.get_counts()\n")) == []


def test_negative_on_legacy_backend_result() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService()\n"
        "backend = service.backend('x')\n"
        "counts = backend.run(qc).result().get_counts()\n"
    )
    assert codes(lint(source)) == []


def test_negative_on_unknown_receiver() -> None:
    assert codes(lint("counts = whatever.get_counts()\n")) == []


def test_negative_on_join_data_which_may_return_an_ndarray() -> None:
    # join_data is documented as returning BitArray or ndarray, so the receiver
    # is a union and nothing may be concluded from it.
    assert codes(lint(HEADER + "counts = result[0].join_data().get_counts()\n")) == []


def test_negative_when_the_register_name_is_not_meas() -> None:
    source = (
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2, 2)\n"
        "qc.measure([0, 1], [0, 1])\n"
        "result = StatevectorSampler().run([qc]).result()\n"
        "counts = result[0].data.c.get_counts()\n"
    )
    assert codes(lint(source)) == []


def test_message_describes_the_shape_not_a_fixed_path() -> None:
    finding = lint(HEADER + "counts = result.get_counts()\n")[0]
    assert "<classical register>" in finding.message
    assert "meas" not in finding.message


def test_noqa_suppresses_it() -> None:
    assert codes(lint(HEADER + "counts = result.get_counts()  # noqa: QXL101\n")) == []
