import os

import compas
from compas_dem.material import Stone
from compas_dem.models import BlockModel
from compas_dem.templates import ArchTemplate
from compas_dem.viewer import DEMViewer

# =============================================================================
# Create a BlockModel from Template
# =============================================================================
template: ArchTemplate = ArchTemplate(rise=4.393, span=21.213, thickness=0.5, depth=3.0, n=30)
model: BlockModel = BlockModel.from_template(template)

# =============================================================================
# Compute contacts to populate the graph
# =============================================================================
model.compute_contacts()

# =============================================================================
# Flag supports
# =============================================================================
# Supports belong to the model, not to the problem: the solvers read
# block.is_support directly off the model.

for element in model.elements():
    if model.graph.degree(element.graphnode) == 1:
        element.is_support = True

# =============================================================================
# Add material and assign to blocks
# =============================================================================

elements = list(model.elements())

limestone = Stone.from_predefined_material("LimeStone")
model.add_material(limestone)
model.assign_material(limestone, elements=elements)

# =============================================================================
# Save model
# =============================================================================

HERE = os.path.dirname(__file__)
compas.json_dump(model, os.path.join(HERE, "DEM_model.json"))

# =============================================================================
# Visualise model
# =============================================================================

viewer = DEMViewer(model)
viewer.setup()
viewer.show()
