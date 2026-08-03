import os

import compas
from compas_dem.analysis.resolve import resolve_centroidal_displacements
from compas_dem.models import Analysis
from compas_dem.viewer import DEMViewer

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = next(p for p in analysis.problems if p.name == "Support settlement")

print(f"Support horizontal settlement is {resolve_centroidal_displacements(problem.boundary_conditions)[0]}")

viewer = DEMViewer(analysis.model)
viewer.add_solution(analysis.results_for(problem), scale=0.5)
viewer.show()
