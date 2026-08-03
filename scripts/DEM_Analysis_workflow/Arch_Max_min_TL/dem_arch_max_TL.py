from compas_dem.material import Stone
from compas_dem.models import BlockModel
from compas_dem.problem import Problem
from compas_dem.problem import Rotation
from compas_dem.problem import Solver
from compas_dem.problem import Translation
from compas_dem.templates import ArchTemplate
from compas_dem.viewer import DEMViewer

# =============================================================================
# Template
# =============================================================================

template = ArchTemplate(rise=3, span=10, thickness=0.5, depth=0.5, n=50)

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

# =============================================================================
# Material
# =============================================================================
limestone = Stone.from_predefined_material("LimeStone")
model.add_material(limestone)
limestone.density = 2000
model.assign_material(limestone, elements=list(model.elements()))

# =============================================================================
# Problem
# =============================================================================
# Supports belong to the model, not to the problem.
model.add_support(block_index=49)

problem = Problem(model, name="Max thrust line")
problem.set_contact_model("MohrCoulomb", phi=40, c=0)

# Push the springing inwards while holding it against rotation. Components left
# as None would stay unconstrained, so the zeros here are deliberate.
problem.add(Translation(block=0, dx=-0.1))
problem.add(Rotation(block=0, rx=0.0, ry=0.0, rz=0.0))

problem.set_solver(Solver.LMGC90(n_steps=100, dt=0.01))
solution = problem.solve()
# =============================================================================
# Viz
# =============================================================================

viewer = DEMViewer(model)

viewer.setup()
viewer.add_solution(solution, scale=0.5)
viewer.show()
