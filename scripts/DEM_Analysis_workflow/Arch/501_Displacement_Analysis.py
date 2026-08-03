import os

import compas
from compas_dem.analysis.resolve import resolve_centroidal_displacements
from compas_dem.models import Analysis
from compas_dem.problem import Solver

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = next(p for p in analysis.problems if p.name == "Support settlement")

print(f"Problem loaded with {resolve_centroidal_displacements(problem.boundary_conditions)[0]}")

problem.set_solver(Solver.LMGC90(duration=1.0, n_steps=100, urf_threshold=0.001))
result = problem.solve()

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))
