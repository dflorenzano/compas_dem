import os

import compas
from compas_dem.analysis.resolve import resolve_centroidal_loads
from compas_dem.models import Analysis
from compas_dem.problem import Solver

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = next(p for p in analysis.problems if p.name == "Point load")

print(f"Problem loaded with {resolve_centroidal_loads(analysis.model, problem.boundary_conditions)[14]}")

# CRA and RBE cannot apply loads; use a solver that can.
problem.set_solver(Solver.LMGC90(duration=1.0, n_steps=100, urf_threshold=0.001))
result = problem.solve()

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))
