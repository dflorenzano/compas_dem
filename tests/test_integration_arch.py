"""End-to-end runs of the workflow the example scripts use.

Modelled on ``scripts/DEM_Analysis_Examples/dem_arch_cra.py`` and
``scripts/DEM_Analysis_workflow/DEM_BC_Demo``: build a template, compute contacts,
flag supports, assign material, set up a problem, solve, serialize.

The solver backends are optional dependencies, so each test skips when its backend
is absent rather than failing.
"""

import shutil

import compas
import pytest
from compas_dem.material import Stone
from compas_dem.models import Analysis
from compas_dem.models import BlockModel
from compas_dem.problem import BodyForce
from compas_dem.problem import PointLoad
from compas_dem.problem import Problem
from compas_dem.problem import Solver
from compas_dem.problem import Translation
from compas_dem.templates import ArchTemplate

# CRA and RBE shell out to the ipopt executable through pyomo. The conda-forge
# ipopt 3.14.9 build ships the library without the binary, so check for the binary.
needs_ipopt = pytest.mark.skipif(shutil.which("ipopt") is None, reason="the ipopt executable is not on PATH")


def _has_module(name: str) -> bool:
    try:
        __import__(name)
    except Exception:
        return False
    return True


needs_lmgc90 = pytest.mark.skipif(not _has_module("compas_lmgc90"), reason="compas_lmgc90 is not installed")


@pytest.fixture(scope="module")
def arch() -> BlockModel:
    """A small arch with contacts, supports and material — the example script setup."""
    model = BlockModel.from_template(ArchTemplate(rise=3, span=10, thickness=0.25, depth=0.5, n=11))
    model.compute_contacts(tolerance=0.001)
    for element in model.elements():
        if model.graph.degree(element.graphnode) == 1:
            element.is_support = True
    stone = Stone(density=2000)
    model.add_material(stone)
    model.assign_material(stone, elements=list(model.elements()))
    return model


@needs_ipopt
@pytest.mark.parametrize("solver_name", ["CRA", "RBE"])
def test_self_weight_arch_solves(arch, solver_name):
    problem = Problem(arch, name="SW")
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(getattr(Solver, solver_name)())

    results = problem.solve()

    assert results.model_id == str(arch.guid)
    assert results.problem_id == str(problem.guid)
    assert list(results.edges())


@needs_ipopt
def test_analysis_owns_results_and_survives_a_roundtrip(arch, tmp_path):
    analysis = Analysis(arch, name="arch")
    problem = analysis.add_problem(Problem(arch, name="SW"))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.RBE())

    results = problem.solve()
    assert analysis.results_for(problem) is results

    path = tmp_path / "analysis.json"
    compas.json_dump(analysis, path)
    reloaded = compas.json_load(path)

    problem = reloaded.problems[0]
    assert problem.model is reloaded.model
    assert reloaded.results_for(problem) is not None
    # Rebound on load, so it solves again without any manual model handling.
    assert problem.solve().model_id == str(arch.guid)


@needs_ipopt
def test_cra_refuses_an_arch_carrying_loads(arch):
    """The BC demo script solved this exact setup with CRA and silently lost the loads."""
    problem = Problem(arch, name="ULS")
    problem.add(PointLoad.at_face(block=5, face=2, force=[0, 0, -100000]))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.CRA())

    with pytest.raises(ValueError, match="cannot apply the boundary conditions"):
        problem.solve()


@needs_lmgc90
def test_loaded_arch_solves_with_lmgc90(arch):
    problem = Problem(arch, name="ULS")
    problem.add(PointLoad.at_face(block=5, face=2, force=[0, 0, -50000]))
    problem.add(BodyForce(acceleration=[0.98, 0, 0]))
    problem.add(Translation(block=0, dx=0.001))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_joint_model(kn=1e9, kt=5e8)
    problem.set_solver(Solver.LMGC90(duration=0.1, dt=0.001, verbose=100000))

    results = problem.solve()

    assert results.problem_id == str(problem.guid)
    assert list(results.edges())
