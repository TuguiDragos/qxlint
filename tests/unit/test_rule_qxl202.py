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


# The bare Runtime names are version dependent ------------------------------
#
# `qiskit_ibm_runtime.Sampler` was SamplerV1 until 0.28, the release that
# removed V1 and rebound the name. Read from the published wheels: 0.27.1
# imports `SamplerV1 as Sampler`, 0.28.0 imports `SamplerV2 as Sampler`. On a
# target proven to predate that, session= and backend= are the correct V1
# spelling and this rule has nothing to say.

BARE = "from qiskit_ibm_runtime import Sampler, Estimator\n"


@pytest.mark.parametrize("target", ["0.20", "0.27", "0.27.1", ">=0.20,<0.28"])
def test_the_bare_name_is_v1_on_a_target_that_predates_the_rebinding(target: str) -> None:
    assert codes(lint(BARE + "p = Sampler(backend=thing)\n", runtime=target)) == []
    assert codes(lint(BARE + "p = Estimator(session=thing)\n", runtime=target)) == []


@pytest.mark.parametrize("target", ["0.28", "0.48", ">=0.28"])
def test_the_bare_name_is_v2_from_the_release_that_rebound_it(target: str) -> None:
    assert codes(lint(BARE + "p = Sampler(backend=thing)\n", runtime=target)) == ["QXL202"]


@pytest.mark.parametrize("target", [None, ">=0.20", ">=0.25,<0.30"])
def test_an_unproven_target_keeps_reading_the_bare_name_as_v2(target: str | None) -> None:
    # Nothing proves V1 here, and the current package has no V1 in it, so the
    # reading that helps a migration is the one kept.
    assert codes(lint(BARE + "p = Sampler(backend=thing)\n", runtime=target)) == ["QXL202"]


@pytest.mark.parametrize("target", ["0.20", "0.27"])
def test_the_explicit_v2_name_is_never_downgraded(target: str) -> None:
    assert codes(lint(HEADER + "p = SamplerV2(backend=thing)\n", runtime=target)) == ["QXL202"]
