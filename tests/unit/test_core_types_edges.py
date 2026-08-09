"""Edges of the core types: the lattice, the state, locations and Engine B dispatch.

Everything here is a corner a normal run does not reach: a repr, a depth limit, a
path that is already dead, a file that cannot be read, a stream that raises.
"""

from __future__ import annotations

import ast
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import qxlint
from qxlint.circuit.walker import walk
from qxlint.config import Config
from qxlint.diagnostics import (
    CircuitLocation,
    Finding,
    InstructionStep,
    NotebookLocation,
    SourceLocation,
    location_path,
)
from qxlint.engine import analyse_path, discover, parse_module
from qxlint.noqa import ALL, _split_codes
from qxlint.notebook import (
    BARRIER_CALL,
    NotebookError,
    parse_cell,
    parse_notebook,
    prepare_cell_source,
    read_notebook,
)
from qxlint.output.palette import ACCENT, Depth, detect_depth, foreground
from qxlint.paths import exists_but_is_not_regular
from qxlint.profile import SemanticProfile
from qxlint.registry import tiers
from qxlint.semantics.model import is_primitive_kind, provenance_for
from qxlint.semantics.objects import (
    Escape,
    ObjectFacts,
    ObjectKind,
    ObjectStore,
    Provenance,
    TriState,
)
from qxlint.semantics.state import State, merge_states
from qxlint.semantics.values import (
    NONE,
    UNBOUND,
    UNKNOWN,
    AbstractValue,
    ConstInt,
    ImportedSymbol,
    ObjectRef,
    Sequence,
    Union,
    iter_options,
    join,
    object_refs,
)
from qxlint.source import SourceFile

# The abstract value lattice -------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (UNKNOWN, "Unknown"),
        (UNBOUND, "Unbound"),
        (NONE, "None"),
        (ObjectRef(7), "Obj(7)"),
        (ImportedSymbol("qiskit.QuantumCircuit"), "Sym(qiskit.QuantumCircuit)"),
        (Sequence(None), "Seq[?]"),
        (Sequence((ObjectRef(1), NONE)), "Seq[Obj(1), None]"),
    ],
)
def test_an_abstract_value_reprs_as_its_lattice_notation(
    value: AbstractValue, expected: str
) -> None:
    assert repr(value) == expected


def test_a_union_repr_sorts_its_options_so_two_runs_agree() -> None:
    value = Union(frozenset({ConstInt(2), ObjectRef(1), UNBOUND}))
    assert repr(value) == "Union{ConstInt(value=2), Obj(1), Unbound}"


def test_joining_with_a_sequence_of_unknown_contents_forgets_the_contents() -> None:
    merged = join(Sequence(None, local=False), Sequence((ObjectRef(1),)))
    assert isinstance(merged, Sequence)
    assert merged.elements is None
    # A container handed to unmodelled code on one path is no longer local.
    assert merged.local is False


def test_iter_options_flattens_a_union_and_wraps_everything_else() -> None:
    assert set(iter_options(Union(frozenset({ConstInt(1), ConstInt(2)})))) == {
        ConstInt(1),
        ConstInt(2),
    }
    assert iter_options(ObjectRef(3)) == (ObjectRef(3),)


def nested_sequence(depth: int) -> AbstractValue:
    value: AbstractValue = ObjectRef(1)
    for _ in range(depth):
        value = Sequence((value,))
    return value


def test_object_refs_stops_descending_past_the_depth_limit() -> None:
    # The walk is bounded, so a deeply buried reference is simply not reported
    # rather than costing an unbounded recursion.
    assert object_refs(nested_sequence(6)) == (ObjectRef(1),)
    assert object_refs(nested_sequence(8)) == ()


# Abstract state -------------------------------------------------------------


def test_unbinding_a_name_leaves_it_unbound_rather_than_absent() -> None:
    state = State()
    state.bind("qc", ObjectRef(1))
    state.unbind("qc")
    assert state.lookup("qc") is UNBOUND
    assert "qc" in state.env


def test_an_unreachable_path_contributes_nothing_to_a_merge() -> None:
    live = State()
    live.bind("qc", ObjectRef(1))
    dead = State(reachable=False)
    dead.bind("qc", ObjectRef(2))
    live.merge_from(dead)
    assert live.lookup("qc") == ObjectRef(1)


