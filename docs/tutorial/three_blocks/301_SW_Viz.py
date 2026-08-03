import os

import compas
from compas_dem.models import Analysis
from compas_dem.viewer import DEMViewer

# =============================================================================
# Load analysis
# =============================================================================

HERE = os.path.dirname(__file__)
analysis: Analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
problem = analysis.problems[0]
results = analysis.results_for(problem)

# =============================================================================
# Inspect block results
# =============================================================================
# Results are a standalone object keyed by block index and contact edge; they
# are never written back into the model.

for node in results.nodes():
    block_transformation = results.transformation(node)
    # print(f"Block {node} transformation:\n{block_transformation}\n")

for edge in results.edges():
    gap = results.gap(edge)
    magnitude = results.force_magnitude(edge)
    print(f"Edge {edge} gap: {gap}, force magnitude: {magnitude}")

# =============================================================================
# Visualize results
# =============================================================================

viewer = DEMViewer(analysis.model)
viewer.add_solution(results, scale=0.5)
viewer.show()
