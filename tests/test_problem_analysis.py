"""The Analysis / Problem / Results ownership contract.

Model and problem are independent objects; results are owned. A problem holds its
model live but serializes it as a guid, and the analysis is what writes the model
once and hands it back on load.
"""

import compas
import pytest
from compas_dem.models import Analysis
from compas_dem.models import BlockModel
from compas_dem.problem import BodyForce
from compas_dem.problem import Moment
from compas_dem.problem import PointLoad
from compas_dem.problem import Problem
from compas_dem.problem import Results
from compas_dem.problem import Rotation
from compas_dem.problem import Solver
from compas_dem.problem import SurfaceLoad
from compas_dem.problem import Translation

# =============================================================================
# Registering boundary conditions
# =============================================================================


def test_add_returns_the_boundary_condition(unit_boxes):
    problem = Problem(unit_boxes)
    load = PointLoad.at_face(block=0, face=0, force=[0, 0, -1])
    assert problem.add(load) is load
    assert problem.boundary_conditions == [load]


def test_add_keeps_insertion_order(unit_boxes):
    problem = Problem(unit_boxes)
    first = problem.add(PointLoad.at_face(block=0, face=0, force=[0, 0, -1]))
    second = problem.add(Translation(block=0, dx=0.1))
    third = problem.add(BodyForce(acceleration=[1, 0, 0]))
    assert problem.boundary_conditions == [first, second, third]


def test_add_rejects_non_boundary_conditions(unit_boxes):
    problem = Problem(unit_boxes)
    with pytest.raises(TypeError, match="Expected a Load or a Displacement"):
        problem.add("gravity")


def test_add_rejects_the_same_object_twice(unit_boxes):
    problem = Problem(unit_boxes)
    load = PointLoad.at_face(block=0, face=0, force=[0, 0, -1])
    problem.add(load)
    with pytest.raises(ValueError, match="already registered"):
        problem.add(load)


def test_loads_and_displacements_partition_the_boundary_conditions(unit_boxes):
    problem = Problem(unit_boxes)
    load = problem.add(PointLoad.at_face(block=0, face=0, force=[0, 0, -1]))
    body = problem.add(BodyForce(acceleration=[1, 0, 0]))
    disp = problem.add(Translation(block=0, dx=0.1))
    assert problem.loads == [load, body]
    assert problem.displacements == [disp]


def test_solve_ordering_is_not_exposed(unit_boxes):
    """A different set of boundary conditions means a new problem, not a reorder."""
    problem = Problem(unit_boxes)
    assert not hasattr(problem, "set_solve_order")
    assert not hasattr(problem, "add_boundary_condition")


@pytest.mark.parametrize(
    "removed",
    [
        "add_boundary_condition",
        "set_solve_order",
        "add_supports_from_model",
        "add_support",
        "load_model",
        "add_gravity",
        "add_global_body_force",
        "add_displacement",
    ],
)
def test_removed_api_is_gone(unit_boxes, removed):
    """These have no replacement: they were duplication, dead code, or model-level."""
    assert not hasattr(Problem(unit_boxes), removed)


@pytest.mark.parametrize(
    "call, expected",
    [
        (lambda p: p.add_point_load_at_vertex(block=0, vertex=0, force=[0, 0, -1]), PointLoad),
        (lambda p: p.add_point_load_at_face(block=0, face=0, force=[0, 0, -1]), PointLoad),
        (lambda p: p.add_point_load_at_point(block=0, point=[1, 2, 3], force=[0, 0, -1]), PointLoad),
        (lambda p: p.add_point_load_at_centroid(block=0, force=[0, 0, -1]), PointLoad),
        (lambda p: p.add_moment(block=0, moment=[0, 1, 0]), Moment),
        (lambda p: p.add_surface_load(block=0, face=0, traction=[0, 0, -1]), SurfaceLoad),
        (lambda p: p.add_body_force(acceleration=[1, 0, 0]), BodyForce),
        (lambda p: p.add_translation(block=0, dx=0.1), Translation),
        (lambda p: p.add_rotation(block=0, rz=0.1), Rotation),
    ],
)
def test_problem_helper_builds_registers_and_returns(unit_boxes, call, expected):
    """The helpers are sugar over the classes: they build, register, and hand back."""
    problem = Problem(unit_boxes)
    bc = call(problem)
    assert isinstance(bc, expected)
    assert problem.boundary_conditions == [bc]