def test_merging_into_an_unreachable_path_adopts_the_other_path_whole() -> None:
    dead = State(reachable=False)
    live = State()
    live.bind("qc", ObjectRef(1))
    object_id = live.store.allocate(ObjectFacts(ObjectKind.CIRCUIT))
    dead.merge_from(live)
    assert dead.reachable is True
    assert dead.lookup("qc") == ObjectRef(1)
    assert dead.store.ids() == frozenset({object_id})


def test_merging_only_dead_paths_keeps_the_store_but_stays_dead() -> None:
    dead = State(reachable=False)
    object_id = dead.store.allocate(ObjectFacts(ObjectKind.CIRCUIT))
    merged = merge_states([dead, State(reachable=False)])
    assert merged.reachable is False
    assert merged.store.ids() == frozenset({object_id})


def test_merging_no_paths_at_all_yields_an_empty_dead_state() -> None:
    merged = merge_states([])
    assert merged.reachable is False
    assert merged.env == {}
    assert merged.store.ids() == frozenset()


# Object facts and the store -------------------------------------------------


def test_an_escaped_object_reads_its_control_flow_fact_as_unknown() -> None:
    facts = ObjectFacts(
        ObjectKind.CIRCUIT,
        control_flow=TriState.DEFINITELY_PRESENT,
        escape=Escape.ESCAPED,
    )
    assert facts.control_flow is TriState.DEFINITELY_PRESENT
    assert facts.read_control_flow() is TriState.UNKNOWN


def test_setting_facts_replaces_them_and_the_id_stays_listed() -> None:
    store = ObjectStore()
    object_id = store.allocate(
        ObjectFacts(ObjectKind.CIRCUIT, measurement=TriState.DEFINITELY_ABSENT)
    )
    store.set(object_id, ObjectFacts(ObjectKind.BIT_ARRAY))
    facts = store.get(object_id)
    assert facts is not None
    assert facts.kind is ObjectKind.BIT_ARRAY
    assert facts.measurement is TriState.UNKNOWN
    assert store.ids() == frozenset({object_id})


@pytest.mark.parametrize(
    ("kind", "primitive", "provenance"),
    [
        (ObjectKind.SAMPLER_V2, True, Provenance.SAMPLER),
        (ObjectKind.ESTIMATOR_V2, True, Provenance.ESTIMATOR),
        (ObjectKind.CIRCUIT, False, Provenance.UNKNOWN),
        (ObjectKind.LEGACY_SAMPLER_V1, False, Provenance.UNKNOWN),
    ],
)
def test_only_the_v2_primitive_kinds_are_primitives_and_carry_a_provenance(
    kind: ObjectKind, primitive: bool, provenance: Provenance
) -> None:
    assert is_primitive_kind(kind) is primitive
    assert provenance_for(kind) is provenance


# Source files and locations -------------------------------------------------


def test_a_line_beyond_the_text_has_no_text_and_starts_at_column_one() -> None:
    source = SourceFile("t.py", "x = 1\n")
    assert source.line_text(9) == ""
    assert source.column_of(9, 4) == 1


def test_a_notebook_cell_location_carries_the_cell_index_and_the_physical_line() -> None:
    source = SourceFile(
        path="n.ipynb",
        text="x = 1\ny = 2\n",
        cell_index=2,
        physical_line_of=(17, 18),
    )
    location = source.location(ast.parse(source.text).body[1])
    assert isinstance(location, NotebookLocation)
    assert (location.cell_index, location.line, location.physical_line) == (2, 2, 18)
    assert location.render() == "n.ipynb:cell2:2:1"


def test_a_physical_line_outside_the_recorded_map_is_unknown() -> None:
    source = SourceFile("n.ipynb", "x = 1\n", cell_index=1, physical_line_of=(4,))
    assert source.physical_line(1) == 4
    assert source.physical_line(2) is None
    assert source.physical_line(0) is None


def test_render_text_is_the_location_then_the_rule_then_the_message() -> None:
    finding = Finding(
        rule="QXL101", message="wrong receiver", location=SourceLocation("a.py", 3, 5)
    )
    assert finding.render_text() == "a.py:3:5: QXL101 wrong receiver"


def test_location_path_is_the_file_for_engine_a_and_nothing_for_engine_b() -> None:
    assert location_path(SourceLocation("a.py", 1, 1)) == "a.py"
    assert location_path(NotebookLocation("n.ipynb", 1, 1, 1)) == "n.ipynb"
    assert location_path(CircuitLocation("qc", (InstructionStep(0),))) is None


