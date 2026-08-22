"""QXL205: an import of a symbol Qiskit removed."""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint


@pytest.mark.parametrize(
    ("line", "symbol", "removed_in"),
    [
        ("from qiskit import execute", "qiskit.execute", "1.0"),
        ("from qiskit import Aer", "qiskit.Aer", "1.0"),
        ("from qiskit import IBMQ", "qiskit.IBMQ", "1.0"),
        ("from qiskit import assemble", "qiskit.assemble", "2.0"),
        ("from qiskit.opflow import PauliSumOp", "qiskit.opflow", "1.0"),
        ("from qiskit.algorithms import VQE", "qiskit.algorithms", "1.0"),
        ("from qiskit.utils import QuantumInstance", "qiskit.utils.QuantumInstance", "1.0"),
        ("from qiskit.primitives import Sampler", "qiskit.primitives.Sampler", "2.0"),
        ("from qiskit.primitives import Estimator", "qiskit.primitives.Estimator", "2.0"),
        ("from qiskit.primitives import BackendSampler", "qiskit.primitives.BackendSampler", "2.0"),
        (
            "from qiskit.primitives import BackendEstimator",
            "qiskit.primitives.BackendEstimator",
            "2.0",
        ),
        ("import qiskit.providers.aer", "qiskit.providers.aer", "1.0"),
        ("import qiskit.opflow", "qiskit.opflow", "1.0"),
    ],
)
def test_each_removed_symbol_is_reported(line: str, symbol: str, removed_in: str) -> None:
    # Every release read from the published wheels and every absence confirmed
    # on the installed Qiskit 2.5.2.
    findings = lint(line + "\n")
    assert codes(findings) == ["QXL205"]
    assert symbol in findings[0].message
    assert f"Qiskit {removed_in}" in findings[0].message


@pytest.mark.parametrize(
    "line",
    [
        "from qiskit import QuantumCircuit",
        "from qiskit import transpile",
        "from qiskit.primitives import StatevectorSampler",
        "from qiskit.primitives import BackendSamplerV2",
        "from qiskit.quantum_info import SparsePauliOp",
        "from qiskit_aer import AerSimulator",
        "from qiskit_ibm_runtime import SamplerV2",
        "import numpy",
    ],
)
def test_a_current_import_is_not_reported(line: str) -> None:
    assert codes(lint(line + "\n")) == []


def test_a_relative_import_is_never_considered() -> None:
    assert codes(lint("from . import opflow\nfrom .algorithms import thing\n")) == []


def test_a_local_module_of_the_same_name_is_not_touched() -> None:
    assert codes(lint("from myproject.algorithms import solve\nimport myproject.opflow\n")) == []


@pytest.mark.parametrize("target", ["0.45", "0.46"])
def test_silent_on_a_target_that_still_has_everything(target: str) -> None:
    source = "from qiskit import execute\nfrom qiskit.primitives import Sampler\n"
    assert codes(lint(source, qiskit=target)) == []


def test_a_one_zero_target_reports_only_what_one_zero_removed() -> None:
    source = "from qiskit import execute\nfrom qiskit.primitives import Sampler\n"
    findings = lint(source, qiskit="1.4")
    assert codes(findings) == ["QXL205"]
    assert "qiskit.execute" in findings[0].message


def test_a_two_zero_target_reports_both() -> None:
    source = "from qiskit import execute\nfrom qiskit.primitives import Sampler\n"
    assert codes(lint(source, qiskit="2.0")) == ["QXL205", "QXL205"]


def test_an_undeclared_target_reads_as_current() -> None:
    assert codes(lint("from qiskit import execute\n")) == ["QXL205"]


def test_several_names_on_one_line_each_report() -> None:
    findings = lint("from qiskit import QuantumCircuit, execute, Aer\n")
    assert codes(findings) == ["QXL205", "QXL205"]


def test_an_aliased_import_is_still_the_same_symbol() -> None:
    assert codes(lint("from qiskit import execute as run_it\n")) == ["QXL205"]


def test_the_fix_hint_names_the_replacement() -> None:
    finding = lint("from qiskit import Aer\n")[0]
    assert "qiskit_aer" in finding.fix_hint


# The families added after the first table --------------------------------