def test_problem_helpers_take_no_boundary_condition_kwarg(unit_boxes):
    """The old footgun: a boundary_condition= kwarg that raised if you forgot it."""
    import inspect

    problem = Problem(unit_boxes)
    helpers = [n for n in dir(problem) if n.startswith("add_") and n not in ("add_problem",)]
    assert helpers, "expected the convenience helpers to exist"
    for name in helpers:
        params = inspect.signature(getattr(problem, name)).parameters
        assert "boundary_condition" not in params, f"{name} still takes boundary_condition="


def test_problem_helper_matches_the_class_it_wraps(unit_boxes):
    """A helper must not be a second implementation -- same data as the class."""
    direct = PointLoad.at_face(block=3, face=2, force=[0, 0, -5000], loading_type="instantaneous")
    viahelper = Problem(unit_boxes).add_point_load_at_face(block=3, face=2, force=[0, 0, -5000], loading_type="instantaneous")
    assert viahelper.__data__ == direct.__data__


def test_every_load_type_is_still_reachable(unit_boxes):
    """The API was deduplicated, not reduced: no load type was dropped.

    compas_dem keeps the full toolset; narrowing what a user is offered is the
    downstream plugin's job, not the library's.
    """
    problem = Problem(unit_boxes)
    for bc in [
        PointLoad.at_vertex(block=0, vertex=0, force=[0, 0, -1]),
        PointLoad.at_face(block=0, face=0, force=[0, 0, -1]),
        PointLoad.at_point(block=0, point=[1, 2, 3], force=[0, 0, -1]),
        PointLoad.at_centroid(block=0, force=[0, 0, -1]),
        Moment(block=0, moment=[0, 1, 0]),
        SurfaceLoad(block=0, face=0, traction=[0, 0, -1]),
        BodyForce(acceleration=[1, 0, 0]),
        Translation(block=0, dx=0.1),
        Rotation(block=0, rz=0.1),
    ]:
        problem.add(bc)
    assert len(problem.loads) == 7
    assert len(problem.displacements) == 2


# =============================================================================
# Model binding
# =============================================================================


def test_problem_holds_the_live_model_object(unit_boxes):
    problem = Problem(unit_boxes)
    assert problem.model is unit_boxes
    assert problem.model_guid == str(unit_boxes.guid)


def test_problem_does_not_serialize_the_model(unit_boxes):
    problem = Problem(unit_boxes)
    payload = compas.json_dumps(problem)
    assert "BlockModel" not in payload
    assert str(unit_boxes.guid) in payload


def test_problem_deserialized_alone_is_unbound(unit_boxes):
    problem = compas.json_loads(compas.json_dumps(Problem(unit_boxes)))
    assert problem.model_guid == str(unit_boxes.guid)
    with pytest.raises(ValueError, match="not bound to a model"):
        problem.model


def test_unbound_problem_refuses_to_solve(unit_boxes):
    problem = Problem(unit_boxes)
    problem.set_solver(Solver.CRA())
    problem = compas.json_loads(compas.json_dumps(problem))
    with pytest.raises(ValueError, match="not bound to a model"):
        problem.solve()


def test_binding_a_different_model_is_rejected(unit_boxes):
    problem = Problem(unit_boxes)
    with pytest.raises(ValueError, match="does not match the model this problem was defined over"):
        problem._bind_model(BlockModel())


# =============================================================================
# Analysis
# =============================================================================


def test_analysis_adopts_the_model_of_its_first_problem(unit_boxes):
    analysis = Analysis()
    analysis.add_problem(Problem(unit_boxes))
    assert analysis.model is unit_boxes


def test_analysis_rejects_a_problem_over_another_model(unit_boxes):
    analysis = Analysis(unit_boxes)
    with pytest.raises(ValueError, match="An analysis covers one model"):
        analysis.add_problem(Problem(BlockModel()))