def test_engine_a_findings_sort_before_engine_b_findings() -> None:
    from_file = Finding(rule="QXL999", message="m", location=SourceLocation("z.py", 9, 9))
    from_circuit = Finding(
        rule="QXL301", message="m", location=CircuitLocation("qc", (InstructionStep(0),))
    )
    assert sorted([from_circuit, from_file], key=Finding.sort_key) == [from_file, from_circuit]


# Suppression comments -------------------------------------------------------


def test_a_blank_code_list_falls_back_to_suppressing_every_rule() -> None:
    # The comment regex never yields a blank list of codes, so this guard has no
    # public path and is exercised directly.
    assert _split_codes(None) == frozenset({ALL})
    assert _split_codes("   ") == frozenset({ALL})


# Parser stack overflow -------------------------------------------------------


def test_a_module_too_deep_to_parse_becomes_a_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 40 KB chain of `+` really does raise here on 3.11 to 3.13 and parse
    # fine on 3.14, so the interpreter is driven directly rather than through a
    # depth that only overflows on some versions.
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(ast, "parse", boom)
    with pytest.raises(SyntaxError, match="nests too deeply") as caught:
        parse_module("x = 1\n", "deep.py")
    assert caught.value.filename == "deep.py"
    assert caught.value.lineno == 1
    assert caught.value.offset == 1


def test_a_cell_too_deep_to_parse_becomes_a_syntax_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real = builtins.compile

    def boom(*args: object, **kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(builtins, "compile", boom)
    with pytest.raises(SyntaxError, match="nests too deeply"):
        parse_cell("x = 1\n", "deep.ipynb")
    monkeypatch.setattr(builtins, "compile", real)


def test_a_file_too_deep_to_parse_does_not_end_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The point of the fix: one unreadable file is a finding, and the other
    # files in the tree are still analysed.
    (tmp_path / "deep.py").write_text("t = 1\n")
    (tmp_path / "good.py").write_text(
        "from qiskit import QuantumCircuit\n"
        "from qiskit.primitives import StatevectorSampler\n"
        "qc = QuantumCircuit(2)\n"
        "qc.h(0)\n"
        "StatevectorSampler().run([qc])\n"
    )
    real = ast.parse

    def only_deep_overflows(source: str, **kwargs: object) -> object:
        if source.startswith("t = "):
            raise RecursionError("maximum recursion depth exceeded")
        return real(source, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ast, "parse", only_deep_overflows)
    config = Config()
    findings = [
        finding
        for path in discover([tmp_path], config)
        for finding in analyse_path(
            path,
            config=config,
            profile=SemanticProfile(),
            enabled=frozenset(tiers()),
            display_path=path.name,
        )
    ]
    assert sorted((f.location.path, f.rule) for f in findings) == [  # type: ignore[union-attr]
        ("deep.py", "QXL000"),
        ("good.py", "QXL103"),
    ]


# Paths that are not files ----------------------------------------------------


@pytest.mark.parametrize("name", ["pipe.py", "pipe.ipynb"])
def test_a_named_pipe_is_recognised_without_opening_it(tmp_path: Path, name: str) -> None:
    # stat does not block on a FIFO; open does, forever, with no timeout. The
    # predicate is checked here rather than by running the analyser on a real
    # pipe, because a regression there would hang the test run instead of
    # failing it. The end to end case is
    # test_a_named_pipe_does_not_hang_the_run, which uses a subprocess.
    path = tmp_path / name
    os.mkfifo(path)
    assert exists_but_is_not_regular(path) is True


def test_a_directory_named_like_a_module_is_not_read_as_source(tmp_path: Path) -> None:
    path = tmp_path / "package.py"
    path.mkdir()
    findings = analyse_path(
        path,
        config=Config(),
        profile=SemanticProfile(),
        enabled=frozenset(tiers()),
        display_path="package.py",
    )
    assert [f.message for f in findings] == ["not a regular file"]


def test_a_broken_symlink_still_reports_the_real_error(tmp_path: Path) -> None:
    # stat fails here, so the reason is left to the reader and the errno
    # reaches the message instead of a flat "not a regular file".
    path = tmp_path / "broken.py"
    path.symlink_to(tmp_path / "missing.py")
    findings = analyse_path(
        path,
        config=Config(),
        profile=SemanticProfile(),
        enabled=frozenset(tiers()),
        display_path="broken.py",
    )
    assert [f.rule for f in findings] == ["QXL000"]
    assert "cannot read file" in findings[0].message


# Notebook reading and cell preparation --------------------------------------


def test_a_notebook_that_cannot_be_read_raises_a_notebook_error(tmp_path: Path) -> None:
    with pytest.raises(NotebookError, match="cannot read notebook"):
        read_notebook(tmp_path)


def test_a_notebook_that_is_not_utf8_raises_a_notebook_error(tmp_path: Path) -> None:
    # Found on real code: an em dash written as cp1252 0x97, which is what a
    # Windows editor produces. nbformat rejects it too, so QXL000 is the right
    # answer; what must not happen is the whole run ending.
    document = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path = tmp_path / "cp1252.ipynb"
    path.write_bytes(json.dumps(document | {"t": "a — b"}, ensure_ascii=False).encode("cp1252"))
    with pytest.raises(NotebookError, match="not valid UTF-8"):
        read_notebook(path)


def test_a_notebook_nested_too_deeply_raises_a_notebook_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # json.loads recurses per level, so a deep document raises RecursionError
    # rather than JSONDecodeError. The depth where that starts is an interpreter
    # detail and moves between versions: measured on this project's four
    # supported interpreters, json.loads raises at 2,000 levels on 3.11, at
    # 20,000 on 3.12 and 3.13, and only at 100,000 on 3.14. The handler is what
    # matters, so it is driven directly instead of through a depth that would
    # have to be retuned for every new release.
    path = tmp_path / "deep.ipynb"
    path.write_text('{"cells": []}')

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(json, "loads", boom)
    with pytest.raises(NotebookError, match="nests too deeply"):
        read_notebook(path)


def test_a_cell_source_that_is_neither_text_nor_lines_becomes_an_empty_cell() -> None:
    document = {
        "cells": [
            {"cell_type": "code", "source": 42},
            {"cell_type": "code", "source": ["a = 1\n", 7, "b = 2\n"]},
        ]
    }
    cells = parse_notebook("n.ipynb", document).cells
    assert [cell.original for cell in cells] == ["", "a = 1\nb = 2\n"]


def test_a_cell_made_only_of_a_non_breaking_space_is_left_alone() -> None:
    # U+00A0 is whitespace to `str.strip` but not to the Python tokenizer, so
    # there is no shared indent to strip and no magic to rewrite.
    text, transformed = prepare_cell_source("\xa0")
    assert text == "\xa0"
    assert transformed is False


def test_a_blank_first_line_does_not_hide_a_magic_further_down() -> None:
    text, transformed = prepare_cell_source("\n%run setup.py\nuse(qc)\n")
    assert transformed is True
    assert text.splitlines() == ["", BARRIER_CALL, "use(qc)"]
    parse_cell(text)


def test_a_cell_magic_below_the_first_line_becomes_a_barrier() -> None:
    text, transformed = prepare_cell_source("x = 1\n%%time\ny = 2\n")
    assert transformed is True
    assert text.splitlines() == ["x = 1", BARRIER_CALL, "y = 2"]
    parse_cell(text)


# Engine A file handling -----------------------------------------------------


def notebook(*cells: str) -> str:
    document = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "code", "metadata": {}, "source": source, "outputs": []}
            for source in cells
        ],
    }
    return json.dumps(document)


