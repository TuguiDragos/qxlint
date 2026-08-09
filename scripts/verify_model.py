"""Re-verify the hardcoded API model against an installed Qiskit.

The tables in `qxlint.semantics.model` are hardcoded so Engine A can analyse a
project targeting a different Qiskit version, and can run with no Qiskit at all.
That is only safe if something notices when upstream moves. This script is what
the scheduled workflow runs; it exits non-zero on the first real disagreement.

Run it locally with `python scripts/verify_model.py`.
"""

from __future__ import annotations

import importlib
import sys
import warnings

import numpy as np

from qxlint.semantics import model

FAILURES: list[str] = []
PERFORMED: list[str] = []
SKIPPED: list[str] = []


def check(condition: bool, message: str) -> None:
    PERFORMED.append(message)
    if not condition:
        FAILURES.append(message)


def resolve(qualified: str) -> object | None:
    """Import a dotted path, trying each split point."""
    parts = qualified.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:cut])
        try:
            obj: object = importlib.import_module(module_name)
        except ImportError:
            continue
        for attribute in parts[cut:]:
            if not hasattr(obj, attribute):
                return None
            obj = getattr(obj, attribute)
        return obj
    return None


def installed(qualified: str) -> bool:
    """Is the distribution providing this symbol present at all?

    A package that is simply not installed is a skip, not a drift failure. Only
    a symbol that vanished from an installed package is a real problem.
    """
    root = qualified.split(".", maxsplit=1)[0]
    try:
        importlib.import_module(root)
    except ImportError:
        return False
    return True


def verify_symbols() -> None:
    for qualified in model.CONSTRUCTORS:
        if not installed(qualified):
            SKIPPED.append(qualified)
            continue
        check(resolve(qualified) is not None, f"constructor no longer resolves: {qualified}")
    for qualified in model.SYMBOL_ALIASES.values():
        if not installed(qualified):
            SKIPPED.append(qualified)
            continue
        check(resolve(qualified) is not None, f"alias target no longer resolves: {qualified}")
    for qualified in model.MEASURING_OPERATIONS | model.NON_MEASURING_OPERATIONS:
        if qualified.startswith("qiskit.circuit.library."):
            check(resolve(qualified) is not None, f"operation class missing: {qualified}")


def verify_circuit_methods() -> None:
    from qiskit import QuantumCircuit

    groups = {
        "GATE_METHODS": model.GATE_METHODS,
        "MEASURING_METHODS": model.MEASURING_METHODS,
        "CONTROL_FLOW_BUILDERS": model.CONTROL_FLOW_BUILDERS,
        "CIRCUIT_DERIVING_METHODS": model.CIRCUIT_DERIVING_METHODS,
    }
    for label, names in groups.items():
        for name in names:
            check(hasattr(QuantumCircuit, name), f"{label}: QuantumCircuit has no '{name}'")

    check(
        not (model.GATE_METHODS & model.MEASURING_METHODS),
        "a method is listed as both a plain gate and a measuring method",
    )


def verify_no_gate_method_measures() -> None:
    """A gate method that started adding a measurement would cause false negatives."""
    from qiskit import QuantumCircuit

    skip = {"break_loop", "continue_loop", "store", "initialize", "prepare_state", "unitary"}
    for name in sorted(model.GATE_METHODS - skip):
        circuit = QuantumCircuit(3, 3)
        method = getattr(circuit, name, None)
        if method is None:
            continue
        for args in ((0,), (0, 1), (0, 1, 2), (0.1, 0), (0.1, 0, 1)):
            try:
                method(*args)
            except Exception:
                continue
            break
        measures = [
            instruction for instruction in circuit.data if instruction.operation.name == "measure"
        ]
        check(not measures, f"gate method '{name}' now adds a measurement")


