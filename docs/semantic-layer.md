# The semantic layer

The rules worth having cannot be local AST pattern matches. `get_counts()` is
correct on a `BitArray` and an `AttributeError` on a `DataBin`, and the two look
identical in the syntax tree. The question is never "does this call appear" but
"what is this object, and what do I know about it".

qxlint answers that with a small abstract interpreter over the module. This page
is the contract: two implementations that both follow it should agree on every
example here.

## 1. Values and objects are separate

A name does **not** carry facts. It binds to an abstract value, and a mutable
object's facts live in a separate store under a stable identity.

```
Environment:  name      -> AbstractValue
ObjectStore:  ObjectId  -> ObjectFacts
```

This is what makes aliasing work. Given

```python
qc = QuantumCircuit(1)
alias = qc
alias.measure_all()
```

the environment holds `qc -> Obj(42)` and `alias -> Obj(42)`, and the mutation
updates `ObjectStore[42]`. Both names see it. If facts hung off names instead,
`qc` would still look unmeasured and QXL103 would fire on correct code.

Rebinding changes the environment, not the object:

```python
alias = QuantumCircuit(2)     # alias -> Obj(43), qc still -> Obj(42)
```

### The value lattice

```
Unbound                                   the name is not bound on this path
ObjectRef(id)                             a mutable object identity
ImportedSymbol(qualified_name)            a module level name, before it is called
ConstStr / ConstInt / ConstBool / None    literals, needed for keyword checks
Sequence(elements, local, token)          a list or tuple
Union({...})                              alternatives a join could not reconcile
Unknown                                   top, absorbs everything
```

`Unbound` is the bottom, and a join **absorbs** it. Using an unbound name raises
NameError, so any execution that reaches a use of the name took the branch that
bound it, and that value is what the use sees. This is what makes the ordinary
conditional import readable:

```python
try:
    from qiskit_ibm_runtime import QiskitRuntimeService
except ImportError:
    pass
QiskitRuntimeService(channel="ibm_quantum")   # QXL201 fires
```

An except branch that **rebinds** the name is a different case and still joins
to a `Union`, because there the name is bound on both paths and one of them is
not something a rule can reason about:

```python
try:
    from qiskit_ibm_runtime import QiskitRuntimeService
except ImportError:
    QiskitRuntimeService = None
QiskitRuntimeService(channel="ibm_quantum")   # silent
```

The same rule covers a name bound in only one branch of an `if`, which is how
the absorption pays for itself outside imports.

`ImportedSymbol` and `ObjectRef` are deliberately distinct. `QuantumCircuit` the
class and `qc` the instance are different things, and collapsing them makes it
impossible to say what `StatevectorSampler` is before it is called.

`Union` exists so that a branch that produces two different kinds does not have
to be rounded to `Unknown`. That matters here:

```python
if condition:
    result = sampler.run([qc]).result()      # PRIMITIVE_RESULT_V2
else:
    result = backend.run(qc).result()        # LEGACY_RESULT
result.get_counts()                          # QXL101 must stay silent
```

Rounding to `Unknown` would also be silent, but it would lose the information for
every future rule. Picking one branch would be a false positive.

`join` is the least upper bound: equal values collapse, `Unknown` absorbs,
sequences merge elementwise, and a union wider than eight alternatives becomes
`Unknown` so the analysis terminates.

### Object kinds

Kinds are what rules match on, never variable names.

```
CIRCUIT              SAMPLER_V2                ESTIMATOR_V2
PRIMITIVE_JOB_V2     PRIMITIVE_RESULT_V2       PUB_RESULT_V2
SAMPLER_PUB_RESULT_V2  ESTIMATOR_PUB_RESULT_V2 DATA_BIN
BIT_ARRAY            NDARRAY                   OBSERVABLE / TARGET
LEGACY_SAMPLER_V1    LEGACY_PRIMITIVE_RESULT_V1
LEGACY_BACKEND       LEGACY_JOB                LEGACY_RESULT
RUNTIME_SERVICE      OPAQUE
```

Sampler and Estimator pub results are separate kinds because their data bins
hold different things. Verified against Qiskit 2.5.2: a Sampler pub result's
data bin has one field per classical register holding a `BitArray`, while a
`StatevectorEstimator` pub result's data bin holds `evs` and `stds`.

## 2. How QXL101 separates a DataBin from a BitArray

The chain is modelled explicitly, one hop at a time.

| Expression | Kind after the hop |
| --- | --- |
| `StatevectorSampler()` | `SAMPLER_V2`, provenance `SAMPLER` |
| `.run([qc])` | `PRIMITIVE_JOB_V2`, provenance carried |
| `.result()` | `PRIMITIVE_RESULT_V2` |
| `[0]` | `SAMPLER_PUB_RESULT_V2` (or `PUB_RESULT_V2` for an Estimator) |
| `.data` | `DATA_BIN`, provenance and register names carried |
| `.meas` | `BIT_ARRAY` **only if** provenance is Sampler and `meas` is a proven register, otherwise `Unknown` |
| `.get_counts()` | fires on the first five, never on `BIT_ARRAY` or `Unknown` |

