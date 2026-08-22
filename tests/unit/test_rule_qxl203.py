"""QXL203: service= passed to a Session or Batch that dropped it."""

from __future__ import annotations

import pytest

from tests.conftest import codes, lint

BAD = (
    "from qiskit_ibm_runtime import QiskitRuntimeService, Session\n"
    "service = QiskitRuntimeService()\n"
    'session = Session(service=service, backend="ibm_brisbane")\n'
)


def test_positive_on_session() -> None:
    findings = lint(BAD)
    assert codes(findings) == ["QXL203"]
    assert "removed in qiskit-ibm-runtime 0.34" in findings[0].message


def test_positive_on_batch() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService, Batch\n"
        "service = QiskitRuntimeService()\n"
        'batch = Batch(service=service, backend="ibm_brisbane")\n'
    )
    findings = lint(source)
    assert codes(findings) == ["QXL203"]
    assert findings[0].message.startswith("Batch takes no service")


def test_the_finding_points_at_the_offending_argument() -> None:
    # Anchored on the argument passed as `service`, the same way QXL201 anchors
    # on the channel value rather than on the whole call.
    finding = lint(BAD)[0]
    line = BAD.splitlines()[2]
    assert finding.location.line == 3
    assert line[finding.location.column - 1 : finding.location.end_column - 1] == "service"


def test_negative_on_the_supported_form() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService, Session\n"
        "service = QiskitRuntimeService()\n"
        'backend = service.backend("ibm_brisbane")\n'
        "session = Session(backend=backend)\n"
    )
    assert codes(lint(source)) == []


@pytest.mark.parametrize("target", ["0.30", "0.33.2", ">=0.20,<0.34"])
def test_silent_on_a_target_that_still_takes_it(target: str) -> None:
    # Read from the published wheels: 0.33.2 still declares the argument.
    assert codes(lint(BAD, runtime=target)) == []


@pytest.mark.parametrize("target", ["0.34", "0.45", ">=0.40"])
def test_reported_on_a_target_that_proves_it_is_gone(target: str) -> None:
    assert codes(lint(BAD, runtime=target)) == ["QXL203"]


def test_an_undeclared_target_reads_as_current() -> None:
    # The migration reading, matching QXL202 rather than QXL201.
    assert codes(lint(BAD, runtime=None)) == ["QXL203"]


def test_a_spanning_target_still_reports() -> None:
    assert codes(lint(BAD, runtime=">=0.30,<0.40")) == ["QXL203"]


def test_a_local_class_of_the_same_name_is_not_touched() -> None:
    source = 'class Session:\n    def __init__(self, service=None): ...\ns = Session(service="x")\n'
    assert codes(lint(source)) == []


def test_an_aliased_import_still_matches() -> None:
    source = "from qiskit_ibm_runtime import Session as S\ns = S(service=thing)\n"
    assert codes(lint(source)) == ["QXL203"]
