"""QXL202: a Runtime primitive constructed the V1 way."""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

HEADER = "from qiskit_ibm_runtime import SamplerV2, EstimatorV2, Session, Batch\n"


@pytest.mark.parametrize("primitive", ["SamplerV2", "EstimatorV2"])
@pytest.mark.parametrize("argument", ["backend", "session"])
def test_positive_for_both_removed_arguments(primitive: str, argument: str) -> None:
    source = HEADER + f"p = {primitive}({argument}=thing)\n"
    findings = lint(source)
    assert codes(findings) == ["QXL202"]
    assert "mode=" in findings[0].message


@pytest.mark.parametrize("primitive", ["SamplerV2", "EstimatorV2"])
def test_negative_with_mode(primitive: str) -> None:
    assert codes(lint(HEADER + f"p = {primitive}(mode=thing)\n")) == []


@pytest.mark.parametrize("container", ["Session", "Batch"])
def test_negative_session_and_batch_really_take_backend(container: str) -> None:
    # This is the case a name based check would get wrong: Session and Batch
    # genuinely take backend=, verified on qiskit-ibm-runtime 0.48.0.
    assert codes(lint(HEADER + f"s = {container}(backend=thing)\n")) == []


def test_negative_on_the_aliased_import() -> None:
    source = "from qiskit_ibm_runtime import SamplerV2 as Sampler\np = Sampler(mode=thing)\n"
    assert codes(lint(source)) == []


def test_positive_through_an_alias() -> None:
    source = "from qiskit_ibm_runtime import SamplerV2 as Sampler\np = Sampler(backend=thing)\n"
    assert codes(lint(source)) == ["QXL202"]


def test_negative_on_a_local_class_of_the_same_name() -> None:
    source = "class SamplerV2:\n    pass\np = SamplerV2(backend=thing)\n"
    assert codes(lint(source)) == []


def test_negative_on_the_local_primitives() -> None:
    # qiskit.primitives.BackendSamplerV2 really does take a backend.
    source = "from qiskit.primitives import BackendSamplerV2\np = BackendSamplerV2(backend=thing)\n"
    assert codes(lint(source)) == []


def test_only_one_finding_per_construction() -> None:
    source = HEADER + "p = SamplerV2(backend=a, session=b)\n"
    assert codes(lint(source)) == ["QXL202"]


def test_location_points_at_the_argument() -> None:
    finding = lint(HEADER + "p = SamplerV2(backend=thing)\n")[0]
    assert finding.location.line == 2
    assert finding.location.column > 10