def analyse(path: Path, config: Config) -> list[Finding]:
    return analyse_path(
        path,
        config=config,
        profile=SemanticProfile(),
        enabled=config.enabled_codes(tiers()),
    )


def test_a_file_that_cannot_be_read_is_reported_as_unparsable(tmp_path: Path) -> None:
    findings = analyse(tmp_path / "missing.py", Config())
    assert [f.rule for f in findings] == ["QXL000"]
    assert "cannot read file" in findings[0].message


def test_a_cell_that_fails_to_parse_invalidates_the_bindings_before_it(tmp_path: Path) -> None:
    path = tmp_path / "n.ipynb"
    path.write_text(
        notebook(
            "from qiskit import QuantumCircuit\n"
            "from qiskit.primitives import StatevectorSampler\n"
            "qc = QuantumCircuit(2)\n",
            "def broken(\n",
            "StatevectorSampler().run([qc])\n",
        ),
        encoding="utf-8",
    )
    # Without the broken cell `qc` is provably unmeasured and QXL103 fires; the
    # cell may have done anything, so afterwards nothing is known.
    assert [f.rule for f in analyse(path, Config())] == ["QXL000"]


def test_a_per_file_ignore_drops_even_the_unparsable_finding(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def f(\n", encoding="utf-8")
    assert [f.rule for f in analyse(path, Config())] == ["QXL000"]
    assert analyse(path, Config(per_file_ignores=(("*.py", ("QXL000",)),))) == []


def test_discover_lists_each_file_once_when_a_directory_is_repeated(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.ipynb").write_text("{}", encoding="utf-8")
    assert discover([tmp_path, tmp_path], Config()) == [tmp_path / "a.py", tmp_path / "b.ipynb"]


# Palette --------------------------------------------------------------------


@pytest.fixture
def plain_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NO_COLOR", "FORCE_COLOR", "COLORTERM", "TERM"):
        monkeypatch.delenv(name, raising=False)


def test_a_stream_whose_isatty_raises_is_not_a_terminal(plain_environment: None) -> None:
    stream = io.StringIO()
    stream.close()
    assert detect_depth(stream) is Depth.NONE


def test_a_256_colour_terminal_gets_the_nearest_cube_index() -> None:
    assert foreground(ACCENT, Depth.ANSI256) == "\033[38;5;104m"


# Engine B dispatch ----------------------------------------------------------


class StubTarget:
    """The duck typed surface QXL301 uses: a qubit count and a support query."""

    def __init__(self, num_qubits: int, supported: frozenset[str]) -> None:
        self.num_qubits = num_qubits
        self._supported = supported

    def instruction_supported(self, name: str, qargs: tuple[int, ...]) -> bool:
        return name in self._supported


@pytest.mark.requires_qiskit
def test_check_circuit_runs_the_target_rule_when_a_target_is_given(
    qiskit_installed: bool,
) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    findings = qxlint.check_circuit(qc, target=StubTarget(5, frozenset({"cx"})))
    assert [f.rule for f in findings] == ["QXL301"]
    assert "'h'" in findings[0].message


@pytest.mark.requires_qiskit
@pytest.mark.parametrize("bad", ["not a target", None, 42, object()])
def test_check_target_rejects_a_target_that_is_not_one(qiskit_installed: bool, bad: object) -> None:
    # An empty circuit never asks the target anything, so a wrong target used to
    # produce an empty list, which reads as "compatible".
    from qiskit import QuantumCircuit

    with pytest.raises(TypeError, match="must be a qiskit Target"):
        qxlint.check_target(QuantumCircuit(1), bad)


@pytest.mark.requires_qiskit
@pytest.mark.parametrize("bad", ["not a target", 42, object()])
def test_check_circuit_rejects_a_target_that_is_not_one(
    qiskit_installed: bool, bad: object
) -> None:
    from qiskit import QuantumCircuit

    with pytest.raises(TypeError, match="must be a qiskit Target"):
        qxlint.check_circuit(QuantumCircuit(1), target=bad)


@pytest.mark.requires_qiskit
def test_check_circuit_with_target_none_means_no_target_rule(qiskit_installed: bool) -> None:
    # None is the documented "no target", not a bad target.
    from qiskit import QuantumCircuit

    assert qxlint.check_circuit(QuantumCircuit(1), target=None) == []


@pytest.mark.requires_qiskit
def test_an_instruction_on_an_unmapped_qubit_is_skipped_rather_than_misreported(
    qiskit_installed: bool,
) -> None:
    # A stub, because a real QuantumCircuit cannot hold a bit it does not own.
    # It also has no `is_control_flow` helper, so the walker falls back to the
    # ControlFlowOp base class check.
    instruction = SimpleNamespace(
        operation=SimpleNamespace(name="h"), qubits=(object(),), clbits=()
    )
    circuit = SimpleNamespace(name="stub", num_qubits=1, qubits=(), clbits=(), data=(instruction,))
    assert [visited.qubits for visited in walk(circuit)] == [(-1,)]
    assert qxlint.check_target(circuit, StubTarget(5, frozenset())) == []


@pytest.mark.requires_qiskit
def test_a_parameterised_operation_borrowing_a_gate_name_never_cancels(
    qiskit_installed: bool,
) -> None:
    from qiskit.circuit import Gate, QuantumCircuit

    custom = Gate(name="x", num_qubits=1, params=[0.5])
    qc = QuantumCircuit(1)
    qc.append(custom, [0])
    qc.append(custom, [0])
    assert [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL302"] == []


@pytest.mark.requires_qiskit
@pytest.mark.parametrize(("method", "args"), [("barrier", (1,)), ("delay", (100, 1)), ("id", (1,))])
def test_a_qubit_touched_only_by_an_ignored_operation_is_still_unused(
    qiskit_installed: bool, method: str, args: tuple[int, ...]
) -> None:
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    getattr(qc, method)(*args)
    findings = [f for f in qxlint.check_circuit(qc, preview=True) if f.rule == "QXL303"]
    assert [f.location.qubits for f in findings] == [(1,)]
