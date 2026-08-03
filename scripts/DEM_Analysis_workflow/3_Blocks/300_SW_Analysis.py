import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import Solver

HERE = os.path.dirname(__file__)

# The analysis carries the model and the problem together, so the problem is
# already bound to its model and can be solved straight away.
analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = analysis.problems[0]

problem.set_solver(Solver.LMGC90(n_steps=100, dt=0.001))
result = problem.solve()

# Solving records the results on the analysis, so dumping the analysis persists
# the model, the problem and its results as one object.
compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

# viewer = DEMViewer(analysis.model)
# viewer.add_solution(result, scale=0.5)
# viewer.show()
