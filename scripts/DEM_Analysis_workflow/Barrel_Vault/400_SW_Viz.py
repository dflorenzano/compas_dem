import os

import compas
from compas_dem.models import Analysis
from compas_dem.viewer import DEMViewer

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = analysis.problems[0]

viewer = DEMViewer(analysis.model)
viewer.add_solution(analysis.results_for(problem), scale=0.5)
viewer.show()