The last row is the important one. `DataBin` field types are primitive and
implementation specific, so an attribute whose type cannot be proven yields
`Unknown` and nothing can fire on it. Register names are learned from the
circuit that entered `run()`: `QuantumCircuit(2, 2)` gives `c`, `measure_all()`
and `measure_active()` give `meas`, all verified by running Qiskit.

`join_data()` is modelled as `Union(BIT_ARRAY, NDARRAY)` because its documented
return type is `BitArray | np.ndarray`. A union is not definite, so
`result[0].join_data().get_counts()` is silent, which is the correct answer.

## 3. Circuit facts

For an object of kind `CIRCUIT`:

```
MeasurementState:  DEFINITELY_ABSENT | DEFINITELY_PRESENT | MAYBE_PRESENT | UNKNOWN
ControlFlowState:  DEFINITELY_ABSENT | DEFINITELY_PRESENT | MAYBE_PRESENT | UNKNOWN
Escape:            LOCAL | ESCAPED
Provenance:        SAMPLER | ESTIMATOR | LEGACY | UNKNOWN
Registers:         set of known classical register names, or unknown
```

Branch join for a tri-state fact:

| left | right | result |
| --- | --- | --- |
| ABSENT | ABSENT | ABSENT |
| PRESENT | PRESENT | PRESENT |
| ABSENT | PRESENT | MAYBE_PRESENT |
| MAYBE | anything except UNKNOWN | MAYBE_PRESENT |
| UNKNOWN | anything | UNKNOWN |

**Rules fire only on a definite value.** Never on `MAYBE_PRESENT`, never on
`UNKNOWN`. An escaped object reads as `UNKNOWN` regardless of what is stored.

### Modelled circuit mutations

Anything not in this table pushes measurement and control flow to `UNKNOWN`
while keeping the kind.

| Method | Effect |
| --- | --- |
| `measure`, `measure_all`, `measure_active` | measurement `PRESENT`; the latter two add register `meas` |
| `measure_all(inplace=False)` | returns a **new** measured circuit, receiver unchanged |
| `remove_final_measurements` | measurement `ABSENT` (or a new circuit with `inplace=False`) |
| `clear` | measurement and control flow `ABSENT` |
| `copy`, `decompose`, `inverse`, `assign_parameters`, ... | new object, facts carried |
| `copy_empty_like` | new object, both `ABSENT` |
| `compose`, `tensor` | `PRESENT` if either side is, `ABSENT` if both are, else `UNKNOWN` |
| the 60 gate methods (`h`, `cx`, `rz`, `barrier`, `reset`, `store`, ...) | no change |
| `if_test`, `for_loop`, `while_loop`, `switch`, `box` | control flow `PRESENT` |
| `append(op, ...)` | `PRESENT` for a proven `Measure`, unchanged for a proven standard gate, `UNKNOWN` otherwise |
| read only methods and properties (`draw`, `depth`, `data`, ...) | no change |

`transpile(qc, ...)` and `generate_preset_pass_manager(...).run(qc)` return a
new circuit that carries the input's measurement facts, so the standard V2
pipeline stays analysable end to end.

### Where a circuit can come from

A circuit object is created by `QuantumCircuit(...)` and by the circuit
constructors in `qiskit.circuit.library`: the ansatz family (`RealAmplitudes`,
`EfficientSU2`, `TwoLocal`, `NLocal`, `ExcitationPreserving`, `PauliTwoDesign`,
`QAOAAnsatz`), the feature maps (`ZFeatureMap`, `ZZFeatureMap`,
`PauliFeatureMap`), and `QFT`, `QuantumVolume`, `GroverOperator`,
`PhaseEstimation`, `UnitaryOverlap`, `GraphState`, `IQP`, `HiddenLinearFunction`
and `FourierChecking`, in both their class and function spellings.

Each of those was constructed and read on a real Qiskit rather than assumed, and
all of them produce a circuit with no measurement and no control flow.
`scripts/verify_model.py` rechecks that on every run, so an upstream change that
starts adding a measurement is a test failure rather than a silent false
positive.

`random_circuit` is the exception: it takes `measure=`, `conditional=` and
`reset=`, so what it contains depends on the call. Only its kind is asserted,
which is enough for the rules that need a circuit and cannot produce a wrong
answer for the ones that need to know about measurements.

## 4. Invalidation and escape

Global invalidation on any unmodelled call is wrong: `print("running")` cannot
touch a circuit. The rules are scoped.