def verify_library_circuits_have_no_measurement() -> None:
    """The library circuit table claims every one of them is measurement free.

    A wrong entry here is a false positive from QXL103, so it is checked by
    construction rather than trusted. Arguments differ per class, so each one
    is tried against a small set until one is accepted.
    """
    import numpy as np
    from qiskit import QuantumCircuit
    from qiskit.circuit import ControlFlowOp
    from qiskit.quantum_info import SparsePauliOp

    base = QuantumCircuit(2)
    base.h(0)
    base.cx(0, 1)
    attempts: tuple[tuple[object, ...], ...] = (
        (2,),
        (3,),
        (2, "ry", "cx"),
        (SparsePauliOp("ZZ"),),
        (base,),
        (base, base),
        (2, base),
        (np.array([[0, 1], [1, 0]]),),
        ([1, -1, 1, -1], [1, 1, -1, -1]),
    )

    for name in model.LIBRARY_CIRCUITS:
        qualified = f"qiskit.circuit.library.{name}"
        factory = resolve(qualified)
        if factory is None:
            check(False, f"library circuit no longer resolves: {qualified}")
            continue
        built: QuantumCircuit | None = None
        for args in attempts:
            try:
                with warnings.catch_warnings():
                    # Several class forms are deprecated in favour of the
                    # function forms. Both spellings are still in the table
                    # because both are still in real code.
                    warnings.simplefilter("ignore", DeprecationWarning)
                    candidate = factory(*args)  # type: ignore[operator]
            except Exception:
                continue
            if isinstance(candidate, QuantumCircuit):
                built = candidate
                break
        if built is None:
            check(False, f"library circuit could not be constructed: {qualified}")
            continue
        measures = [
            instruction for instruction in built.data if instruction.operation.name == "measure"
        ]
        check(not measures, f"library circuit '{name}' now contains a measurement")
        control_flow = [
            instruction
            for instruction in built.data
            if isinstance(instruction.operation, ControlFlowOp)
        ]
        check(not control_flow, f"library circuit '{name}' now contains control flow")


def verify_register_names() -> None:
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(2)
    circuit.measure_all()
    check(
        [register.name for register in circuit.cregs] == [model.MEASURE_ALL_REGISTER],
        f"measure_all no longer creates a register named '{model.MEASURE_ALL_REGISTER}'",
    )

    active = QuantumCircuit(2)
    active.h(0)
    active.measure_active()
    check(
        [register.name for register in active.cregs] == [model.MEASURE_ACTIVE_REGISTER],
        f"measure_active no longer creates a register named '{model.MEASURE_ACTIVE_REGISTER}'",
    )

    sized = QuantumCircuit(2, 2)
    check(
        [register.name for register in sized.cregs] == ["c"],
        "QuantumCircuit(n, m) no longer creates a register named 'c'",
    )
    check(QuantumCircuit(2).cregs == [], "QuantumCircuit(n) now creates a classical register")


def verify_self_inverse() -> None:
    """Square every listed gate. This list must never be inferred from names."""
    from qiskit.circuit import library
    from qiskit.quantum_info import Operator

    for class_name in sorted(set(model.SELF_INVERSE_GATES.values())):
        gate_class = getattr(library, class_name, None)
        if gate_class is None:
            FAILURES.append(f"self inverse gate class missing: {class_name}")
            continue
        matrix = Operator(gate_class()).data
        identity = np.eye(matrix.shape[0])
        check(
            bool(np.allclose(matrix @ matrix, identity)),
            f"{class_name} is listed as self inverse but is not",
        )

    # Gates that look self inverse and are not. If one of these ever becomes
    # listed, QXL302 would start deleting real operations.
    for class_name in ("SGate", "TGate", "SXGate", "iSwapGate", "DCXGate"):
        check(
            class_name not in model.SELF_INVERSE_GATES.values(),
            f"{class_name} must not be in the self inverse list",
        )
        gate_class = getattr(library, class_name, None)
        if gate_class is not None:
            matrix = Operator(gate_class()).data
            check(
                not np.allclose(matrix @ matrix, np.eye(matrix.shape[0])),
                f"{class_name} is now self inverse; the exclusion list is stale",
            )


