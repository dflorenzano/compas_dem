import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import Problem
from compas_dem.viewer import DEMViewer

# =============================================================================
# Load model
# =============================================================================

HERE = os.path.dirname(__file__)
model = compas.json_load(os.path.join(HERE, "DEM_model.json"))

# =============================================================================
# Create Problem
# =============================================================================
# Supports are already flagged on the model in 100_init.py — they belong to the
# model, not to the problem. A problem carries boundary conditions, contact
# properties and the solver, nothing else.

problem = Problem(model, name="Self-weight")

# =============================================================================
# Add contact properties
# =============================================================================

problem.set_contact_model("MohrCoulomb", mu=0.5)

# =============================================================================
# Save analysis
# =============================================================================
# The analysis owns the model, its problems and their results, and writes the
# model exactly once. This single file replaces the old model/problem/results
# split, and every problem comes back already bound to its model.

analysis = Analysis(model, name="Barrel vault")
analysis.add_problem(problem)

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

# =============================================================================
# Visualize problem
# =============================================================================

viewer = DEMViewer(model)
viewer.setup()
viewer.show()
