"""The Qiskit API model.

Every table here was checked against an installed Qiskit 2.5.2 and
qiskit-ibm-runtime 0.49.0 by introspection, not from documentation prose. The
tables are hardcoded on purpose: Engine A must analyse a project that targets a
different Qiskit version than the one the linter runs under, and must work with
no Qiskit installed at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from qxlint.semantics.objects import ObjectKind, Provenance, TriState
from qxlint.semantics.values import AbstractValue

QISKIT_CIRCUIT = "qiskit.QuantumCircuit"
TRANSPILE = "qiskit.transpile"
GENERATE_PRESET_PASS_MANAGER = "qiskit.transpiler.generate_preset_pass_manager"
MEASURE_OP = "qiskit.circuit.Measure"

# Import paths that name the same object. Resolution normalises to the right side.
SYMBOL_ALIASES: dict[str, str] = {
    "qiskit.circuit.QuantumCircuit": QISKIT_CIRCUIT,
    "qiskit.circuit.barrier.Barrier": "qiskit.circuit.Barrier",
    "qiskit.circuit.library.Barrier": "qiskit.circuit.Barrier",
    "qiskit.circuit.quantumcircuit.QuantumCircuit": QISKIT_CIRCUIT,
    "qiskit.compiler.transpile": TRANSPILE,
    "qiskit.compiler.transpiler.transpile": TRANSPILE,
    "qiskit.transpiler.preset_passmanagers.generate_preset_pass_manager": (
        GENERATE_PRESET_PASS_MANAGER
    ),
    "qiskit.transpiler.preset_passmanagers.generate_preset_pass_manager"
    ".generate_preset_pass_manager": GENERATE_PRESET_PASS_MANAGER,
    "qiskit.primitives.statevector_sampler.StatevectorSampler": (
        "qiskit.primitives.StatevectorSampler"
    ),
    "qiskit.primitives.statevector_estimator.StatevectorEstimator": (
        "qiskit.primitives.StatevectorEstimator"
    ),
    "qiskit.primitives.backend_sampler_v2.BackendSamplerV2": ("qiskit.primitives.BackendSamplerV2"),
    "qiskit.primitives.backend_estimator_v2.BackendEstimatorV2": (
        "qiskit.primitives.BackendEstimatorV2"
    ),
    # `qiskit_ibm_runtime.Sampler` is SamplerV2 here, verified with an identity
    # check, but only from 0.28. See VERSION_DEPENDENT_ALIASES below.
    # `qiskit_ibm_runtime.sampler.Sampler` is NOT: the submodule name is an empty
    # version 0 marker base class, so it is deliberately not aliased here.
    "qiskit_ibm_runtime.Sampler": "qiskit_ibm_runtime.SamplerV2",
    "qiskit_ibm_runtime.Estimator": "qiskit_ibm_runtime.EstimatorV2",
    "qiskit_ibm_runtime.sampler.SamplerV2": "qiskit_ibm_runtime.SamplerV2",
    "qiskit_ibm_runtime.estimator.EstimatorV2": "qiskit_ibm_runtime.EstimatorV2",
    "qiskit_ibm_runtime.qiskit_runtime_service.QiskitRuntimeService": (
        "qiskit_ibm_runtime.QiskitRuntimeService"
    ),
    # qiskit-ibm-runtime 0.49 exports the service under a second name. It is the
    # same class object, verified with an identity check, and it is exported from
    # the package only, not from the submodule.
    "qiskit_ibm_runtime.IBMQuantumComputeService": "qiskit_ibm_runtime.QiskitRuntimeService",
}


@dataclass(frozen=True, slots=True)
class ConstructorSpec:
    """What calling a symbol produces."""

    kind: ObjectKind
    measurement: TriState = TriState.UNKNOWN
    control_flow: TriState = TriState.UNKNOWN
    provenance: Provenance = Provenance.UNKNOWN


CONSTRUCTORS: dict[str, ConstructorSpec] = {
    QISKIT_CIRCUIT: ConstructorSpec(
        ObjectKind.CIRCUIT,
        measurement=TriState.DEFINITELY_ABSENT,
        control_flow=TriState.DEFINITELY_ABSENT,
    ),
    "qiskit.primitives.StatevectorSampler": ConstructorSpec(
        ObjectKind.SAMPLER_V2, provenance=Provenance.SAMPLER
    ),
    "qiskit.primitives.BackendSamplerV2": ConstructorSpec(
        ObjectKind.SAMPLER_V2, provenance=Provenance.SAMPLER
    ),
    "qiskit_ibm_runtime.SamplerV2": ConstructorSpec(
        ObjectKind.SAMPLER_V2, provenance=Provenance.SAMPLER
    ),
    "qiskit.primitives.StatevectorEstimator": ConstructorSpec(
        ObjectKind.ESTIMATOR_V2, provenance=Provenance.ESTIMATOR
    ),
    "qiskit.primitives.BackendEstimatorV2": ConstructorSpec(
        ObjectKind.ESTIMATOR_V2, provenance=Provenance.ESTIMATOR
    ),
    "qiskit_ibm_runtime.EstimatorV2": ConstructorSpec(
        ObjectKind.ESTIMATOR_V2, provenance=Provenance.ESTIMATOR
    ),
    "qiskit_ibm_runtime.QiskitRuntimeService": ConstructorSpec(ObjectKind.RUNTIME_SERVICE),
    "qiskit.primitives.SamplerResult": ConstructorSpec(
        ObjectKind.LEGACY_PRIMITIVE_RESULT_V1, provenance=Provenance.LEGACY
    ),
    "qiskit.primitives.EstimatorResult": ConstructorSpec(
        ObjectKind.LEGACY_PRIMITIVE_RESULT_V1, provenance=Provenance.LEGACY
    ),
    GENERATE_PRESET_PASS_MANAGER: ConstructorSpec(ObjectKind.OPAQUE),
}

# Circuits from qiskit.circuit.library. Without these every ansatz and feature
# map is an unknown object, so no rule can reach it: 11.8% of all circuit
# construction across a 113 repository corpus was invisible for that reason.
#
# Each entry was constructed and read on Qiskit 2.5.2 rather than assumed. All
# of them return a QuantumCircuit with no measure instruction and no control
# flow. scripts/verify_model.py rechecks that on every run, so an upstream
# change that starts adding a measurement is a failure rather than a silent
# false positive.
LIBRARY_CIRCUITS = (
    # Class forms.
    "EfficientSU2",
    "ExcitationPreserving",
    "FourierChecking",
    "GraphState",
    "GroverOperator",
    "HiddenLinearFunction",
    "IQP",
    "NLocal",
    "PauliFeatureMap",
    "PauliTwoDesign",
    "PhaseEstimation",
    "QAOAAnsatz",
    "QFT",
    "QuantumVolume",
    "RealAmplitudes",
    "TwoLocal",
    "UnitaryOverlap",
    "ZFeatureMap",
    "ZZFeatureMap",
    # Function forms, which are the supported spelling from Qiskit 2.x.
    "efficient_su2",
    "excitation_preserving",
    "grover_operator",
    "n_local",
    "pauli_feature_map",
    "pauli_two_design",
    "quantum_volume",
    "real_amplitudes",
    "z_feature_map",
    "zz_feature_map",
)

for _name in LIBRARY_CIRCUITS:
    CONSTRUCTORS[f"qiskit.circuit.library.{_name}"] = ConstructorSpec(
        ObjectKind.CIRCUIT,
        measurement=TriState.DEFINITELY_ABSENT,
        control_flow=TriState.DEFINITELY_ABSENT,
    )

# random_circuit takes measure=, conditional= and reset=, so what it contains
# depends on the call. Only the kind is asserted here: that is enough for the
# rules that need a circuit, and it cannot produce a wrong answer for the ones
# that need to know about measurements.
CONSTRUCTORS["qiskit.circuit.random.random_circuit"] = ConstructorSpec(ObjectKind.CIRCUIT)

# Symbols whose call returns a circuit carrying the input circuit's facts.
CIRCUIT_PRESERVING_FUNCTIONS = frozenset({TRANSPILE})

SAMPLER_KINDS = frozenset({ObjectKind.SAMPLER_V2})
ESTIMATOR_KINDS = frozenset({ObjectKind.ESTIMATOR_V2})

# QuantumCircuit methods that append operations without adding a measurement.
# Taken from the methods returning InstructionSet on QuantumCircuit 2.5.2, minus
# `measure`, and minus `append` which needs its operand inspected.
GATE_METHODS = frozenset(
    {
        "barrier",
        "break_loop",
        "ccx",
        "ccz",
        "ch",
        "continue_loop",
        "cp",
        "crx",
        "cry",
        "crz",
        "cs",
        "csdg",
        "cswap",
        "csx",
        "cu",
        "cx",
        "cy",
        "cz",
        "dcx",
        "delay",
        "ecr",
        "h",
        "id",
        "initialize",
        "iswap",
        "mcp",
        "mcrx",
        "mcry",
        "mcrz",
        "mcx",
        "ms",
        "noop",
        "p",
        "pauli",
        "prepare_state",
        "r",
        "rcccx",
        "rccx",
        "reset",
        "rv",
        "rx",
        "rxx",
        "ry",
        "ryy",
        "rz",
        "rzx",
        "rzz",
        "s",
        "sdg",
        "store",
        "swap",
        "sx",
        "sxdg",
        "t",
        "tdg",
        "u",
        "unitary",
        "x",
        "y",
        "z",
    }
)

# QuantumCircuit methods that add measurements.
MEASURING_METHODS = frozenset({"measure", "measure_all", "measure_active"})

# Context manager builders that add a control flow operation.
CONTROL_FLOW_BUILDERS = frozenset({"if_test", "if_else", "for_loop", "while_loop", "switch", "box"})

# Classical register created by each measurement helper, verified by running it.
MEASURE_ALL_REGISTER = "meas"
MEASURE_ACTIVE_REGISTER = "meas"

# Read only circuit methods and properties. They never change a tracked fact.
CIRCUIT_READ_METHODS = frozenset(
    {
        "count_ops",
        "depth",
        "draw",
        "find_bit",
        "get_instructions",
        "has_control_flow_op",
        "has_parameter",
        "has_register",
        "has_var",
        "num_connected_components",
        "num_nonlocal_gates",
        "num_tensor_factors",
        "num_unitary_factors",
        "qasm",
        "size",
        "width",
    }
)

# Methods returning a fresh circuit rather than mutating the receiver.
CIRCUIT_DERIVING_METHODS = frozenset(
    {
        "copy",
        "copy_empty_like",
        "decompose",
        "inverse",
        "power",
        "repeat",
        "reverse_bits",
        "reverse_ops",
        "assign_parameters",
    }
)

# Deriving methods that keep the instruction order, so a measurement that was
# last stays last. Verified on Qiskit 2.5.2: reverse_ops, repeat, power and
# inverse all move or wrap it, so they are deliberately absent.
ORDER_PRESERVING_DERIVING_METHODS = frozenset(
    {"copy", "decompose", "assign_parameters", "reverse_bits"}
)

# Positional index of `inplace`, read from the signatures on Qiskit 2.5.2.
# `qc.measure_all(False)` passes it by position, which a keyword lookup misses.
INPLACE_POSITION: dict[str, int] = {
    "measure_all": 0,
    "measure_active": 0,
    "remove_final_measurements": 0,
    "assign_parameters": 1,
    "tensor": 1,
    "compose": 4,
}


def inplace_argument(
    method: str,
    args: tuple[AbstractValue, ...],
    kwargs: dict[str, AbstractValue],
    complete: bool = True,
) -> AbstractValue | None:
    """The `inplace` argument, passed either way. None when it was not passed.

    A dropped argument shifts every later one left, so positions are read only
    when the tuple is known to be whole.
    """
    if "inplace" in kwargs:
        return kwargs["inplace"]
    if not complete:
        return None
    index = INPLACE_POSITION.get(method)
    if index is not None and index < len(args):
        return args[index]
    return None


# `remove_final_measurements` strips trailing barriers along with the
# measurements, so a barrier leaves a measurement final. Verified on Qiskit
# 2.5.2: a delay does not, and neither does any other gate.
FINALITY_TRANSPARENT_METHODS = frozenset({"barrier"})
FINALITY_TRANSPARENT_OPERATIONS = frozenset(
    {"qiskit.circuit.Barrier", "qiskit.circuit.library.Barrier"}
)


# Standard operation classes that never introduce a measurement, used to keep
# `QuantumCircuit.append` from destroying facts for ordinary gate appends.
NON_MEASURING_OPERATIONS = frozenset(
    {
        "qiskit.circuit.Barrier",
        "qiskit.circuit.Delay",
        "qiskit.circuit.Reset",
        "qiskit.circuit.Store",
        "qiskit.circuit.library.Barrier",
    }
) | frozenset(
    f"qiskit.circuit.library.{name}"
    for name in (
        "CCXGate",
        "CCZGate",
        "CHGate",
        "CPhaseGate",
        "CRXGate",
        "CRYGate",
        "CRZGate",
        "CSGate",
        "CSXGate",
        "CSdgGate",
        "CSwapGate",
        "CUGate",
        "CU1Gate",
        "CU3Gate",
        "CXGate",
        "CYGate",
        "CZGate",
        "DCXGate",
        "ECRGate",
        "GlobalPhaseGate",
        "HGate",
        "IGate",
        "PhaseGate",
        "RGate",
        "RXGate",
        "RXXGate",
        "RYGate",
        "RYYGate",
        "RZGate",
        "RZXGate",
        "RZZGate",
        "SGate",
        "SXGate",
        "SXdgGate",
        "SdgGate",
        "SwapGate",
        "TGate",
        "TdgGate",
        "UGate",
        "U1Gate",
        "U2Gate",
        "U3Gate",
        "XGate",
        "XXMinusYYGate",
        "XXPlusYYGate",
        "YGate",
        "ZGate",
        "iSwapGate",
    )
)

MEASURING_OPERATIONS = frozenset({MEASURE_OP, "qiskit.circuit.measure.Measure"})

# Gates that are exactly their own inverse. Every entry was verified by squaring
# the operator matrix and comparing with the identity, not inferred from the
# class name. iSwap, S, T, SX and DCX are deliberately absent: they are not.
SELF_INVERSE_GATES: dict[str, str] = {
    "x": "XGate",
    "y": "YGate",
    "z": "ZGate",
    "h": "HGate",
    "id": "IGate",
    "cx": "CXGate",
    "cy": "CYGate",
    "cz": "CZGate",
    "ch": "CHGate",
    "swap": "SwapGate",
    "ccx": "CCXGate",
    "ccz": "CCZGate",
    "cswap": "CSwapGate",
    "ecr": "ECRGate",
    "rccx": "RCCXGate",
}


# The bare names were the V1 classes until 0.28, the release that removed V1 and
# rebound them. Read from the published wheels rather than from a release note:
# 0.27.1 imports `SamplerV1 as Sampler`, 0.28.0 imports `SamplerV2 as Sampler`.
BARE_RUNTIME_PRIMITIVES_BECAME_V2 = "0.28"

# Resolving to the V1 spelling rather than leaving the name alone is what makes
# the decision stick: every later lookup sees a name no table claims is V2.
VERSION_DEPENDENT_ALIASES: dict[str, str] = {
    "qiskit_ibm_runtime.Sampler": "qiskit_ibm_runtime.SamplerV1",
    "qiskit_ibm_runtime.Estimator": "qiskit_ibm_runtime.EstimatorV1",
}


def canonical(qualified_name: str, *, bare_runtime_is_v2: bool = True) -> str:
    """Normalise an import path to the public path the tables use.

    ``bare_runtime_is_v2`` is false only when the target version is proven to
    predate 0.28, where these two names are the V1 classes and none of the V2
    rules apply to them.
    """
    if not bare_runtime_is_v2:
        legacy = VERSION_DEPENDENT_ALIASES.get(qualified_name)
        if legacy is not None:
            return legacy
    return SYMBOL_ALIASES.get(qualified_name, qualified_name)


def constructor_for(qualified_name: str) -> ConstructorSpec | None:
    return CONSTRUCTORS.get(canonical(qualified_name))


def is_primitive_kind(kind: ObjectKind) -> bool:
    return kind in SAMPLER_KINDS or kind in ESTIMATOR_KINDS


def provenance_for(kind: ObjectKind) -> Provenance:
    if kind in SAMPLER_KINDS:
        return Provenance.SAMPLER
    if kind in ESTIMATOR_KINDS:
        return Provenance.ESTIMATOR
    return Provenance.UNKNOWN
