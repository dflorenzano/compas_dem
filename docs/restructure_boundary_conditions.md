# compas_dem — BC hierarchy restructure: implementation report

**Branch:** `restructure/bc-hierarchy` (off `main`, nothing pushed)
**Base:** `6e5dd23` (Baraa's partial restructure)
**Dates:** 2026-08-03 / 2026-08-04

Everything below was verified against the code, not taken from the brief. Where I found
the brief or the notes to be wrong about the current state, that is called out
explicitly.

### Commits on this branch

| Commit | What |
|---|---|
| `dff10ea` | The restructure itself — typed BC hierarchy, ownership, deletions, tests (§1–§9) |
| `f2413cc` | This report |
| `d90d044` | Report correction: CRA/RBE history (§5.1) |
| `86d8773` | Solver backends report the real import error; pin matplotlib and compas_cra (§11.1, §11.2) |
| `db880ab` | LMGC90 constructor fixed for compas_lmgc90 0.1.9 (§11.3) |
| `8b73d4c` | Viewer draws contact polygons without a Brep backend (§11.4) |
| `d455f26` | Restore every load type; add `Problem` convenience helpers (§6.2, §6.5) |
| `72e1c78` | Report update |
| `046dbf4` | **CRA and RBE now apply loads** (§12) |

Plus one commit in a second repository — see §12:

| Repo | Branch | Commit |
|---|---|---|
| `dflorenzano/compas_cra` (fork of BRG) | `feature/external-loads` | `998a24a` — pushed to the fork, **no PR opened** |

**Two things to read first if time is short:** §12 (CRA and RBE now apply loads — this
closes the branch's one real correctness hole, and needs a decision about upstreaming)
and §11 (five bugs that were already on `main` and blocked every solver from running
outside Rhino).

---

## 1. Executive summary

The review's central instruction — *"a BC is either a displacement or a load and each
has a specific set of utility functions"* — was declared in `6e5dd23` but hollow: the
subclasses were all `pass` and the fat base class still carried every `add_*` method.
This branch makes the hierarchy real, expresses the Analysis/Problem/Results ownership
the notes describe, and adds a test suite where there was a placeholder.

**No capability was removed.** Every load type still exists, reachable two ways — as a
class (`PointLoad.at_face(...)`) or via a `Problem` helper
(`problem.add_point_load_at_face(...)`) that builds that class. The single genuine removal
is `add_gravity`, which provably did nothing. What *was* deleted is duplication and
dead ends: `set_solve_order`, `add_boundary_condition`, `load_model`, and the
`boundary_condition=` keyword that made the old helpers a guaranteed `ValueError`.

Two things turned up that were **not** in the brief and are more serious than API smell:

1. **CRA and RBE silently discarded every boundary condition** (§5.1) — a wrong answer
   returned without warning. **Now fixed** (§12): they apply loads for real, via a small
   additive change to compas_cra that still needs upstreaming. Prescribed displacements
   remain structurally impossible there and are refused explicitly.
2. **`bc.g` was a lie** — no solver ever read it (§5.2).

And separately, **five environment/compatibility bugs already on `main`** meant no solver
could run from an example script outside Rhino at all (§11). Each masked the next; all
five are fixed and verified.

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
│   ├── PointLoad           block, force, anchor, anchor_value
│   ├── Moment              block, moment          (pure couple, no net force)
│   ├── SurfaceLoad         block, face, traction
│   └── BodyForce           acceleration
└── Displacement            block
    ├── Translation         dx, dy, dz   (None = unconstrained)
    └── Rotation            rx, ry, rz   (None = unconstrained)
```

`PointLoad` keeps all four application points, one per factory: `at_vertex`,
`at_face`, `at_point` (explicit xyz) and `at_centroid` (no induced moment). The
anchor is stored symbolically as a kind plus a value and resolved against the model
at solve time, so a load can be built without a model in hand.

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
| "Point Loads are the same as the Body Loads right now… should be placed on a face of the selected block (centroid or vertex)" | **N/A (plugin)** | Scoped to what compas_masonry offers a user, not to the library. compas_dem keeps all four anchors. See §6.2. |
| "The processed point load should not be visualized by the user" | **N/A (plugin)** | Library keeps the anchor symbolic (`anchor`, `anchor_value`) and resolves at solve time, which makes the plugin-side choice easier — nothing is baked into coordinates. |
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
| Commented-out API sketches | `boundary_condition.py:310-339` | 30 |
| `Analysis.set_model` | `analysis.py:57-72` | 16 |

The nine delegators were: `add_point_load_at_vertex`, `add_point_load_at_face`,
`add_point_load_at_point`, `add_point_load_at_centroid`, `add_global_body_force`,
`add_surface_load`, `add_displacement`, `add_rotation`, `add_moment`.

### What was NOT deleted — an important distinction

**Nothing a user could previously do was taken away.** The delegators were rewritten, not
removed: each is now a thin wrapper that builds the corresponding class and registers it
(§6.5). Both spellings work and produce identical data:

| Old delegator | Now, as a helper | Or, as a class |
|---|---|---|
| `add_point_load_at_vertex` | `problem.add_point_load_at_vertex(...)` | `PointLoad.at_vertex(...)` |
| `add_point_load_at_face` | `problem.add_point_load_at_face(...)` | `PointLoad.at_face(...)` |
| `add_point_load_at_point` | `problem.add_point_load_at_point(...)` | `PointLoad.at_point(...)` |
| `add_point_load_at_centroid` | `problem.add_point_load_at_centroid(...)` | `PointLoad.at_centroid(...)` |
| `add_moment` | `problem.add_moment(...)` | `Moment(...)` |
| `add_surface_load` | `problem.add_surface_load(...)` | `SurfaceLoad(...)` |
| `add_global_body_force` | `problem.add_body_force(...)` | `BodyForce(...)` |
| `add_displacement` | `problem.add_translation(...)` | `Translation(...)` |
| `add_rotation` | `problem.add_rotation(...)` | `Rotation(...)` |

Two names changed to match their classes: `add_global_body_force` → `add_body_force`, and
`add_displacement` → `add_translation`.

Enforced by `test_every_load_type_is_still_reachable` (registers one of each, asserts 7
loads and 2 displacements) and `test_problem_helper_matches_the_class_it_wraps` (helper
output must equal direct construction). **The only genuine capability removal is
`add_gravity`, which never did anything** (§5.2).

Net file sizes:

| File | `main` | now | Δ |
|---|---:|---:|---:|
| `problem/problem.py` | 760 | 579 | −181 |
| `problem/boundary_condition.py` | 339 | 567 | +228 |
| `models/analysis.py` | 89 | 119 | +30 |
| `analysis/resolve.py` | 143 | 190 | +47 |

`boundary_condition.py` more than doubled because eight documented classes replaced one
fat class; `problem.py` shrank by a quarter despite gaining the `Moment` rendering.

---

## 5. Findings not in the brief

### 5.1 CRA and RBE silently discard all boundary conditions — **the serious one**

`src/compas_dem/analysis/cra.py` never calls `resolve_centroidal_loads` or
`resolve_centroidal_displacements`. Grep for `resolve` in that file returns only its own
local `_resolve_mu` / `_resolve_density`. Only `lmgc90.py:143`, `prd.py:60` and
`bla.py:69` read boundary conditions.

**History check.** `git log --all -S"resolve_centroidal_loads" -- src/compas_dem/analysis/cra.py`
returns nothing: **no commit has ever applied loads in CRA or RBE.** This is not a
regression introduced by `6e5dd23` or by this branch.

Displacements are a narrower story. Before `6e5dd23`, `cra.py` did call
`resolve_centroidal_displacements`, but only inside a helper called `_mark_supports`:

```python
if all(v == 0.0 for v in t) and all(v == 0.0 for v in r):
    block.is_support = True
```

It read **zero-valued** movements only, to infer `is_support` — the back half of the old
`add_supports_from_model` round-trip (supports on the model → promoted to zero-displacement
BC entries → converted back to `is_support` for the assembly). A non-zero settlement was
ignored then too. Baraa deleted both halves in `6e5dd23`, correctly: the assembly reads
`element.is_support` directly (`cra.py:86`). Nothing was lost.

**Migration note:** prescribing a zero displacement used to be the idiom for "this block is
a support". Under the new API that raises via the guard below. Use
`model.add_support(block_index=...)` instead.

Consequence in your own repo: `DEM_Boundary_Conditions_Demo.py` set up a 0.5 m
settlement, three surface loads and a 100 kN point load, solved with CRA, and plotted
`result_cra` beside `result_lmgc90`. The CRA result was self-weight alone. Nothing warned.

**First response:** made both solvers refuse rather than mislead, so a problem carrying
boundary conditions raised instead of silently returning a self-weight answer.

**Then fixed properly — see §12.** CRA and RBE now apply loads for real, via a small
additive change to compas_cra. The guard survives only for *prescribed displacements*,
which are structurally impossible in the formulation.

> `The CRA and RBE solvers cannot apply prescribed movements (Translation): support
> blocks are excluded from the equilibrium system and have no displacement degrees of
> freedom. Solve this problem with Solver.LMGC90(...), Solver.PRD(...) or
> Solver.BLA(...).`

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

### 5.5b `_resolve_mu` stopped defaulting to 0.6 in `6e5dd23` — plugin-visible

Not this branch, but easily mistaken for it when CRA "stops working" in Rhino. Baraa
changed the fallback in `cra.py`:

```python
-    if problem.contact_properties.contact_model:
+    elif problem.contact_properties.contact_model:
         return problem.contact_properties.contact_model.mu
-    return 0.6
+    else:
+        raise ValueError("No friction coefficient provided and no contact model in the problem.")
```

A CRA or RBE solve with no contact model previously ran with `mu=0.6`; it now raises. The
plugin has 2 `add_contact_model` call sites, so any path that reached a solve without one
worked before `6e5dd23` and fails after. Independent of the boundary-condition guard.

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

### 6.2 Point load anchors — narrowed, then restored *(reversed 2026-08-04)*

**Current state: all four anchors and the pure couple are present. Nothing was lost.**

This was the one place I over-cut, and it is worth understanding because it turns on a
scoping question that will come up again.

**What I did first.** Reading the masonry note *"a point load can be applied to a vertex
or the centroid of a selected face"* together with *"Point Loads are the same as the Body
Loads right now"*, I cut `at_point` and `at_centroid`, leaving only `at_vertex` and
`at_face`, and dropped `add_moment` — reasoning that a pure couple was not in the reviewed
class list, was unused by the plugin, and that eccentric moments come free once loads
anchor off-centroid.

**Why that was wrong.** Those notes scope what *compas_masonry offers a Rhino user*, not
what the library can express. The governing principle:

> compas_dem keeps the full toolset. compas_masonry exposes a deliberately narrow subset.
> Restricting the library forecloses that choice for every other consumer.

The "summer school" framing in the note is the tell — it describes a teaching
configuration of the plugin, not a permanent library constraint.

**Restored.** `PointLoad` has four factories, one per application point:

| Factory | Application point | Induced moment |
|---|---|---|
| `PointLoad.at_vertex(block, vertex, force)` | a vertex of the block geometry | eccentric |
| `PointLoad.at_face(block, face, force)` | centroid of a face | eccentric |
| `PointLoad.at_point(block, point, force)` | explicit `[x, y, z]` | eccentric |
| `PointLoad.at_centroid(block, force)` | the block centroid | **none** (zero lever arm) |
| `Moment(block, moment)` | — pure couple, no net force | as given |

The anchor is stored as a kind plus a value (`anchor`, `anchor_value`) and resolved
against the model at solve time. `anchor_value` is an index for `vertex`/`face`, `[x,y,z]`
for `point`, and `None` for `centroid`; a mismatch raises at construction.

**What survives from the original concern.** The observation that a centroidal point load
is indistinguishable from a body force on that block is *true*, and is documented in
`PointLoad`'s docstring as a note rather than enforced by removal. The user is told; the
option remains. That is the "less features, more control" line drawn at the right level —
guidance in the library, restriction in the plugin.

**Practical consequence for compas_masonry.** The plugin's `Problem_Loads` command should
offer vertex and face only, per the summer-school decision. That is now a plugin-side
choice, reversible without touching this library.

### 6.5 `Problem` helper methods restored as thin wrappers *(added 2026-08-04)*

**This one needs Baraa's agreement, because it partially reverses "one way to do it".**

The review objected to the duplicated load API. I deleted all nine `Problem.add_*`
delegators. They are now back — but rebuilt so the objection no longer applies.

**What was actually wrong with the old ones.** Two things, and only one of them was
"duplication":

1. Every delegator took `boundary_condition=None` and raised `ValueError` if you omitted
   it. A required argument with a default of `None` is a guaranteed runtime error for
   anyone who reads the signature and assumes it is optional. *This* was the footgun.
2. Both levels held real logic — the `Problem` method resolved geometry (`_block`,
   `vertex_coordinates`) and the `BoundaryCondition` method stored it. Two places to
   change, two places to drift.

**How the new ones differ.** Both causes are gone:

```python
def add_point_load_at_vertex(self, block, vertex, force, loading_type="ramp", name=None):
    """Add a concentrated force at a vertex of a block. See PointLoad."""
    return self.add(PointLoad.at_vertex(block=block, vertex=vertex, force=force,
                                        loading_type=loading_type, name=name))
```

- **No `boundary_condition=` keyword.** A problem *is* the load case, so there is nothing
  to target and nothing to forget. Pinned by `test_problem_helpers_take_no_boundary_condition_kwarg`,
  which walks every `add_*` method and asserts the parameter is absent.
- **No logic.** One line: build, register, return. The class is the only place data lives,
  and geometry resolution happens once, in `resolve.py`, at solve time.
- **Returns the object**, so it can be kept for reference, inspected, or named.

**The honest tension.** There are now two spellings for the same thing:

```python
problem.add_point_load_at_face(block=10, face=2, force=[0, 0, -5000])   # helper
problem.add(PointLoad.at_face(block=10, face=2, force=[0, 0, -5000]))   # class
```

That is a real cost against "one way to do it". The argument for paying it: the helper is
the discoverable path — `problem.add_<tab>` lists everything available without knowing the
class names — while the class path is what a plugin or serializer needs. They cannot drift,
because one calls the other, and a test asserts their output is identical.

**Worth deciding at the meeting:** whether the discoverability is worth the second
spelling, or whether the helpers should be the only public path with the classes treated
as internal.

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
| `problem.add_point_load(block_index, force)` | `problem.add(PointLoad.at_centroid(block=…, force=…))` — old default was the centroid | 5 |
| `problem.add_point_load_at_centroid(b, f, bc)` | `problem.add(PointLoad.at_centroid(block=b, force=f))` | — |
| `problem.add_point_load_at_vertex(b, v, f, bc)` | `problem.add(PointLoad.at_vertex(block=b, vertex=v, force=f))` | — |
| `problem.add_point_load_at_face(b, fi, f, bc)` | `problem.add(PointLoad.at_face(block=b, face=fi, force=f))` | — |
| `problem.add_point_load_at_point(b, pt, f, bc)` | `problem.add(PointLoad.at_point(block=b, point=pt, force=f))` | — |
| `problem.add_surface_load(b, fi, load, bc)` | `problem.add(SurfaceLoad(block=b, face=fi, traction=load))` — note `load` → `traction` | — |
| `problem.add_global_body_force(ax, ay, az, bc)` | `problem.add(BodyForce(acceleration=[ax, ay, az]))` | 5 |
| `problem.add_displacement(b, [dx,dy,dz], bc)` | `problem.add(Translation(block=b, dx=…, dy=…, dz=…))` | — |
| `problem.add_rotation(b, rot, bc)` | `problem.add(Rotation(block=b, rx=…, ry=…, rz=…))` | — |
| `problem.add_moment(b, m, bc)` | `problem.add(Moment(block=b, moment=m))` | — |
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

**Every row above is a mechanical rename.** No plugin call site needs a modelling
decision, because every old application point still exists. The one thing to be
deliberate about: the plugin *should* narrow its own UI to vertex and face per the
summer-school decision (§6.2), but that is a choice it now makes freely rather than one
the library forces.

**Genuinely gone, with no replacement:** `add_gravity` (never did anything — §5.2),
`add_boundary_condition` (named groups were labels, not load cases — §2.7),
`set_solve_order` (§2.7), `add_supports_from_model` / `add_support` (supports live on the
model — §5.5), `load_model` (§2.4).

---

## 8. Tests

**102 tests, all passing, none skipped**, replacing the single `test_placeholder.py`.
(Every LMGC90 test now runs too — see §11.4.)

| File | Tests | Covers |
|---|---:|---|
| `tests/conftest.py` | — | `unit_boxes` fixture: two stacked 1 m cubes at 2000 kg/m³, so mass is exactly 2000 kg and face area exactly 1 m² — resolution is checkable by hand |
| `test_boundary_conditions.py` | 34 | hierarchy membership, `Displacement` can't take loads, `Gravity` absent, all four point-load anchors, `Moment`, anchor/value mismatch rejection, serialization round-trip per type |
| `test_resolve.py` | 20 | numeric resolution: body force × mass, eccentric moment from vertex and explicit-point anchors, zero moment at the centroid, pure couple, traction × area, per-loading-type split, cross-filtering, missing block/vertex/face errors |
| `test_problem_analysis.py` | 43 | `add()` type + duplicate rejection, every helper builds/registers/returns, helpers take no `boundary_condition=`, helper output equals direct construction, removed-API assertions, model not serialized, unbound problem raises, analysis rebinding, guid mismatch, model written once, results ownership, solve guards, CRA/RBE refusal |
| `test_integration_arch.py` | 5 | full workflow from the reference scripts: arch → contacts → supports → material → problem → solve → dump → load → re-solve, on CRA, RBE and LMGC90 |

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
| `pytest tests/ -q` | **102 collected, 102 passed, 0 skipped** |
| CRA end-to-end on a real arch | solved — 49 contacts, forces 11.0–18.4 kN |
| RBE end-to-end on a real arch | solved — 19 contacts |
| LMGC90 end-to-end with loads | solved — applies `PointLoad`, `BodyForce`, `Translation` |
| CRA/RBE refusing a loaded problem | raises as designed |
| All four point-load anchors + `Moment` | resolve, solve through LMGC90, and round-trip |
| Helper methods vs direct class construction | identical `__data__` |
| Solve through the **viewer import path** | CRA and RBE both solve after importing `DEMViewer` first |
| `add_solution` without a Brep backend | runs clean (offscreen Qt) |
| Round trip: solve → dump → load → rebind → re-solve | works, results preserved |
| Model written once per analysis | 1 occurrence of the `BlockModel` dtype |
| Guid stability across round-trip | model, problem and BC guids all stable |
| `ruff check` | clean except 1 pre-existing error in `prd.py`, confirmed on `main` |
| `ruff format --check` | clean except `elements/block.py`, pre-existing on `main` |
| Python 3.9 (Rhino) syntax | all of `src/` parses with `feature_version=(3,9)`; no PEP 604 unions |
| Stale API references in `src/`, `scripts/`, `docs/` | none remaining |

### Physical sanity checks

Not just "it returned a number" — the numbers were checked against hand calculations on
a 100-block arch (rise 4.393, span 21.213, thickness 0.5, depth 3.0, density 2000):

| Check | Result |
|---|---|
| Total self-weight | 704.9 kN |
| Σ vertical support reactions (self-weight only) | 690.8 kN = **0.980 × weight**, exactly the 98/100 blocks above the interfaces — the two support blocks bear directly on ground |
| Horizontal thrust per support | ~394 kN vs parabolic estimate `wL²/8r` ≈ 425 kN |
| Contact force distribution | springing 524 kN vs crown 395 kN, ratio 1.33 |
| LMGC90 convergence | 50 steps (the no-arg default) is **3.3% off** vertical equilibrium; 1000 steps is **0.3% off** |

The last row is a usability finding: `Solver.LMGC90()` with no arguments silently falls
back to `duration=0.5s, n_steps=50`, which is not converged for a 100-block model. Worth
discussing whether that default should exist at all, or should warn more loudly.

**Still unexercised:** BLA and PRD — `compas_bla` and `compas_pr3d` are not installed in
`dem-dev`. Their code paths are unchanged by this branch beyond the resolver they call,
which is covered by unit tests and by the LMGC90 integration test.

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

## 11. Five bugs already on `main` that stopped the solvers running *(2026-08-04)*

None of these came from the restructure. All five were present on `main`, and each was
hidden by the one before it — they surfaced one at a time as each was cleared. Together
they meant **no solver could run from an example script outside Rhino**.

This section matters for the meeting because it explains why "it worked in Rhino" and
"it fails in dem-dev" were both true at the same time.

### 11.1 A missing `matplotlib` reported as "compas_cra is not installed"

**Symptom.** Running any example script:

```
ImportError: compas_cra is not installed. Install it to use the CRA / RBE solvers.
```

`compas_cra` was installed and working.

**Cause.** A four-step chain:

1. Every example script imports `DEMViewer`, which pulls in **PySide6**.
2. PySide6/shiboken installs a **global import hook** that calls `inspect.unwrap` on every
   newly imported module.
3. `inspect.unwrap` does `hasattr(f, "__wrapped__")`, which forces **pyomo's lazy
   dependency proxies** to resolve. `compas_cra` imports pyomo.
4. `matplotlib` — an optional pyomo dependency — was absent, so the proxy raised
   `DeferredImportError`. That is a **subclass of `ImportError`**, so `cra.py`'s blanket
   `except ImportError` caught it and re-reported a cause it had never checked.

**Why the test suite missed it.** The order of imports decides the outcome. A bare
`import compas_cra` succeeds; `import PySide6` *then* `import compas_cra` fails. My tests
never imported the viewer, so they passed while every real script failed. Reproduced
directly:

```
A: compas_cra alone                 -> imports fine
B: PySide6 first, then compas_cra   -> DeferredImportError: matplotlib
```

**Fix (`86d8773`).** `matplotlib` added to `requirements-analysis.txt` with the reason.
All three backends (`cra.py`, `bla.py`, `prd.py`) now include the original exception and
stop asserting which package is missing:

```python
except ImportError as exc:
    raise ImportError(f"The CRA / RBE solvers could not be loaded: {exc}. ...") from exc
```

**Discussion point.** This class of bug — a broad `except ImportError` that re-raises with
a guessed cause — cost hours. Worth agreeing as a convention that optional-dependency
guards must preserve the original error.

### 11.2 `compas_cra` pinned at 0.4.0 because 0.5.0 was never published

`requirements-analysis.txt` listed `compas_cra` unpinned, so pip installed **0.4.0** — the
newest on PyPI. **v0.5.0 exists only as a GitHub tag.** No amount of `pip install -U`
would ever have found it.

Checked before upgrading: the 0.5.0 changelog is `compas_view2` → `compas_viewer`, COMPAS 2
sample files, and a viewer arrow fix — **no solver math**. The three functions compas_dem
calls (`cra_solve`, `cra_penalty_solve`, `rbe_solve`) have unchanged signatures.

Now pinned to the tag:

```
compas_cra @ git+https://github.com/BlockResearchGroup/compas_cra@v0.5.0
```

**Discussion point.** Worth asking Baraa whether 0.5.0 should be released to PyPI, since
every fresh environment silently gets 0.4.0 otherwise.

### 11.3 The `ipopt` pin shipped no executable

Covered in full at §5.4: `environment.yml` pinned `ipopt ==3.14.9`, a conda-forge
build that ships the library without the `ipopt` binary pyomo shells out to. Listed
here because it belongs to the same chain — it was the first of the five to surface.

### 11.4 LMGC90 broken against `compas_lmgc90` 0.1.9

Once `matplotlib` let `compas_lmgc90` import at all, a pre-existing incompatibility
appeared immediately:

```
TypeError: Solver.__init__() missing 1 required positional argument: 'model'
```

`compas_lmgc90` 0.1.9 takes the model in the constructor and converts it there, replacing
the separate `geometry_from_model()` call, which no longer exists. Checked every method
compas_dem calls — `geometry_from_model` is the **only** one that disappeared; the other
eight are intact. So the port is one line (`db880ab`):

```python
solver = Solver(model, density=density, dt=dt, theta=theta)
```

Confirmed unrelated to this branch: `git diff main...HEAD -- lmgc90.py` was empty before
this fix. It had been invisible because `compas_lmgc90` could not be imported in
`dem-dev`, so the LMGC90 integration test *skipped* rather than failed — a reminder that a
skipping test proves nothing.

**Consequence:** `test_loaded_arch_solves_with_lmgc90` now runs, giving the boundary
condition resolver its first end-to-end coverage on a solver that actually applies loads.

### 11.5 The viewer required a Brep backend that only Rhino provides

`DEMViewer.add_solution` called `Polygon.to_brep()` on every contact polygon, which
dispatches to a COMPAS Brep plugin. **Rhino supplies one; a standalone install does not**
unless `compas_occ` is present — and `compas_occ` is in no requirements file. So every
`add_solution` outside Rhino raised `PluginNotInstalledError` as soon as a solve finally
succeeded.

This is the direct explanation of "it worked in Rhino".

`compas_viewer` has a native `PolygonObject`, and the rest of the codebase already adds
polygons directly, so the Brep round-trip bought nothing. Both call sites now pass the
polygon (`8b73d4c`) — works in Rhino and standalone, and avoids adding OCC as a dependency
just to shade a contact face.

### Summary for the meeting

| # | Bug | Origin | Fixed in |
|---|---|---|---|
| 11.1 | `matplotlib` missing, misreported as `compas_cra` | pre-existing | `86d8773` |
| 11.2 | `compas_cra` 0.4.0; 0.5.0 is GitHub-tag-only | pre-existing | `86d8773` |
| 11.3 | `ipopt ==3.14.9` pin ships no executable | pre-existing | `dff10ea` |
| 11.4 | LMGC90 constructor signature | pre-existing | `db880ab` |
| 11.5 | Viewer needs a Brep backend | pre-existing | `8b73d4c` |

All five verified fixed: CRA, RBE and LMGC90 each solve a real arch, and `add_solution`
runs without a Brep backend.

---

## 12. CRA and RBE now apply loads *(2026-08-04)* — **needs a decision**

§5.1 recorded that CRA and RBE silently discard every boundary condition. That is now
fixed, and the fix required a change in **compas_cra**, not in compas_dem. This section
is the main thing to discuss.

### Why it turned out to be small

The hook already existed. `external_force_setup()` builds a per-block **6-vector**
`[fx, fy, fz, mx, my, mz]`, and the equilibrium constraint is literally `A_eq · f = -p`.
compas_cra only ever populated `p[2]`, with self-weight. Every other slot was zero and
unused.

compas_dem's `resolve_centroidal_loads()` already returns exactly
`{block: {"force", "moment"}}`. **The data structures already matched** — this was an
addition into `p`, not a reformulation of anything.

### What changed in compas_cra

Branch `feature/external-loads` on `dflorenzano/compas_cra`, commit `998a24a`, rebased
onto current BRG `main`. **Pushed to the fork only; no pull request has been opened.**

```python
external_force_setup(assembly, density, loads=None)
cra_solve(assembly, ..., loads=None)
cra_penalty_solve(assembly, ..., loads=None)
rbe_solve(assembly, ..., loads=None)
```

`loads` is `{node_key: [fx, fy, fz, mx, my, mz]}`, superposed on self-weight. Shorter
sequences are zero-padded, so `[fx, fy, fz]` is a force with no moment. Loads on support
blocks are ignored — supports are excluded from the equilibrium system, so anything
applied to them is absorbed. Unknown node keys and over-long vectors raise.

Also removed a stray `print` of the block density that emitted one line per block on
every solve — that was the `1.0 1.0 1.0 …` noise in every CRA run.

11 new tests in `tests/test_external_loads.py`; 15/15 pass with no regressions.

### What changed in compas_dem

`_centroidal_loads_for_cra()` converts our loads into compas_cra's units. compas_cra
works in a scaled system — its force vector holds `volume × density`, not a force, and
`_post_processing_cra` scales the result back up by `density × 9.81`. Applied loads are
real newtons, so they are divided by that same factor going in.

The guard narrows from *"cannot apply the boundary conditions"* to *"cannot apply
prescribed movements"*.

### Displacements are still impossible, and that is structural

Not an oversight. `free_nodes()` excludes every `is_support` block, and the displacement
variable is sized `free_num * 6` — **support blocks have no displacement degrees of
freedom in the formulation at all**. A support settlement cannot be expressed without
restructuring the free/fixed partition, which changes the problem class rather than
patching it. Settlement stays with LMGC90, PRD and BLA.

### Verification

On a 20-block arch, self-weight reactions 27.580 kN:

| Case | Reactions | Delta | Expected |
|---|---|---|---|
| CRA + 2 kN point load | 29.580 kN | **+2.000** | +2.000 |
| RBE + 2 kN point load | 29.580 kN | **+2.000** | +2.000 |
| CRA + eccentric load (face anchor) | 29.580 kN | +2.000 | +2.000 |
| CRA + pure couple | 27.580 kN | **−0.0000** | 0 — no net force |
| CRA + prescribed movement | — | raises | rejected |

In compas_cra's own unit-cube test: 0.25 per corner under self-weight, 0.5 with an equal
load applied, on both `cra_solve` and `rbe_solve`.

### For discussion

1. **Should this go upstream to BRG?** The change is additive and backward-compatible —
   omitting `loads` reproduces the previous behaviour exactly, and a test asserts it.
   Baraa's own compas_cra work is already merged upstream (BRG PR #9), so the path is
   established.
2. **Until it lands, compas_dem depends on an unreleased branch.** Options: pin
   `requirements-analysis.txt` at the fork branch, vendor the ~30 lines, or keep the
   guard and treat CRA loads as opt-in. See §13.
3. **PRD and BLA already applied loads.** Only CRA/RBE were missing it, because the two
   come from compas_cra rather than from compas_dem's own resolver.
4. **A related pre-existing bug:** `_resolve_density` takes the *first* block's density
   and scales the whole model by it, so mixed-density models are already mis-scaled in
   the CRA path, independent of loads. compas_cra exports `density_setup()` for per-block
   densities and compas_dem does not use it.

---

## 13. Open items

### Needs a decision with Baraa

1. **Upstream the compas_cra `loads` change** (§12). CRA and RBE now apply loads, but the
   change lives on `dflorenzano/compas_cra:feature/external-loads` with **no PR opened**.
   Until it lands, compas_dem depends on an unreleased branch: either pin
   `requirements-analysis.txt` at the fork, vendor the ~30 lines, or gate CRA loads
   behind a capability check. **Decide this first.**
2. **`Gravity` deleted, not just `g`** (§6.1). The one knowing departure from the reviewed
   class list. If it comes back, the honest version makes self-weight opt-in — four
   backends to edit, and it silently changes results for every script that never added
   gravity.
3. **Two spellings for adding a load** (§6.5). Helper methods *and* classes. Discoverability
   vs "one way to do it" — decide whether both stay public.
4. **`SurfaceLoad` vs `FaceLoad`** naming (§6.3). Cheap to change now, ugly later.
5. **`Solver.LMGC90()` with no arguments** silently uses 50 steps, which is 3.3% off
   equilibrium on a 100-block arch (§9). Should the default exist?
6. **Release `compas_cra` 0.5.0 to PyPI** (§11.2), so fresh environments stop silently
   getting 0.4.0.

### Housekeeping

7. **Orphaned data files.** `docs/tutorial/three_blocks/DEM_problem.json` and
   `DEM_results.json` are unreferenced *and* hold the pre-`6e5dd23` serialization format,
   so they can no longer deserialize. Left in place — deleting committed data is your call.
8. **`prd.py:95`** unused `cvx_result`, and **`elements/block.py`** formatting — both
   pre-existing on `main`, deliberately untouched.
9. **Plugin migration** — §7. Not attempted here, per the brief. Every row is a mechanical
   rename; no modelling decisions required.
10. **Before syncing to Rhino:** `rm -rf build/` then
    `~/.local/bin/sync-compas-dem-rhino.sh`. This branch deletes and renames modules, and
    setuptools packages from a stale `build/lib`, which would resurrect them.
11. **Nothing is pushed.** Six commits on `restructure/bc-hierarchy`; `main` untouched.