def test_analysis_roundtrip_rebinds_the_model_into_every_problem(unit_boxes):
    analysis = Analysis(unit_boxes, name="arch")
    first = analysis.add_problem(Problem(unit_boxes, name="SW"))
    second = analysis.add_problem(Problem(unit_boxes, name="ULS"))
    second.add(PointLoad.at_vertex(block=0, vertex=0, force=[0, 0, -1000]))

    other = compas.json_loads(compas.json_dumps(analysis))

    assert other.name == "arch"
    assert [p.name for p in other.problems] == ["SW", "ULS"]
    assert str(other.model.guid) == str(unit_boxes.guid)
    for problem in other.problems:
        # The rebound model is the analysis's own object, not a per-problem copy.
        assert problem.model is other.model
    assert [str(p.guid) for p in other.problems] == [str(first.guid), str(second.guid)]
    assert other.problems[1].boundary_conditions[0].__data__ == second.boundary_conditions[0].__data__


def test_analysis_writes_the_model_exactly_once(unit_boxes):
    analysis = Analysis(unit_boxes)
    for _ in range(3):
        analysis.add_problem(Problem(unit_boxes))
    assert compas.json_dumps(analysis).count('"dtype": "compas_dem.models/BlockModel"') == 1


def test_results_are_owned_by_the_analysis(unit_boxes):
    analysis = Analysis(unit_boxes)
    problem = analysis.add_problem(Problem(unit_boxes))
    assert analysis.results_for(problem) is None

    results = Results(model_id=str(unit_boxes.guid), problem_id=str(problem.guid))
    analysis._record_results(problem, results)

    assert analysis.results_for(problem) is results
    other = compas.json_loads(compas.json_dumps(analysis))
    assert other.results_for(other.problems[0]) is not None
    assert other.results_for(other.problems[0]).problem_id == str(problem.guid)


def test_solving_a_problem_in_an_analysis_records_its_results(unit_boxes, monkeypatch):
    """The recording hook, without needing a solver backend installed."""
    analysis = Analysis(unit_boxes)
    problem = analysis.add_problem(Problem(unit_boxes))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.CRA())

    sentinel = Results(model_id=str(unit_boxes.guid), problem_id=str(problem.guid))
    monkeypatch.setattr("compas_dem.analysis.cra.cra_solve", lambda *a, **kw: sentinel)

    assert problem.solve() is sentinel
    assert analysis.results_for(problem) is sentinel


def test_solving_a_standalone_problem_records_nothing(unit_boxes, monkeypatch):
    problem = Problem(unit_boxes)
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.CRA())
    sentinel = Results(model_id=str(unit_boxes.guid), problem_id=str(problem.guid))
    monkeypatch.setattr("compas_dem.analysis.cra.cra_solve", lambda *a, **kw: sentinel)
    assert problem.solve() is sentinel


# =============================================================================
# Solve guards
# =============================================================================


def test_solving_without_a_solver_is_rejected(unit_boxes):
    problem = Problem(unit_boxes)
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    with pytest.raises(ValueError, match="No solver configured"):
        problem.solve()


def test_solving_without_supports_is_rejected(unit_boxes):
    for block in unit_boxes.elements():
        block.is_support = False
    problem = Problem(unit_boxes)
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.CRA())
    with pytest.raises(ValueError, match="no supports defined"):
        problem.solve()


def test_solving_without_a_contact_model_is_rejected(unit_boxes):
    problem = Problem(unit_boxes)
    problem.set_solver(Solver.CRA())
    with pytest.raises(ValueError, match="No contact model defined"):
        problem.solve()


def test_cra_refuses_boundary_conditions_it_cannot_apply(unit_boxes):
    """CRA and RBE resolve self-weight only; dropping loads silently would lie."""
    problem = Problem(unit_boxes)
    problem.add(PointLoad.at_vertex(block=0, vertex=0, force=[0, 0, -1000]))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.CRA())
    with pytest.raises(ValueError, match="cannot apply the boundary conditions"):
        problem.solve()


def test_rbe_refuses_boundary_conditions_it_cannot_apply(unit_boxes):
    problem = Problem(unit_boxes)
    problem.add(Translation(block=0, dx=0.1))
    problem.set_contact_model("MohrCoulomb", mu=0.6)
    problem.set_solver(Solver.RBE())
    with pytest.raises(ValueError, match="cannot apply the boundary conditions"):
        problem.solve()
