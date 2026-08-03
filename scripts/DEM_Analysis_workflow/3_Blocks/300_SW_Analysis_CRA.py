import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import Solver

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = analysis.problems[0]

# CRA and RBE resolve self-weight against contact forces only. They refuse a
# problem carrying loads or prescribed movements rather than dropping them
# silently, which is fine here: this problem is self-weight alone.
problem.set_solver(Solver.CRA(verbose=True))
result = problem.solve()

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))
