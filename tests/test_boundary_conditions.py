import compas
import pytest
from compas_dem.problem import BodyForce
from compas_dem.problem import BoundaryCondition
from compas_dem.problem import Displacement
from compas_dem.problem import Load
from compas_dem.problem import Moment
from compas_dem.problem import PointLoad
from compas_dem.problem import Rotation
from compas_dem.problem import SurfaceLoad
from compas_dem.problem import Translation

# =============================================================================
# Hierarchy
# =============================================================================


@pytest.mark.parametrize(
    "bc",
    [
        PointLoad.at_vertex(block=0, vertex=0, force=[0, 0, -1]),
        PointLoad.at_centroid(block=0, force=[0, 0, -1]),
        SurfaceLoad(block=0, face=0, traction=[0, 0, -1]),
        BodyForce(acceleration=[1, 0, 0]),
        Moment(block=0, moment=[0, 1, 0]),
    ],
)
def test_loads_are_loads_and_not_displacements(bc):
    assert isinstance(bc, Load)
    assert isinstance(bc, BoundaryCondition)
    assert not isinstance(bc, Displacement)


@pytest.mark.parametrize(
    "bc",
    [
        Translation(block=0, dx=1.0),
        Rotation(block=0, rz=1.0),
    ],
)
def test_displacements_are_displacements_and_not_loads(bc):
    assert isinstance(bc, Displacement)
    assert isinstance(bc, BoundaryCondition)
    assert not isinstance(bc, Load)


def test_displacements_do_not_expose_load_methods():
    """The point of the split: a Displacement cannot be given a load."""
    disp = Translation(block=0, dx=1.0)
    assert not hasattr(disp, "add_point_load")
    assert not hasattr(disp, "add_surface_load")
    assert not hasattr(disp, "add_global_body_force")


def test_gravity_is_not_an_api():
    """Self-weight is unconditional, so there is no gravity switch to get wrong."""
    import compas_dem.problem as problem_module

    assert not hasattr(problem_module, "Gravity")
    assert not hasattr(BoundaryCondition, "add_gravity")
    assert not hasattr(BoundaryCondition(), "g")


# =============================================================================
# Point loads
# =============================================================================


def test_point_load_at_vertex():
    load = PointLoad.at_vertex(block=7, vertex=3, force=[0, 0, -5000])
    assert load.block == 7
    assert load.anchor == "vertex"
    assert load.anchor_value == 3
    assert load.force == [0, 0, -5000]
    assert load.loading_type == "ramp"


def test_point_load_at_face():
    load = PointLoad.at_face(block=7, face=2, force=[0, 0, -5000], loading_type="instantaneous")
    assert load.anchor == "face"
    assert load.anchor_value == 2
    assert load.loading_type == "instantaneous"


def test_point_load_at_point():
    load = PointLoad.at_point(block=7, point=[1, 2, 3], force=[0, 0, -5000])
    assert load.anchor == "point"
    assert load.anchor_value == [1.0, 2.0, 3.0]


def test_point_load_at_centroid():
    load = PointLoad.at_centroid(block=7, force=[0, 0, -5000])
    assert load.anchor == "centroid"
    assert load.anchor_value is None


def test_moment_is_a_load():
    m = Moment(block=7, moment=[0, 5000, 0])
    assert isinstance(m, Load)
    assert m.moment == [0, 5000, 0]


def test_point_load_rejects_unknown_anchor():
    with pytest.raises(ValueError, match="anchor must be one of"):
        PointLoad(block=0, force=[0, 0, -1], anchor="edge", anchor_value=0)


@pytest.mark.parametrize(
    "anchor, value, message",
    [
        ("vertex", [1, 2, 3], "needs an integer index"),
        ("face", None, "needs an integer index"),
        ("point", 4, "needs \\[x, y, z\\]"),
        ("point", [1, 2], "needs \\[x, y, z\\]"),
        ("centroid", 4, "takes no value"),
    ],
)
def test_point_load_rejects_mismatched_anchor_value(anchor, value, message):
    with pytest.raises(ValueError, match=message):
        PointLoad(block=0, force=[0, 0, -1], anchor=anchor, anchor_value=value)


def test_load_rejects_unknown_loading_type():
    with pytest.raises(ValueError, match="loading_type must be one of"):
        PointLoad.at_face(block=0, face=0, force=[0, 0, -1], loading_type="sinusoidal")


# =============================================================================
# Displacements
# =============================================================================


def test_translation_components_keep_unconstrained_dofs_as_none():
    assert Translation(block=0, dx=0.5).components == [0.5, None, None]


def test_rotation_components_keep_unconstrained_dofs_as_none():
    assert Rotation(block=0, rz=0.01).components == [None, None, 0.01]


def test_translation_with_no_components_is_rejected():
    with pytest.raises(ValueError, match="at least one of dx, dy, dz"):
        Translation(block=0)


def test_rotation_with_no_components_is_rejected():
    with pytest.raises(ValueError, match="at least one of rx, ry, rz"):
        Rotation(block=0)


# =============================================================================
# Serialization
# =============================================================================


@pytest.mark.parametrize(
    "bc",
    [
        PointLoad.at_vertex(block=3, vertex=1, force=[1, 2, 3], loading_type="instantaneous", name="crane"),
        PointLoad.at_face(block=3, face=1, force=[1, 2, 3]),
        PointLoad.at_point(block=3, point=[1.5, 2.5, 3.5], force=[1, 2, 3]),
        PointLoad.at_centroid(block=3, force=[1, 2, 3]),
        Moment(block=3, moment=[0, 5000, 0]),
        SurfaceLoad(block=4, face=2, traction=[0, 0, -10000], name="snow"),
        BodyForce(acceleration=[1.96, 0, 0], loading_type="instantaneous"),
        Translation(block=0, dx=0.5, dz=-0.01),
        Rotation(block=1, ry=0.02),
    ],
)
def test_boundary_condition_roundtrips(bc):
    other = compas.json_loads(compas.json_dumps(bc))
    assert type(other) is type(bc)
    assert other.__data__ == bc.__data__
    assert str(other.guid) == str(bc.guid)
    assert other._name == bc._name
