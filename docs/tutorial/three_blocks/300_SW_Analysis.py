import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import Solver

# =============================================================================
# Load analysis
# =============================================================================
# The analysis carries the model and the problem together, so the problem comes
# back already bound to its model and can be solved straight away.

HERE = os.path.dirname(__file__)
analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = analysis.problems[0]

# =============================================================================
# Solve
# =============================================================================

problem.set_solver(Solver.LMGC90(n_steps=100, dt=0.001))
results = problem.solve()

# =============================================================================
# Save results
# =============================================================================
# Solving records the results on the analysis, so dumping the analysis persists
# the model, the problem and its results as one object.

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

# # # =============================================================================
# # # Visualize problem
# # # =============================================================================

# viewer = DEMViewer(analysis.model)
# viewer.add_solution(results, scale=0.5)
# viewer.show()
