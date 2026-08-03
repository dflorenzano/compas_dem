"""Showcase of the compas_dem API: materials, model-side supports, boundary conditions,
every load application type, all five solvers, and overlaying their solutions.

Run top to bottom. The solvers each need their own backend installed
(compas_lmgc90, compas_cra, compas_pr3d, compas_bla); the ones that are commented
out below say which.
"""

import pathlib

import compas
from compas_dem.material import Stone
from compas_dem.models import Analysis
from compas_dem.models import BlockModel
from compas_dem.problem import BodyForce
from compas_dem.problem import PointLoad
from compas_dem.problem import Problem
from compas_dem.problem import Rotation
from compas_dem.problem import Solver
from compas_dem.problem import SurfaceLoad
from compas_dem.problem import Translation
from compas_dem.templates import ArchTemplate
from compas_dem.viewer import DEMViewer

HERE = pathlib.Path(__file__).parent

# =============================================================================
# Model
# =============================================================================

template: ArchTemplate = ArchTemplate(rise=4.393, span=21.213, thickness=0.5, depth=3.0, n=40)
model: BlockModel = BlockModel.from_template(template)

# Contacts are the interfaces the solvers work on; tolerance is the gap below which
# two faces are considered touching, minimum_area discards slivers.
model.compute_contacts(tolerance=0.001, minimum_area=0.01)

CROWN = 20  # blocks run 0..39 along the arch, so this is roughly the crown

# =============================================================================
# Material
# =============================================================================
# Stone.from_predefined_material(name) loads stiffness, Poisson and a default density
# from the built-in catalogue ("LimeStone", "Concrete C20/25"; matched case-insensitively).
# Stone(density=..., fck=..., Ecm=...) builds one from scratch instead.

limestone: Stone = Stone.from_predefined_material("LimeStone")
limestone.density = 2000  # kg/m3 — override the catalogue default

model.add_material(limestone)
# Assign to *every* element, supports included: body forces are mass-scaled, so an
# element without a density raises when the loads are resolved.
model.assign_material(limestone, elements=list(model.elements()))

# =============================================================================
# Supports — supports belong to the model, not to the problem
# =============================================================================
# Every solver reads block.is_support, so the same supports apply to every problem
# defined over this model. Use problem.inspect_model(model) to look up indices.

model.add_supports([0, 39])  # the two springing blocks

# add_support / remove_support / clear_supports flag them one at a time:
model.add_support(1)
model.remove_support(1)

print(f"supports: {[block.graphnode for block in model.supports()]}")
print(f"free blocks: {len(list(model.blocks()))} of {len(list(model.elements()))}")

# =============================================================================
# Problem — contact and joint behaviour
# =============================================================================

problem = Problem(model, name="live + fill + seismic + settlement")

# set_contact_model: string-keyed contact law. "MohrCoulomb" takes either phi
# (friction angle, degrees) or mu (tan phi), plus c (cohesion) and t_c (tension cutoff).
problem.set_contact_model("MohrCoulomb", phi=30, c=0)

# set_joint_model: linear normal/tangential interface stiffness [N/m].
problem.set_joint_model(kn=10e10, kt=10e7)

# =============================================================================
# Boundary conditions — typed objects, built standalone and registered
# =============================================================================
# A boundary condition is either a Load or a Displacement, and each is its own
# class. Build one, then hand it to problem.add(). There is no second way in, and
# nothing to select or reorder afterwards: every boundary condition registered on
# a problem is applied. A different combination means a different problem, which
# is what "settlement only" further down is for.
#
# Self-weight is not among them. Every solver applies it from the block densities,
# so there is no gravity switch to set — or to forget.

# =============================================================================
# Loads — the two ways to place a point load
# =============================================================================
# A point load anchors to a vertex or to a face centroid of the block. It never
# anchors to the block centroid: a centroidal force induces no moment, which makes
# it indistinguishable from a body force. The eccentric moment about the centroid
# is worked out from the resolved anchor position at solve time.

# ...at one vertex of the block mesh:
problem.add(PointLoad.at_vertex(block=12, vertex=0, force=[0, 0, -25000]))

# ...at the centre of one face:
problem.add(PointLoad.at_face(block=14, face=4, force=[0, 0, -25000]))

# Loads can be named; the name is a label for inspect_model, nothing more.
problem.add(PointLoad.at_face(block=CROWN, face=4, force=[0, 0, -151500], name="crown"))

# =============================================================================
# Loads — pressure, body force, prescribed movement
# =============================================================================

# A traction [N/m2] over one face; multiplied by the face area when resolved.
for index in range(8, 14):
    problem.add(SurfaceLoad(block=index, face=4, traction=[0, 0, -10000]))

# An acceleration [m/s2] applied to every block, mass-scaled into a force. 0.3 g
# sideways is the usual way to assess lateral capacity. loading_type="instantaneous"
# applies it at t=0 and releases it at the end, instead of ramping up and holding.
# This is on top of self-weight, so do not pass -9.81 here expecting gravity.
problem.add(BodyForce(acceleration=[0.3 * 9.81, 0, 0], loading_type="instantaneous"))

# A prescribed movement, per component. On a support block it overrides the fixity
# for the components it names, which is how a settlement analysis is set up;
# components left as None stay unconstrained.
problem.add(Translation(block=0, dx=0.02))
problem.add(Rotation(block=0, ry=0.001))

# Loads and prescribed movements partition the boundary conditions by type.
print(f"loads: {len(problem.loads)}, prescribed movements: {len(problem.displacements)}")

