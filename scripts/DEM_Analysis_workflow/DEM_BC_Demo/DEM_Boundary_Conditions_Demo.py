import pathlib

import compas
from compas_dem.material import Stone
from compas_dem.models import Analysis
from compas_dem.models import BlockModel
from compas_dem.problem import PointLoad
from compas_dem.problem import Problem
from compas_dem.problem import Solver
from compas_dem.problem import SurfaceLoad
from compas_dem.problem import Translation
from compas_dem.templates import ArchTemplate
from compas_dem.viewer import DEMViewer

# =============================================================================
# Template
# =============================================================================

template = ArchTemplate(rise=4.393, span=21.213, thickness=0.5, depth=3.0, n=15)

# =============================================================================
# Model
# =============================================================================

model = BlockModel.from_template(template)

# =============================================================================
# Interactions
# =============================================================================

model.compute_contacts(tolerance=0.001)

# =============================================================================
# Supports
# =============================================================================

for node in model.graph.nodes_where(degree=1):
    model.graph.node_element(node).is_support = True  # type: ignore

# ============================================================================
# Material
# ============================================================================

generic: Stone = Stone(density=2000)
model.add_material(generic)
model.assign_material(generic, elements=list(model.elements()))

# =============================================================================
# Problems
# =============================================================================
# Boundary conditions are objects, built standalone and registered with
# problem.add(). Every boundary condition on a problem is applied together, so a
# different set of them means a different problem — which is why the self-weight
# case below is its own problem rather than a named group inside this one.

loaded = Problem(model, name="Loads and settlement")
loaded.set_contact_model("MohrCoulomb", phi=35, c=0.0)
loaded.set_joint_model(kn=1e9, kt=5e8)

# A prescribed movement on a support block overrides its fixity, per component.
loaded.add(Translation(block=0, dx=0.5))

# A traction in [N/m2]; the resultant is the traction times the face area.
for index in range(3, 6):
    loaded.add(SurfaceLoad(block=index, face=4, traction=[0, 0, -10000]))

# Point loads anchor to a vertex or a face centroid, never to the block centroid:
# a centroidal force produces no moment and is just a body force.
loaded.add(PointLoad.at_face(block=10, face=4, force=[0, 0, -100000]))

# Self-weight is applied by every solver from the block densities. It is not a
# boundary condition, so this problem carries none at all.
self_weight = Problem(model, name="Self-weight")
self_weight.set_contact_model("MohrCoulomb", phi=35, c=0.0)

# =============================================================================
# Analysis
# =============================================================================
# One analysis holds the model, both problems and their results, and writes the
# model exactly once.

analysis = Analysis(model, name="Arch BC demo")
analysis.add_problem(loaded)
analysis.add_problem(self_weight)

# loaded.inspect_model()

# =============================================================================
# Solve
# =============================================================================
# CRA and RBE resolve self-weight against contact forces and have no mechanism
# for applied loads, so they refuse the loaded problem instead of quietly
# returning a result for a different problem than the one set up here.

self_weight.set_solver(Solver.CRA())
result_cra = self_weight.solve()

loaded.set_solver(Solver.LMGC90(duration=10.0, dt=0.001, verbose=100))
result_lmgc90 = loaded.solve()

# Solving records results on the analysis, so this one file carries the model,
# both problems and both sets of results.
compas.json_dump(data=analysis, fp=pathlib.Path(__file__).parent / "dem_arch_analysis.json")

# Viewer
viewer = DEMViewer(model)
# viewer.setup()
viewer.add_solution(result_cra, name="CRA (self-weight)", scale=0.5)
viewer.add_solution(result_lmgc90, name="LMGC90 (loaded)", scale=0.5)
viewer.show()