@pytest.mark.parametrize(
    ("line", "symbol", "removed_in"),
    [
        ("from qiskit.extensions import UnitaryGate", "qiskit.extensions", "1.0"),
        ("import qiskit.extensions", "qiskit.extensions", "1.0"),
        (
            "from qiskit.providers.fake_provider import FakeManilaV2",
            "qiskit.providers.fake_provider.FakeManilaV2",
            "1.0",
        ),
        (
            "from qiskit.providers.fake_provider import FakeVigo",
            "qiskit.providers.fake_provider.FakeVigo",
            "1.0",
        ),
        (
            "from qiskit.providers.fake_provider import Fake5QV1",
            "qiskit.providers.fake_provider.Fake5QV1",
            "2.0",
        ),
        (
            "from qiskit.providers.fake_provider import FakeOpenPulse2Q",
            "qiskit.providers.fake_provider.FakeOpenPulse2Q",
            "2.0",
        ),
    ],
)
def test_the_later_families_are_reported(line: str, symbol: str, removed_in: str) -> None:
    # Read from the wheels: 1.0.0 still exported Fake5QV1 and FakeOpenPulse2Q
    # and had already lost the device fakes; 2.0.0 exports only GenericBackendV2.
    findings = lint(line + "\n")
    assert codes(findings) == ["QXL205"]
    assert symbol in findings[0].message
    assert f"Qiskit {removed_in}" in findings[0].message


@pytest.mark.parametrize(
    "line",
    [
        "from qiskit.providers.fake_provider import GenericBackendV2",
        "from qiskit.providers.fake_provider import generic_backend_v2",
        "import qiskit.providers.fake_provider",
    ],
)
def test_what_the_fake_provider_still_offers_is_not_reported(line: str) -> None:
    assert codes(lint(line + "\n")) == []


CIRCUIT = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(1)\n"


@pytest.mark.parametrize(
    ("call", "method"),
    [("qc.bind_parameters({})", "bind_parameters"), ("qc.qasm()", "qasm")],
)
def test_a_removed_circuit_method_is_reported(call: str, method: str) -> None:
    # Verified on Qiskit 2.5.2: both raise AttributeError.
    findings = lint(CIRCUIT + f"x = {call}\n")
    assert codes(findings) == ["QXL205"]
    assert f"QuantumCircuit.{method}" in findings[0].message
    assert "AttributeError" in findings[0].message


def test_the_surviving_spelling_is_not_reported() -> None:
    assert codes(lint(CIRCUIT + "x = qc.assign_parameters({})\n")) == []


def test_a_removed_method_name_on_something_else_is_not_reported() -> None:
    # The rule reads the receiver's proven kind, never the method name alone.
    assert codes(lint("thing.qasm()\nother.bind_parameters({})\n")) == []


@pytest.mark.parametrize("target", ["0.45", "0.46"])
def test_the_later_families_are_silent_on_an_older_target(target: str) -> None:
    source = (
        "from qiskit.extensions import UnitaryGate\n"
        "from qiskit.providers.fake_provider import FakeManilaV2\n"
    )
    assert codes(lint(source, qiskit=target)) == []


def test_a_one_zero_target_separates_the_two_fake_generations() -> None:
    source = (
        "from qiskit.providers.fake_provider import FakeManilaV2\n"
        "from qiskit.providers.fake_provider import Fake5QV1\n"
    )
    assert codes(lint(source, qiskit="1.4")) == ["QXL205"]
    assert codes(lint(source, qiskit="2.0")) == ["QXL205", "QXL205"]


@pytest.mark.parametrize("target", ["0.45", "0.46"])
def test_a_removed_circuit_method_is_silent_on_an_older_target(target: str) -> None:
    assert codes(lint(CIRCUIT + "x = qc.qasm()\n", qiskit=target)) == []


def test_a_star_import_of_a_module_that_still_exists_is_not_reported() -> None:
    # Verified on Qiskit 2.5.2: this succeeds, binding whatever the module still
    # has. The name `*` is not a removed symbol.
    assert codes(lint("from qiskit.providers.fake_provider import *\n")) == []


def test_a_star_import_of_a_removed_module_is_still_reported() -> None:
    # Verified on Qiskit 2.5.2: ModuleNotFoundError, whatever is asked for.
    assert codes(lint("from qiskit.opflow import *\n")) == ["QXL205"]