def verify_result_shape() -> None:
    """The shape QXL101 and QXL102 depend on."""
    from qiskit import QuantumCircuit
    from qiskit.primitives import StatevectorSampler

    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    result = StatevectorSampler().run([circuit], shots=8).result()

    check(not hasattr(result, "get_counts"), "PrimitiveResult now has get_counts")
    check(not hasattr(result, "quasi_dists"), "PrimitiveResult now has quasi_dists")
    check(not hasattr(result[0], "get_counts"), "PubResult now has get_counts")
    check(not hasattr(result[0].data, "get_counts"), "DataBin now has get_counts")
    check(hasattr(result[0].data, "meas"), "the measure_all register is no longer 'meas'")
    check(
        hasattr(result[0].data.meas, "get_counts"),
        "BitArray no longer has get_counts, which QXL101 points users to",
    )
    check(hasattr(result[0], "join_data"), "SamplerPubResult no longer has join_data")

    try:
        from qiskit.primitives import SamplerResult
    except ImportError:
        FAILURES.append("qiskit.primitives.SamplerResult is gone; QXL102 negative case changed")
    else:
        fields = getattr(SamplerResult, "__annotations__", {})
        check("quasi_dists" in fields, "V1 SamplerResult no longer declares quasi_dists")


def verify_unmeasured_sampler_behaviour() -> None:
    """QXL103's rationale claims this fails quietly. Confirm it still does.

    The two sampler calls below are exactly what QXL103 reports, on purpose:
    this function exists to prove the quiet failure is still quiet. They are the
    documented legitimate case, so they are suppressed rather than reworded.
    """
    import warnings

    from qiskit import QuantumCircuit
    from qiskit.primitives import StatevectorSampler

    # No classical register: Qiskit warns and returns an empty data bin.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        empty = StatevectorSampler().run([QuantumCircuit(2)], shots=4).result()  # noqa: QXL103
    check(
        any("measurement" in str(entry.message).lower() for entry in caught),
        "an unmeasured circuit with no register no longer warns; QXL103's rationale changed",
    )
    check(
        len(list(empty[0].data.keys())) == 0,
        "an unmeasured circuit no longer produces an empty data bin",
    )

    # Classical register but no measure instruction: silent, and all zeros.
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        StatevectorSampler().run([circuit], shots=4).result()  # noqa: QXL103
    check(
        len(caught) == 0,
        "a circuit with registers but no measure now warns; QXL103's rationale needs updating",
    )


def verify_control_flow() -> None:
    from qiskit.circuit import ControlFlowOp

    names = {subclass.__name__ for subclass in ControlFlowOp.__subclasses__()}
    check(
        {"IfElseOp", "ForLoopOp", "WhileLoopOp", "SwitchCaseOp"} <= names,
        f"ControlFlowOp subclasses changed: {sorted(names)}",
    )
    check(hasattr(ControlFlowOp, "blocks"), "ControlFlowOp no longer exposes blocks")


def verify_target_api() -> None:
    from qiskit.transpiler import Target

    check(
        hasattr(Target, "instruction_supported"),
        "Target.instruction_supported is gone; QXL301 depends on it",
    )
    check(hasattr(Target, "num_qubits"), "Target.num_qubits is gone")


def main() -> int:
    import qiskit

    print(f"qiskit {qiskit.__version__}")
    try:
        import qiskit_ibm_runtime

        print(f"qiskit-ibm-runtime {qiskit_ibm_runtime.__version__}")
    except ImportError:
        print("qiskit-ibm-runtime not installed")

    for step in (
        verify_symbols,
        verify_circuit_methods,
        verify_no_gate_method_measures,
        verify_library_circuits_have_no_measurement,
        verify_register_names,
        verify_self_inverse,
        verify_result_shape,
        verify_unmeasured_sampler_behaviour,
        verify_control_flow,
        verify_target_api,
    ):
        step()

    if FAILURES:
        print(f"\n{len(FAILURES)} of {len(PERFORMED)} checks failed:\n")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1

    if SKIPPED:
        print(f"\nskipped {len(SKIPPED)} symbols from packages that are not installed")
    print(f"\nall {len(PERFORMED)} model checks agree with the installed Qiskit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
