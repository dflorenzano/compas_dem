import os

import compas
from compas_dem.models import Analysis
from compas_dem.problem import Problem
from compas_dem.problem import Translation
from compas_dem.viewer import DEMViewer

# =============================================================================
# Load analysis
# =============================================================================

HERE = os.path.dirname(__file__)
analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))

# =============================================================================
# Create Problem
# =============================================================================

problem = Problem(analysis.model, name="Support settlement")

# =============================================================================
# Add prescribed movement
# =============================================================================
# A prescribed movement on a support block overrides its fixity, per component:
# this is a 50 mm horizontal settlement of the springing. Components left as None
# stay unconstrained.

problem.add(Translation(block=0, dx=-0.05))

# =============================================================================
# Add contact properties
# =============================================================================

problem.set_contact_model("MohrCoulomb", mu=0.5)

# =============================================================================
# Save analysis
# =============================================================================

analysis.add_problem(problem)
compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

viewer = DEMViewer(analysis.model)
viewer.setup()
viewer.show()
