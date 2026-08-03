# compas_dem — BC hierarchy restructure: implementation report

**Branch:** `restructure/bc-hierarchy` (off `main`, nothing pushed)
**Documents commit:** `dff10ea` — *refactor: split BoundaryCondition into typed Load/Displacement leaves*
**Base:** `6e5dd23` (Baraa's partial restructure)
**Date:** 2026-08-03
**Scope:** 50 files, +2011 / −1259 (this report was added separately and is not counted)

Everything below was verified against the code, not taken from the brief. Where I
found the brief or the notes to be wrong about the current state, that is called out
explicitly.

---

## 1. Executive summary

The review's central instruction — *"a BC is either a displacement or a load and each
has a specific set of utility functions"* — was declared in `6e5dd23` but hollow: the
subclasses were all `pass` and the fat base class still carried every `add_*` method.
This branch makes the hierarchy real, deletes the duplicated API layer, expresses the
Analysis/Problem/Results ownership that the notes describe, and adds a test suite where
there was a placeholder.

Three things turned up that were **not** in the brief and are more serious than API
smell:

1. **CRA and RBE silently discard every boundary condition.** (§5.1)
2. **`bc.g` was a lie** — no solver ever read it. (§5.2)
3. **The `environment.yml` ipopt pin was itself the bug** that made CRA/RBE unrunnable. (§5.4)

---

## 2. Note-by-note comparison — design review notes

Verdict key: **DONE** = implemented as written · **DONE+** = implemented, went further ·
**DIVERGED** = deliberately did something else, flagged · **N/A** = plugin-side, not library.

### 2.1 "most of the public API should be on the level of the model"

**Verdict: DONE, reinterpreted — needs your sign-off.**

This note predates the `Analysis` object that has since been built, and taken literally
it now conflicts with it. My reading: it meant *one entry point, not four*, not
literally "put everything on `BlockModel`". Resolved as:

| Task | Object |
|---|---|
| geometry, contacts, `is_support`, materials | `BlockModel` |
| loads, prescribed movements, contact model, solver | `Problem` |
| owns model + problems + results, serializes whole | `Analysis` |
| read forces / displacements / contact data | `Results` |

The concrete effect that *does* honour the note: **supports moved to the model and
stayed there**. `Problem.add_support` / `add_supports_from_model` are gone; solvers read
`block.is_support` directly. `BlockModel` already had `add_support`, `add_supports`,
`remove_support`, `clear_supports` — nothing new was needed.

### 2.2 "if you assign the model to the problem you do not gain efficiency… you don't need to use the guid to reduce (if you are working in memory)"

**Verdict: DONE.** `6e5dd23` had this backwards: it stored `model_id` plus a transient
`_model`, and made you call `load_model(model)` with a guid check to get the object back.
That is exactly the indirection the note says not to pay for.

Now `problem.model` **is** the live `BlockModel` object. `load_model()` and the public
`model_id` are deleted. The guid exists only in the serialized form.

### 2.3 "If you are serializing the Problem, you don't want to serialize the model as well with it"

**Verdict: DONE, test-enforced.**

```python
def test_problem_does_not_serialize_the_model(unit_boxes):
    payload = compas.json_dumps(Problem(unit_boxes))
    assert "BlockModel" not in payload
    assert str(unit_boxes.guid) in payload
```

Also enforced at the analysis level — the model is written exactly once no matter how
many problems reference it (`test_analysis_writes_the_model_exactly_once`).

### 2.4 "If you serialize the Problem (which stores the Object instance of the model), you need to override `__from_data__` and `__data__`"

**Verdict: DONE — this is exactly your Q4 answer.**

- `Problem.__data__` writes `{"model_guid": "<guid>", …}` — a string, never the object.
- `Problem.__from_data__` reconstructs **unbound**: `_model = None`, `_model_guid` kept.
- `Analysis.__data__` writes the model once alongside its problems.
- `Analysis.__from_data__` walks the problems and calls `problem._bind_model(self.model)`,
  which raises on a guid mismatch.

A problem deserialized *on its own* is unbound, and says so:

> `This problem is not bound to a model (model_guid=…). A problem only carries a guid
> reference to its model when serialized; load it as part of an Analysis, or add it to
> one with analysis.add_problem(problem).`

### 2.5 "Base class BoundaryCondition, then Load / Displacement, and PointLoad, SurfaceLoad, Gravity, Translation, Rotation"

**Verdict: DONE, with one DIVERGENCE — `Gravity` deleted. See §6.1.**

Built:

```
BoundaryCondition(Data)
├── Load                    loading_type
│   ├── PointLoad           block, force, anchor, anchor_index
│   ├── SurfaceLoad         block, face, traction
│   └── BodyForce           acceleration
└── Displacement            block
    ├── Translation         dx, dy, dz   (None = unconstrained)
    └── Rotation            rx, ry, rz   (None = unconstrained)
```

`BodyForce` is not in the reviewed list but had to exist — the plugin uses it in 5 places
(`add_body_force`) and it is how seismic coefficients are applied.

The leaves are now **the data**, not containers. One object = one entry. This is the
consequence of §2.7: since `solve()` sums every registered BC anyway, named groups were
labels, not load cases.

### 2.6 "It makes more sense that a BC is either a displacement or a load and each has a specific set of utility functions"

**Verdict: DONE, test-enforced.** The point of the split is what becomes *unspellable*:

```python
def test_displacements_do_not_expose_load_methods():
    disp = Translation(block=0, dx=1.0)
    assert not hasattr(disp, "add_point_load")
    assert not hasattr(disp, "add_surface_load")
    assert not hasattr(disp, "add_global_body_force")
```

`resolve.py` now dispatches on the branch (`isinstance(bc, Load)` / `isinstance(bc,
Displacement)`) instead of iterating four parallel dict-lists. Both resolvers ignore what
isn't theirs, so `problem.boundary_conditions` goes straight in with no pre-filtering.

### 2.7 "Do not expose the ordering of the solving or the selection of all the boundary conditions. If I want to solve another list of BCs, I create a new problem. Provide a default order."

**Verdict: DONE.** Deleted `Problem.set_solve_order` (~25 lines) and its only caller
`_find_boundary_condition` (~18 lines). Also deleted `add_boundary_condition`, since
named groups were the *selection* mechanism this note rejects.

Default order = insertion order, and it is not adjustable. Enforced:

```python
def test_solve_ordering_is_not_exposed(unit_boxes):
    problem = Problem(unit_boxes)
    assert not hasattr(problem, "set_solve_order")
    assert not hasattr(problem, "add_boundary_condition")
```

"A different set means a new problem" is now demonstrated in the scripts: the BC demo
carries a loaded problem *and* a self-weight problem in one analysis, and
`dem_new_features.py` adds a `settlement only` problem beside the combined one.

### 2.8 "Less features, more control, less breaking scenarios" / "Remove the option for them to get it wrong"

**Verdict: DONE+.** Deletions in §4. Beyond the removals, the failure modes that were
*possible before and are impossible now*:

| Before | Now |
|---|---|
| `problem.add_point_load(...)` without `boundary_condition=` → guaranteed `ValueError` | kwarg doesn't exist |
| `bc.add_point_load(...)` on a "displacement" BC | `Displacement` has no such method |
| `add_gravity(g=3.71)` → silently ignored | method deleted; self-weight documented as unconditional |
| Point load at block centroid → no moment, = body force | anchor is required, vertex or face only |
| CRA solve with loads → wrong answer, no warning | raises |
| `Translation(block=0)` with no components → constrains nothing | raises |
| Reordering BCs → unclear which are solved | not expressible |

### 2.9 "Analysis: Model / Problem / Results. Model independent, Problem independent, results are owned."

**Verdict: DONE — the "results are owned" half did not exist before.**

You suspected this and were right: `Analysis` had no results field at all, and
`problem.solve()` returned a `Results` that nothing kept. Now:

- `Analysis.results: dict[str, Results]`, keyed by problem guid.
- `Problem.solve()` records into the owning analysis via a transient `_analysis`
  back-reference, rebuilt on load. Standalone problems still solve and record nothing.
- `Results` keeps `model_id` / `problem_id` as an integrity check.

Guids survive JSON round-trip (`Data.__jsondump__` writes `guid`, `__jsonload__` restores
it), so the keying is stable — verified, not assumed.

### 2.10 "changes… on a different branch, not on main"

**Verdict: DONE.** `restructure/bc-hierarchy`, branched from `main`, one commit, not pushed.
`main` untouched.

---

## 3. Note-by-note comparison — compas_masonry notes

Most are plugin-side. Two constrained the library design and were applied here.

| Note | Verdict | Detail |
|---|---|---|
| "compas_dem should now have a class for boundary conditions" | **DONE** | Users construct `PointLoad`/`SurfaceLoad`/`Translation`… objects; the plugin no longer assembles dict entries. |
| "Point Loads are the same as the Body Loads right now… should be placed on a face of the selected block (centroid or vertex)" | **DONE+** | This is why `at_point` and `at_centroid` were cut. Only `at_vertex` and `at_face` remain. See §6.2. |
| "The processed point load should not be visualized by the user" | **N/A (plugin)** | Library keeps the anchor symbolic (`anchor`, `anchor_index`) and resolves at solve time, which makes the plugin-side choice easier — nothing is baked into coordinates. |
| "For surface load… a Rhino method to select a single face. No index inputting" | **N/A (plugin)** | Library still takes `face=<int>`; a Rhino picker supplies it. `problem.inspect_model()` remains the non-Rhino way to find indices. |
| "Distributed load (select a surface), FaceLoad is not DistributedLoad" | **DIVERGED (naming)** | Kept `SurfaceLoad`, matching Baraa's written class list. Read this note as plugin command naming. Cheap to rename if you disagree — say so before the PR. |
| "Loads/Force/Displacements: helper functions to DRAW vectors, not input x,y,z" | **N/A (plugin)** | Library constructors take component lists; a `from_line` helper belongs in the plugin. |
| "Load_in_x, Load_in_y, Load_in_z" | **N/A (plugin)** | Library side already supports it: `Translation(block=0, dx=0.5)` leaves y/z unconstrained. |
| "Tone down the gimmicks / sensible defaults" | **partial** | `inspect_model` still defaults `show_blocks=False`, `face_indices=True` (wireframe-ish), unchanged. Viewer defaults are plugin-side. |
| "Remove the results export command" / new command order | **N/A (plugin)** | No library effect. |
| "Review the latest changes in compas_dem to align" | **this document** | §7 is the migration surface. |

---

## 4. What was deleted, and what it cost

| Target | Location on `main` | ~Lines |
|---|---|---|
| `Problem.set_solve_order` | `problem.py:145-169` | 25 |
| `Problem._find_boundary_condition` | `problem.py:126-143` | 18 |
| 9 duplicated `Problem.add_*` delegators | `problem.py:401-645` | 245 |
| `Problem.add_boundary_condition` | `problem.py:96-124` | 29 |
| `Problem.model_id` / `_model` / `load_model` | `problem.py:41-90` | 30 |
| `BoundaryCondition.add_gravity` + `g` | `boundary_condition.py:37-83` | 15 |
| `BoundaryCondition.add_moment` | `boundary_condition.py:184-206` | 23 |
| Commented-out API sketches | `boundary_condition.py:310-339` | 30 |
| `Analysis.set_model` | `analysis.py:57-72` | 16 |

The nine delegators were: `add_point_load_at_vertex`, `add_point_load_at_face`,
`add_point_load_at_point`, `add_point_load_at_centroid`, `add_global_body_force`,
`add_surface_load`, `add_displacement`, `add_rotation`, `add_moment`.

Net file sizes:

| File | `main` | now | Δ |
|---|---:|---:|---:|
| `problem/problem.py` | 760 | 553 | −207 |
| `problem/boundary_condition.py` | 339 | 422 | +83 |
| `models/analysis.py` | 89 | 119 | +30 |
| `analysis/resolve.py` | 143 | 179 | +36 |

`boundary_condition.py` grew because seven real classes with docstrings replaced one fat
class; `problem.py` shrank by a third.

---

## 5. Findings not in the brief

### 5.1 CRA and RBE silently discard all boundary conditions — **the serious one**

`src/compas_dem/analysis/cra.py` never calls `resolve_centroidal_loads` or
`resolve_centroidal_displacements`. Grep for `resolve` in that file returns only its own
local `_resolve_mu` / `_resolve_density`. Only `lmgc90.py:143`, `prd.py:60` and
`bla.py:69` read boundary conditions.

Consequence in your own repo: `DEM_Boundary_Conditions_Demo.py` set up a 0.5 m
settlement, three surface loads and a 100 kN point load, solved with CRA, and plotted
`result_cra` beside `result_lmgc90`. The CRA result was self-weight alone. Nothing warned.

**What I did:** added `_reject_unsupported_boundary_conditions(problem)` at the top of
both `cra_solve` and `rbe_solve`. A problem carrying any BC now raises, naming the types:

> `The CRA and RBE solvers apply self-weight only, and cannot apply the boundary
> conditions on this problem (PointLoad, SurfaceLoad, Translation). Solve this problem
> with Solver.LMGC90(...), Solver.PRD(...) or Solver.BLA(...), or build a separate
> self-weight-only problem for CRA.`

**What I did NOT do:** teach CRA to apply loads. That is a solver change across the
compas_cra backend, out of scope for an API refactor, and it should be a deliberate
decision with Baraa. **This is the highest-value open item.**

### 5.2 `bc.g` was dead and actively misleading

No solver read it. `lmgc90.py:36` hardcodes `g_vec = np.array([0.0, 0.0, -9.81])`;
`cra.py:167` hardcodes `scale = density * 9.81`. So `add_gravity(g=3.71)` set an attribute
nothing consumed and returned cleanly — the worst kind of silent failure. Both deleted.

### 5.3 `PointLoad.at_vertex` was broken as written

`boundary_condition.py:287` on `main`:

```python
bc.add_point_load(block_index=block_index, force=force, point=vertex_index)
```

`point` is meant to be `[x, y, z]`; a vertex **index** was passed. `resolve.py:87` would
then do `Vector(*entry["point"])` on an `int` → `TypeError`. Dead code, so nobody hit it.
Fixed structurally: the anchor is now `(kind, index)` and resolved against the mesh.

### 5.4 The `environment.yml` ipopt pin was the bug

`ipopt ==3.14.9` was pinned and *installed* — but the conda-forge `3.14.9` build
(`h843a782_1`, osx-arm64) ships the library **without the `ipopt` executable** that pyomo
shells out to. Every CRA and RBE solve died with `No executable found for solver 'ipopt'`.

Upgraded the env to 3.14.13 (which does ship the binary) and changed the pin to
`ipopt >=3.14.13` with a comment explaining why. Three integration tests that would
otherwise have skipped now actually run.

*Note for anyone reproducing:* pyomo resolves `ipopt` via `PATH`, so invoking the env's
interpreter directly is not enough — activate the env, or prepend
`/opt/anaconda3/envs/dem-dev/bin` to `PATH`.

### 5.5 `add_supports_from_model` — dropped correctly, not lost

The brief asked whether this was an accident. It was not. Supports live on the model and
solvers read `block.is_support` directly (`cra.py:86`, `lmgc90.py:149`); nothing needed
them on `Problem`. **But** it was still *called* in 6 places (3 workflow scripts + 3 docs
files), so those were broken.

### 5.6 `scripts/DEM_Analysis_workflow/` was already dead before this branch

Not caused by my changes. That whole folder called `problem.solver()`, `model.solve()`,
`add_contact_model`, `add_support`, `add_supports_from_model` and
`active_boundary_conditions` — all removed in `6e5dd23` or earlier. Only
`DEM_Analysis_Examples/` still ran. Per your "update scripts in this branch" answer, I
fixed the lot. `Arch/502_Displacement_Viz.py` was doubly broken: it loaded results into a
variable named `problem` and then referenced an undefined `results`.

### 5.7 `Problem` was not independent of the model on `main`

`Problem.__init__(model)` required a model to derive `model_id`, so a problem could not
exist before a model — contradicting "Problem is independent". Consequently
`Analysis.set_model` could never usefully run before `add_problem`, and is deleted.
`Analysis` now adopts the model from its first problem if it has none.

---

## 6. Deliberate divergences — flag these on the PR

### 6.1 `Gravity` is deleted, not just `g`

Baraa's list says `Gravity(Load)` explicitly. You chose "delete both, self-weight always
on" when asked. I followed that, and extended it: with `g` gone and self-weight
unconditional, a `Gravity` class holds nothing. An empty `Gravity()` that changes no
result is precisely "a way to get it wrong" — a user adds it believing they enabled
self-weight, or adds it twice.

Documented in `Load`'s docstring and tested:

```python
def test_gravity_is_not_an_api():
    assert not hasattr(problem_module, "Gravity")
    assert not hasattr(BoundaryCondition, "add_gravity")
    assert not hasattr(BoundaryCondition(), "g")
```

**This is the one knowing departure from the reviewed hierarchy. It needs to be a talking
point, not a surprise.** If Baraa wants `Gravity` back, the honest version makes
self-weight opt-in, which means editing all four backends and silently changing results
for every script that never added gravity.

### 6.2 Point loads narrowed to two factories

From four (`at_vertex`, `at_face`, `at_point`, `at_centroid`) plus `add_moment`, down to
`at_vertex` and `at_face`. Driven by your masonry note: *"a point load can be applied to a
vertex or the centroid of a selected face"* and *"Point Loads are the same as the Body
Loads right now"*.

`add_moment` went with them: a pure couple is not in Baraa's class list, is not used by
the plugin, and once loads anchor off-centroid the eccentric moment is produced
automatically.

### 6.3 `SurfaceLoad`, not `FaceLoad`

Kept Baraa's name. The masonry note reads as plugin command naming. Reversible cheaply.

### 6.4 `SurfaceLoad(load=…)` renamed to `traction=`

It is per-area (multiplied by face area at solve time), and the old name invited passing a
force. Renamed while we were already breaking the call.

---

## 7. Migration surface

Every break, old → new. Plugin blast radius from the brief in the right column.

| Old | New | Plugin sites |
|---|---|---|
| `Problem(model)` | `Problem(model, name=...)` — unchanged signature | — |
| `bc = problem.add_boundary_condition("X")` | *(gone)* — `name=` on the leaf object | 6 |
| `problem.add_point_load(block_index, force)` | `problem.add(PointLoad.at_face(block=…, face=…, force=…))` | 5 |
| `problem.add_point_load_at_centroid(b, f, bc)` | `problem.add(PointLoad.at_face(block=b, face=…, force=f))` — **needs a face chosen** | — |
| `problem.add_point_load_at_vertex(b, v, f, bc)` | `problem.add(PointLoad.at_vertex(block=b, vertex=v, force=f))` | — |
| `problem.add_point_load_at_face(b, fi, f, bc)` | `problem.add(PointLoad.at_face(block=b, face=fi, force=f))` | — |
| `problem.add_point_load_at_point(b, pt, f, bc)` | *(gone)* — anchor to a vertex or face | — |
| `problem.add_surface_load(b, fi, load, bc)` | `problem.add(SurfaceLoad(block=b, face=fi, traction=load))` | — |
| `problem.add_global_body_force(ax, ay, az, bc)` | `problem.add(BodyForce(acceleration=[ax, ay, az]))` | 5 |
| `problem.add_displacement(b, [dx,dy,dz], bc)` | `problem.add(Translation(block=b, dx=…, dy=…, dz=…))` | — |
| `problem.add_rotation(b, rot, bc)` | `problem.add(Rotation(block=b, rx=…, ry=…, rz=…))` | — |
| `problem.add_moment(b, m, bc)` | *(gone)* | — |
| `bc.add_gravity(g)` | *(gone)* — self-weight unconditional | 6 |
| `problem.add_supports_from_model()` | *(already gone)* — `model.add_supports([...])` | 5 |
| `problem.add_support(i)` | `model.add_support(block_index=i)` | — |
| `problem.set_solve_order([...])` | *(gone)* — one problem per BC set | — |
| `problem.load_model(model)` | *(gone)* — `analysis.add_problem(problem)` | — |
| `problem.model_id` | `problem.model_guid` (read-only) | — |
| `problem.add_contact_model(...)` | `problem.set_contact_model(...)` *(6e5dd23)* | 2 |
| `problem.add_joint_model(...)` | `problem.set_joint_model(...)` *(6e5dd23)* | 1 |
| `problem.solver(s)` | `problem.set_solver(s)` *(6e5dd23)* | 4 |
| `model.solve(problem)` | `problem.solve()` *(6e5dd23)* | 4 |
| `problem.inspect_model(model)` | `problem.inspect_model()` | — |
| `bc.point_loads` / `.surface_loads` / `.body_forces` / `.displacements` | `problem.loads` / `problem.displacements`, filtered by `isinstance` | — |
| `Analysis(); a.set_model(m)` | `Analysis(m)` | — |
| results discarded | `analysis.results_for(problem)` | — |

**Watch item for the plugin:** the 5 `add_point_load` sites and any centroid loads need a
face or vertex index chosen. That is a modelling decision, not a mechanical rename.

---

## 8. Tests

76 tests, replacing `test_placeholder.py`. 75 pass, 1 skips (`compas_lmgc90` absent from
`dem-dev`).

| File | Tests | Covers |
|---|---:|---|
| `tests/conftest.py` | — | `unit_boxes` fixture: two stacked 1 m cubes at 2000 kg/m³, so mass is exactly 2000 kg and face area exactly 1 m² — resolution is checkable by hand |
| `test_boundary_conditions.py` | 21 | hierarchy membership, `Displacement` can't take loads, `Gravity` absent, factories, validation, serialization round-trip per type |
| `test_resolve.py` | 17 | numeric resolution: body force × mass, eccentric moment from a vertex anchor, traction × area, per-loading-type split, cross-filtering, missing block/vertex/face errors |
| `test_problem_analysis.py` | 33 | `add()` type + duplicate rejection, deleted-API assertions, model not serialized, unbound problem raises, analysis rebinding, guid mismatch, model written once, results ownership, solve guards, CRA/RBE refusal |
| `test_integration_arch.py` | 5 | full workflow from the reference scripts: arch → contacts → supports → material → problem → solve → dump → load → re-solve. Skips per missing backend. |

Worked example of the numeric check — vertex 0 of the lower cube is at
`(-0.5, -0.5, 0.0)`, centroid `(0, 0, 0.5)`, so lever `(-0.5, -0.5, -0.5)`; with force
`(0, 0, -1000)` the moment is `lever × force = (500, -500, 0)`:

```python
def test_point_load_at_vertex_produces_eccentric_moment(unit_boxes, block_indices):
    lower = block_indices[0]
    loads = resolve_centroidal_loads(unit_boxes, [PointLoad.at_vertex(block=lower, vertex=0, force=[0, 0, -1000])])
    assert approx(loads[lower]["force"]) == [0.0, 0.0, -1000.0]
    assert approx(loads[lower]["moment"]) == [500.0, -500.0, 0.0]
```

---

## 9. Verification performed

| Check | Result |
|---|---|
| `pytest tests/ -q` | 76 collected, 75 passed, 1 skipped |
| CRA end-to-end on a real arch | solved, `Results` returned |
| RBE end-to-end on a real arch | solved, `Results` returned |
| CRA refusing a loaded problem | raises as designed |
| Round trip: solve → dump → load → rebind → re-solve | works, results preserved |
| Model written once per analysis | 1 occurrence of the `BlockModel` dtype |
| Guid stability across round-trip | model, problem and BC guids all stable |
| `ruff check src/ tests/ scripts/ docs/` | clean except 1 pre-existing error in `prd.py`, confirmed present on `main` |
| `ruff format --check` | clean except `elements/block.py`, pre-existing on `main` |
| Python 3.9 (Rhino) syntax | all of `src/` parses with `feature_version=(3,9)`; no PEP 604 unions |
| Stale API references in `src/`, `scripts/`, `docs/` | none remaining |
| Syntax check of every `.py` in repo | 0 failures |

BLA and LMGC90 could not be exercised — `compas_bla` is not installed anywhere, and
`compas_lmgc90` lives only in the separate `lmgc90` env. Their code paths are unchanged by
this branch beyond the resolver they call, which is covered by unit tests.

---

## 10. Files changed

**Library (7):** `problem/boundary_condition.py` (rewritten), `problem/problem.py`,
`problem/__init__.py`, `models/analysis.py`, `analysis/resolve.py`, `analysis/cra.py`,
`environment.yml`

**Tests (6):** 5 new, `test_placeholder.py` deleted

**Scripts (24):** `dem_new_features.py`; `DEM_Analysis_Examples/` ×2 (commented lines);
`DEM_Analysis_workflow/` ×21 — `Arch/` ×11, `2_Blocks/` ×4, `3_Blocks/` ×4,
`Barrel_Vault/` ×4, `Arch_Max_min_TL/` ×2, `DEM_BC_Demo/` ×2

**Docs (7):** `compas_geometry_guide.md`, `tutorial/three_blocks/` ×6 (`02_problem.rst`,
`03_analysis.rst` and the four scripts)

The workflow scripts were restructured, not just renamed: the old
`DEM_model.json` + `DEM_problem.json` + `DEM_results.json` split is exactly what
`Analysis` collapses, so they now write a single `DEM_analysis.json`. `03_analysis.rst`
was badly stale — it documented results being written back onto the model in place, which
has not been true since `Results` became standalone.

---

## 11. Open items

1. **CRA/RBE cannot apply loads.** They now refuse instead of lying, but the underlying
   gap is real. Deciding whether to implement it belongs with Baraa. *(highest value)*
2. **`Gravity` deletion** needs Baraa's agreement — §6.1.
3. **`SurfaceLoad` vs `FaceLoad`** naming — §6.3.
4. **Orphaned data files.** `docs/tutorial/three_blocks/DEM_problem.json` and
   `DEM_results.json` are now unreferenced *and* hold the pre-`6e5dd23` serialization
   format, so they can no longer deserialize. Left in place — deleting committed data is
   your call.
5. **`prd.py:94`** unused `cvx_result` — pre-existing ruff error on `main`, untouched.
6. **Plugin migration** — §7. Not attempted here, per the brief.
7. **After any sync:** `rm -rf build/` before `~/.local/bin/sync-compas-dem-rhino.sh`.
   This branch deletes and renames modules, so a stale `build/lib` will resurrect them.
