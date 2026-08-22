"""QXL201: the removed ibm_quantum channel, and its version gate."""

from __future__ import annotations

import pytest

from qxlint.diagnostics import Severity
from tests.conftest import codes, lint

SOURCE = (
    "from qiskit_ibm_runtime import QiskitRuntimeService\n"
    'service = QiskitRuntimeService(channel="ibm_quantum")\n'
)


@pytest.mark.parametrize("target", ["0.41", "0.41.0", "0.48", ">=0.41", "~=0.48.0"])
def test_positive_when_every_allowed_version_removed_it(target: str) -> None:
    findings = lint(SOURCE, runtime=target)
    assert codes(findings) == ["QXL201"]
    assert findings[0].severity is Severity.ERROR
    assert "removed" in findings[0].message


@pytest.mark.parametrize("target", ["0.40", "0.40.2", "==0.40.*"])
def test_deprecation_message_below_the_removal_version(target: str) -> None:
    findings = lint(SOURCE, runtime=target)
    assert codes(findings) == ["QXL201"]
    assert findings[0].severity is Severity.WARNING
    assert "deprecated" in findings[0].message


@pytest.mark.parametrize("target", [">=0.38,<0.43", ">=0.40", "!=0.41,>=0.38"])
def test_a_specifier_that_spans_the_removal_is_reported(target: str) -> None:
    # The project says it supports versions where the channel is gone, so the
    # call breaks somewhere inside its own declared range. This is the policy
    # QXL202, QXL203 and QXL205 use, and QXL201 now uses it too.
    findings = lint(SOURCE, runtime=target)
    assert codes(findings) == ["QXL201"]
    assert findings[0].severity is Severity.ERROR
    assert "which the declared target allows" in findings[0].message


def test_silent_below_the_deprecation_version() -> None:
    assert codes(lint(SOURCE, runtime="0.39")) == []


@pytest.mark.parametrize("target", ["0.30", ">=0.28,<0.40"])
def test_silent_on_a_target_entirely_before_the_deprecation(target: str) -> None:
    assert codes(lint(SOURCE, runtime=target)) == []


def test_an_undeclared_target_reads_as_current() -> None:
    # V1 era runtimes are 8 releases behind, so the reading that helps a
    # migration is the current one, and it is the reading the other four
    # version gated rules already take.
    findings = lint(SOURCE)
    assert codes(findings) == ["QXL201"]
    assert findings[0].severity is Severity.ERROR
    assert "was removed" in findings[0].message


def test_constant_propagation_through_a_variable() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        'CHANNEL = "ibm_quantum"\n'
        "service = QiskitRuntimeService(channel=CHANNEL)\n"
    )
    assert codes(lint(source, runtime="0.48")) == ["QXL201"]


def test_negative_when_the_channel_is_omitted() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService(token=TOKEN)\n"
    )
    assert codes(lint(source, runtime="0.48")) == []


@pytest.mark.parametrize("channel", ["ibm_quantum_platform", "ibm_cloud", "local"])
def test_negative_for_every_currently_valid_channel(channel: str) -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        f'service = QiskitRuntimeService(channel="{channel}")\n'
    )
    assert codes(lint(source, runtime="0.48")) == []


def test_negative_on_an_unrelated_class_with_the_same_argument() -> None:
    source = 'client = SomeOtherService(channel="ibm_quantum")\n'
    assert codes(lint(source, runtime="0.48")) == []


def test_negative_when_the_value_is_computed() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService(channel=pick_channel())\n"
    )
    assert codes(lint(source, runtime="0.48")) == []


def test_location_points_at_the_argument() -> None:
    finding = lint(SOURCE, runtime="0.48")[0]
    assert finding.location.line == 2
    assert finding.location.column > 30


# save_account ------------------------------------------------------------
#
# The constructor was the only call site checked, and save_account is the one
# the IBM setup docs open with. Eleven of them sat unreported across the
# external corpus. Verified on qiskit-ibm-runtime 0.48.0: save_account raises
# InvalidAccountError for this value, so it is the same defect.

SAVE = (
    "from qiskit_ibm_runtime import QiskitRuntimeService\n"
    'QiskitRuntimeService.save_account(channel="ibm_quantum", token="t")\n'
)


def test_save_account_is_reported() -> None:
    findings = lint(SAVE, runtime="0.48")
    assert codes(findings) == ["QXL201"]
    assert findings[0].location.column > 30


def test_save_account_through_an_import_alias_is_reported() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService as QRS\n"
        'QRS.save_account(channel="ibm_quantum")\n'
    )
    assert codes(lint(source, runtime="0.48")) == ["QXL201"]


