"""Read back everything the BC demo wrote, from the single analysis file.

Run ``DEM_Boundary_Conditions_Demo.py`` first to produce ``dem_arch_analysis.json``.
"""

import pathlib

import compas
from compas_dem.analysis.resolve import resolve_centroidal_displacements
from compas_dem.analysis.resolve import resolve_centroidal_loads
from compas_dem.models import Analysis
from compas_dem.problem import Displacement
from compas_dem.problem import Load

RULE = "----------------------------------------------------------------"

# One file carries the model, its problems and their results, and the problems
# come back already bound to the model.
analysis: Analysis = compas.json_load(pathlib.Path(__file__).parent / "dem_arch_analysis.json")
model = analysis.model

loaded = next(p for p in analysis.problems if p.name == "Loads and settlement")
self_weight = next(p for p in analysis.problems if p.name == "Self-weight")

print(f"Analysis: {analysis.name} - Model: {model.guid} - {len(analysis.problems)} problems")
print(RULE)

for problem in analysis.problems:
    results = analysis.results_for(problem)
    status = "solved" if results else "not solved"
    print(f"Problem '{problem.name}' ({problem.guid}): {len(problem.boundary_conditions)} boundary conditions, {status}")

print(RULE)

# Boundary conditions are typed objects, so they can be filtered by what they are
# rather than by which named bucket they happened to be put in.
print(f"Loads on '{loaded.name}':")
for bc in loaded.loads:
    print(f"  {bc!r}  [{bc.loading_type}]")

print(f"Prescribed movements on '{loaded.name}':")
for bc in loaded.displacements:
    print(f"  {bc!r}")

print(f"'{self_weight.name}' carries {len(self_weight.boundary_conditions)} boundary conditions - self-weight is applied by the solver, not registered.")
print(RULE)

# The branch of the hierarchy is what decides how a boundary condition resolves.
assert all(isinstance(bc, Load) for bc in loaded.loads)
assert all(isinstance(bc, Displacement) for bc in loaded.displacements)

contact_properties = loaded.contact_properties
print("Contact properties:")
print(f"  Contact model phi: {contact_properties.contact_model.phi}")
print(f"  Contact model c:   {contact_properties.contact_model.c}")
print(f"  Joint model:       kn = {contact_properties.joint_model.kn}, kt = {contact_properties.joint_model.kt}")
print(RULE)

print("Supports are set on the model, not on the problem:")
print(f"  {[block.graphnode for block in model.supports()]}")
print(RULE)

# Both resolvers take the whole boundary condition list and ignore what is not
# theirs, so there is nothing to pre-filter.
print("Centroidal loads (block 10):")
print(f"  {resolve_centroidal_loads(model, loaded.boundary_conditions)[10]}")

print("Centroidal displacements (block 0):")
print(f"  {resolve_centroidal_displacements(loaded.boundary_conditions)[0]}")
print(RULE)

results = analysis.results_for(self_weight)
if results:
    for edge in results.edges():
        print(f"Edge: {edge}")
        print(f"  Transformation:  {results.transformation(edge[0])}")
        print(f"  Contact polygon: {results.contact_polygon(edge)}")
        print(f"  Contact force:   {results.resultant_global(edge)}")
        break
