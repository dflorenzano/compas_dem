import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import PointLoad
from compas_dem.problem import Problem

HERE = os.path.dirname(__file__)

analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))

# A different set of boundary conditions means a new problem, not a reordering of
# an existing one. The analysis holds both problems over the same model.
problem = Problem(analysis.model, name="Point load")
problem.set_contact_model("MohrCoulomb", mu=0.5)

# A point load is anchored to a vertex or to a face centroid of the block; a load
# at the block centroid would produce no moment and be indistinguishable from a
# body force. Run inspect_model() below to check which face index you want.
problem.add(PointLoad.at_face(block=14, face=4, force=[0, 0, -50000.0]))

analysis.add_problem(problem)

compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

problem.inspect_model()