| Situation | Effect |
| --- | --- |
| Unmodelled call that receives the object | **escape**: unmodelled code may keep the reference and mutate it later |
| Unmodelled call that cannot reach the object | nothing |
| Known pure builtin (`print`, `len`, `str`, ...) receiving it | nothing |
| Unmodelled method on the object itself | invalidate its mutable facts, keep the kind |
| Stored into an attribute, a set, or returned | escape |
| Passed to a **modelled** consumer such as `SamplerV2.run` | nothing, it is consumed not retained |
| `global` or `nonlocal` on the name | escape |
| Calling a function defined in this module | invalidate every fact, since it can reach module level objects |
| Rebinding the name | old binding dropped, the object itself untouched |

This differs from an earlier draft of the specification, which invalidated
rather than escaped on an unmodelled call. Escape is strictly more conservative,
so it can only silence a rule and never create a false positive.

### Containers

Storing into a local container is **not** an escape. Treating it as one would
break the most common Sampler idiom.

```python
pubs = [qc]                 # tracked, local
sampler.run(pubs)           # QXL103 still sees qc

circuits = []
circuits.append(qc)         # tracked
sampler.run(circuits)       # still sees qc

store = {"first": qc}       # tracked, local
sampler.run([store["first"]])   # still sees qc
```

A dict literal is a `Mapping`, which keeps only its values. Iterating a dict
yields its keys, so a `Mapping` is never read as a sequence, and no dict method
is modelled: calling one escapes the values. A subscript answers with the join
of every value, since any key can reach any of them.

A `Sequence` carries a `token` identifying the literal it came from, so
`append` updates only the container it was called on. Two lists holding equal
contents remain two lists. A join of containers with different tokens drops the
token, and the container stops being updatable, which loses a later element
rather than inventing one.

A container handed to unmodelled code escapes everything reachable inside it.
A literal that cannot record its own contents, because a spread brought in
something unknown or because it is larger than the tracking limit, escapes the
values it did name: they are about to become unreachable, and nothing can escape
them afterwards.

### PUB extraction

A `run` replaced by `mock.patch.object(Sampler, "run")` or
`mock.patch("module.Sampler.run")` is not a primitive call: the circuits reach
the mock and no result is produced, so the pub rules stay silent inside that
block. The mock records what it was handed and cannot mutate it, so the circuits
are still analysable after the block ends.

The rules that read pubs report once per `run` call, not once per pub. The
finding is anchored on the call, so a second defective pub in the same call would
repeat the same diagnostic at the same line and column.

A pub is a circuit, or a tuple whose first element is a circuit. A pub list whose
contents cannot be resolved yields no pubs and sets a completeness flag to false,
so a rule knows it did not see everything.

## 5. Control flow policy

There is no full CFG in v0.1, but the policy is fixed so that two
implementations agree.

| Construct | Policy |
| --- | --- |
| `if` / `else` | analyse both branches from a copy, join |
| `for`, `while` | join with the zero-iteration path, so a body mutation is `MAYBE`; the body is walked twice to reach a fixed point |
| `try` / `except` | a handler starts from the join of the entry state and the body state, because an exception can occur anywhere in the body |
| `finally` | applied to the joined state of every path |
| `match` | join every case, plus the implicit no-match path unless a wildcard case exists |
| `with` | the body runs unconditionally; `with qc.if_test(...)` therefore records a control flow op |
| conditional expression, `and` / `or` | join both sides |
| comprehension | iterables and element expressions are evaluated; a list or generator comprehension yields a local sequence carrying its element, a set or dict comprehension yields nothing tracked |
| `return`, `raise`, `break`, `continue` | the path becomes unreachable and contributes nothing to a join |
| `global`, `nonlocal` | escape and rebind to `Unknown` |
| function and class bodies | analysed in their own scope; only import bindings are inherited, since call order is unknown |
| calls between functions | not modelled in v0.1 |

So this stays silent, and the answer to "what does the analyser prove here" is
`MAYBE_PRESENT`:

```python
qc = QuantumCircuit(3)
for qubit in range(3):
    qc.measure(qubit, qubit)
sampler.run([qc])
```

Proving at least one iteration would need range analysis. It is not in v0.1.

## 6. Notebook barriers

A magic that can rebind names produces a **semantic barrier**: every data
binding becomes `Unknown` and every object fact is invalidated. Import bindings
survive, because losing them would silence every later cell for a risk that is
close to theoretical.

`get_ipython().run_line_magic(...)`, `run_cell_magic`, `system` and `getoutput`
are recognised in that call form too, since nbconvert leaves them in exported
notebooks.

## 7. What this deliberately does not do

- No interprocedural analysis, no call graph, no return value propagation.
- No range or value analysis, so a loop is never proven to execute.
- No class attribute tracking; `self.circuit = qc` is an escape.
- No cross-module analysis. Each file is analysed alone.

Each of these is a recall limit, not a precision risk. Every one of them makes
the analyser answer `UNKNOWN`, and `UNKNOWN` means silence.
