"""QXL102: a V1 result field on a V2 result."""

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


# The estimator half of the same mistake -------------------------------------

ESTIMATOR = (
    "from qiskit import QuantumCircuit\n"
    "from qiskit.primitives import StatevectorEstimator\n"
    "from qiskit.quantum_info import SparsePauliOp\n"
    "qc = QuantumCircuit(2)\n"
    "qc.h(0)\n"
    "result = StatevectorEstimator().run([(qc, SparsePauliOp('ZZ'))]).result()\n"
)


def test_values_on_a_v2_estimator_result_is_reported() -> None:
    # Verified on Qiskit 2.5.2: PrimitiveResult has no `values`, from either
    # primitive, exactly as it has no `quasi_dists`.
    findings = lint(ESTIMATOR + "energies = result.values\n")
    assert codes(findings) == ["QXL102"]
    assert "result[i].data.evs" in findings[0].message
    assert findings[0].fix_hint == "result[0].data.evs"


def test_values_on_a_v2_sampler_result_is_reported() -> None:
    assert codes(lint(HEADER + "x = result.values\n")) == ["QXL102"]


def test_both_fields_are_reported_on_the_same_object() -> None:
    source = ESTIMATOR + "a = result.quasi_dists\nb = result.values\n"
    assert codes(lint(source)) == ["QXL102", "QXL102"]


def test_metadata_exists_on_a_v2_result_and_is_not_reported() -> None:
    # Verified on Qiskit 2.5.2: `metadata` is a real field of PrimitiveResult.
    assert codes(lint(HEADER + "m = result.metadata\n")) == []


def test_values_on_the_data_bin_is_not_reported() -> None:
    # DataBin is a mapping, so `.values` there is the dict method, not the V1 field.
    assert codes(lint(HEADER + "v = result[0].data.values\n")) == []


def test_each_field_carries_its_own_fix_hint() -> None:
    counts = lint(HEADER + "d = result.quasi_dists\n")[0]
    energies = lint(ESTIMATOR + "e = result.values\n")[0]
    assert counts.fix_hint == "result[0].data.<register>.get_counts()"
    assert energies.fix_hint == "result[0].data.evs"
