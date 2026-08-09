"""Traversal of an in-memory circuit.

A flat instruction index cannot address an instruction inside a control flow
block: two blocks both start at index 0. Every visited instruction therefore
carries the full path it was reached by, and the qubit indices are remapped to
the outermost circuit so a finding names bits the user recognises.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from qxlint.diagnostics import InstructionStep


@dataclass(frozen=True, slots=True)
class VisitedInstruction:
    """One instruction, addressed by its path from the outermost circuit."""

    instruction: Any
    path: tuple[InstructionStep, ...]
    qubits: tuple[int, ...]
    clbits: tuple[int, ...]
    depth: int

    @property
    def name(self) -> str:
        return str(self.instruction.operation.name)


def bit_index_map(circuit: Any) -> dict[Any, int]:
    return {bit: index for index, bit in enumerate(circuit.qubits)}


def clbit_index_map(circuit: Any) -> dict[Any, int]:
    return {bit: index for index, bit in enumerate(circuit.clbits)}


def walk(
    circuit: Any, *, recurse: bool = True, max_depth: int = 12
) -> Iterator[VisitedInstruction]:
    """Yield every instruction, descending into control flow blocks."""
    yield from _walk(
        circuit,
        qubit_map=bit_index_map(circuit),
        clbit_map=clbit_index_map(circuit),
        prefix=(),
        depth=0,
        recurse=recurse,
        max_depth=max_depth,
    )


def _walk(
    circuit: Any,
    *,
    qubit_map: dict[Any, int],
    clbit_map: dict[Any, int],
    prefix: tuple[InstructionStep, ...],
    depth: int,
    recurse: bool,
    max_depth: int,
) -> Iterator[VisitedInstruction]:
    for index, instruction in enumerate(circuit.data):
        qubits = tuple(qubit_map.get(bit, -1) for bit in instruction.qubits)
        clbits = tuple(clbit_map.get(bit, -1) for bit in instruction.clbits)
        path = (*prefix, InstructionStep(index))
        yield VisitedInstruction(
            instruction=instruction,
            path=path,
            qubits=qubits,
            clbits=clbits,
            depth=depth,
        )

        if not recurse or depth >= max_depth or not _is_control_flow(instruction):
            continue

        operation = instruction.operation
        for block_number, block in enumerate(operation.blocks):
            inner_qubits = {
                inner: qubit_map.get(outer, -1)
                for outer, inner in zip(instruction.qubits, block.qubits, strict=False)
            }
            inner_clbits = {
                inner: clbit_map.get(outer, -1)
                for outer, inner in zip(instruction.clbits, block.clbits, strict=False)
            }
            yield from _walk(
                block,
                qubit_map=inner_qubits,
                clbit_map=inner_clbits,
                prefix=(*prefix, InstructionStep(index, block_number)),
                depth=depth + 1,
                recurse=recurse,
                max_depth=max_depth,
            )


def _is_control_flow(instruction: Any) -> bool:
    """Prefer the CircuitInstruction helper, fall back to the base class."""
    checker = getattr(instruction, "is_control_flow", None)
    if callable(checker):
        return bool(checker())
    from qiskit.circuit import ControlFlowOp

    return isinstance(instruction.operation, ControlFlowOp)


def circuit_name(circuit: Any) -> str:
    name = getattr(circuit, "name", None)
    return str(name) if name else "circuit"