# Draw the model with its indices, loads and supports before committing to a solve.
# Note this halts the script when the viewer closes unless you pass kill=False.
# problem.inspect_model(show_blocks=True)

# =============================================================================
# Solvers — every backend is configured the same way, through Solver.<NAME>()
# =============================================================================

# Time-stepping dynamics. Give exactly two of duration / n_steps / dt; the third
# is derived. urf_threshold stops early once the unbalanced force ratio settles.
lmgc90 = Solver.LMGC90(duration=1, dt=0.001)

# Rigid block equilibrium, and its contact-relaxation refinement.
rbe = Solver.RBE(verbose=False)
cra = Solver.CRA(penalty=False, verbose=False)

# Limit analysis and piecewise rigid displacement. n_steps=1 runs the one-shot LP;
# n_steps>1 runs the incremental solve with open_tol as the contact opening tolerance.
bla = Solver.BLA(n_steps=1, associative=True, open_tol=1e-3, solver="CLARABEL")
prd = Solver.PRD(n_steps=1, open_tol=1e-3, solver="CLARABEL")

# =============================================================================
# Solve — the same problem, once per solver
# =============================================================================
# set_solver then solve; the model comes from the problem, so solve() takes no arguments.
# Each call returns its own Results object, so they can be compared and overlaid.
# Solving also records the result on the analysis this problem belongs to.
#
# Not every solver can apply every boundary condition. CRA and RBE resolve
# self-weight against contact forces and have no mechanism for applied loads or
# prescribed movements, so they refuse a problem carrying them rather than
# returning a result for a different problem than the one set up. That is why they
# are used on the self-weight problem below, not on this one.

solutions = {}

problem.set_solver(bla)
solutions["BLA"] = problem.solve()

problem.set_solver(lmgc90)
solutions["LMGC90"] = problem.solve()

problem.set_solver(prd)  # needs compas_pr3d
solutions["PRD"] = problem.solve()

# Self-weight alone, which is what CRA and RBE are for.
self_weight = Problem(model, name="self-weight")
self_weight.set_contact_model("MohrCoulomb", phi=30, c=0)

self_weight.set_solver(rbe)
solutions["RBE"] = self_weight.solve()

# self_weight.set_solver(cra)  # needs compas_cra + the ipopt executable; slowest of the five
# solutions["CRA"] = self_weight.solve()

# =============================================================================
# Results
# =============================================================================
# Results are standalone: keyed by block index and contact edge, serializable on
# their own, and they never write back into the model.

for name, result in solutions.items():
    print(f"\n{name}: {result.metadata.get('solver_status', 'n/a')}  mu={result.metadata.get('mu')}")
    for edge in result.edges():
        print(f"  contact {edge}: |F| = {result.force_magnitude(edge):.1f} N")
        print(f"  resultant {edge}: {result.resultant_global(edge)}")
        break
    for block in model.supports():
        print(f"  support {block.graphnode} displacement: {result.displacement(block.graphnode)}")

compas.json_dump(data=solutions["BLA"], fp=HERE / "dem_new_features_result.json")

# =============================================================================
# Analysis — one model, its problems, serialized together
# =============================================================================
# A problem holds its model as a live object, but writes it out as a guid only, so
# dumping a problem on its own would leave it unbound. Analysis is the container
# that holds the model alongside them: the geometry is written once, and on load
# the real model is handed back to every problem so each can solve straight away.
# The model and the problems are independent; the results are owned by the analysis.

analysis = Analysis(model, name="arch study")
analysis.add_problem(problem)
analysis.add_problem(self_weight)

# A second problem over the same model — still only one copy of the geometry on
# disk. This is what replaces picking a subset of boundary conditions to solve:
# a different combination is a different problem.
settlement_only = Problem(model, name="settlement only")
settlement_only.set_contact_model("MohrCoulomb", phi=30, c=0)
settlement_only.add(Translation(block=0, dx=0.05))
settlement_only.set_solver(Solver.BLA(n_steps=50))
analysis.add_problem(settlement_only)

PATH = HERE / "dem_new_features_analysis.json"
compas.json_dump(data=analysis, fp=PATH)

# =============================================================================
# ...and load it back
# =============================================================================

reloaded: Analysis = compas.json_load(PATH)

print(f"\nanalysis '{reloaded.name}': {len(reloaded.problems)} problems")
print(f"  model: {len(list(reloaded.model.elements()))} blocks, {len(list(reloaded.model.supports()))} supports")

for reloaded_problem in reloaded.problems:
    # .model resolves because Analysis handed the real model back on load — there is
    # nothing to re-link by hand.
    linked = reloaded_problem.model is reloaded.model
    solved = reloaded.results_for(reloaded_problem) is not None
    print(f"  '{reloaded_problem.name}': {len(reloaded_problem.boundary_conditions)} BCs, model linked = {linked}, results kept = {solved}")

# So the reloaded problem is immediately solvable:
# result = reloaded.problems[0].solve()

# =============================================================================
# Visualize — overlay every solution in one scene
# =============================================================================
# Each solution becomes its own toggleable group. The force scale is computed from
# the first one and reused, so arrow lengths stay comparable between solvers.

viewer = DEMViewer(model)
viewer.setup()

for name, result in solutions.items():
    result.displacement_scale = 1.0  # amplify the deformed shape without touching the stored values
    viewer.add_solution(result, name=name, scale=0.5)

viewer.show()