def test_save_account_on_an_instance_is_reported() -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService()\n"
        'service.save_account(channel="ibm_quantum")\n'
    )
    assert codes(lint(source, runtime="0.48")) == ["QXL201"]


def test_save_account_obeys_the_same_version_gate() -> None:
    assert codes(lint(SAVE, runtime="0.40")) == ["QXL201"]
    assert lint(SAVE, runtime="0.40")[0].severity is Severity.WARNING
    # A spanning target and an undeclared one both reach the removal.
    assert codes(lint(SAVE, runtime=">=0.38,<0.43")) == ["QXL201"]
    assert codes(lint(SAVE)) == ["QXL201"]
    assert codes(lint(SAVE, runtime="0.39")) == []


@pytest.mark.parametrize("channel", ["ibm_quantum_platform", "ibm_cloud"])
def test_save_account_with_a_valid_channel_is_silent(channel: str) -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        f'QiskitRuntimeService.save_account(channel="{channel}")\n'
    )
    assert codes(lint(source, runtime="0.48")) == []


def test_a_local_class_with_the_same_name_is_not_flagged() -> None:
    source = (
        "class QiskitRuntimeService:\n"
        "    @staticmethod\n"
        "    def save_account(**kwargs):\n"
        "        pass\n"
        'QiskitRuntimeService.save_account(channel="ibm_quantum")\n'
        "local = QiskitRuntimeService()\n"
        'local.save_account(channel="ibm_quantum")\n'
    )
    assert codes(lint(source, runtime="0.48")) == []


def test_save_account_on_an_unrelated_object_is_not_flagged() -> None:
    source = 'store.save_account(channel="ibm_quantum")\n'
    assert codes(lint(source, runtime="0.48")) == []


@pytest.mark.parametrize("channel", ['channel="ibm_cloud"', "channel=pick()", ""])
def test_save_account_on_an_instance_without_the_removed_value_is_silent(channel: str) -> None:
    source = (
        "from qiskit_ibm_runtime import QiskitRuntimeService\n"
        "service = QiskitRuntimeService()\n"
        f"service.save_account({channel})\n"
    )
    assert codes(lint(source, runtime="0.48")) == []


# The renamed service class ------------------------------------------------
#
# qiskit-ibm-runtime 0.49 exports QiskitRuntimeService a second time as
# IBMQuantumComputeService. It is the same class object and takes the same
# channel, so every call site the rule already knows about has a second
# spelling that must be read the same way.

RENAMED = (
    "from qiskit_ibm_runtime import IBMQuantumComputeService\n"
    'service = IBMQuantumComputeService(channel="ibm_quantum")\n'
)


def test_renamed_service_class_is_reported() -> None:
    findings = lint(RENAMED, runtime="0.49")
    assert codes(findings) == ["QXL201"]
    assert findings[0].severity is Severity.ERROR


def test_renamed_service_class_save_account_is_reported() -> None:
    source = (
        "from qiskit_ibm_runtime import IBMQuantumComputeService\n"
        'IBMQuantumComputeService.save_account(channel="ibm_quantum", token="t")\n'
    )
    assert codes(lint(source, runtime="0.49")) == ["QXL201"]


def test_renamed_service_class_on_an_instance_is_reported() -> None:
    source = (
        "from qiskit_ibm_runtime import IBMQuantumComputeService\n"
        "service = IBMQuantumComputeService()\n"
        'service.save_account(channel="ibm_quantum")\n'
    )
    assert codes(lint(source, runtime="0.49")) == ["QXL201"]


def test_renamed_service_class_obeys_the_version_gate() -> None:
    assert codes(lint(RENAMED)) == ["QXL201"]
    assert codes(lint(RENAMED, runtime="0.39")) == []


def test_renamed_service_class_with_a_valid_channel_is_silent() -> None:
    source = (
        "from qiskit_ibm_runtime import IBMQuantumComputeService\n"
        'service = IBMQuantumComputeService(channel="ibm_cloud")\n'
    )
    assert codes(lint(source, runtime="0.49")) == []


def test_a_local_class_with_the_renamed_spelling_is_not_flagged() -> None:
    source = (
        "class IBMQuantumComputeService:\n"
        "    @staticmethod\n"
        "    def save_account(**kwargs):\n"
        "        pass\n"
        'IBMQuantumComputeService.save_account(channel="ibm_quantum")\n'
        "local = IBMQuantumComputeService()\n"
        'local.save_account(channel="ibm_quantum")\n'
    )
    assert codes(lint(source, runtime="0.49")) == []
