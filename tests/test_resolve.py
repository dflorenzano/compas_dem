"""Numeric checks on the one place that turns typed boundary conditions into
centroidal forces, moments and prescribed movements.

The ``unit_boxes`` fixture is two stacked 1 m cubes of density 2000 kg/m³, so every
block has a mass of exactly 2000 kg and every face an area of exactly 1 m².
"""

import pytest
from compas_dem.analysis.resolve import resolve_centroidal_displacements
from compas_dem.analysis.resolve import resolve_centroidal_loads
from compas_dem.problem import BodyForce
from compas_dem.problem import PointLoad
from compas_dem.problem import Rotation
from compas_dem.problem import SurfaceLoad
from compas_dem.problem import Translation


def approx(vector):
    return pytest.approx(list(vector), abs=1e-9)


# =============================================================================
# Loads
# =============================================================================


def test_body_force_scales_with_block_mass(unit_boxes, block_indices):
    loads = resolve_centroidal_loads(unit_boxes, [BodyForce(acceleration=[1.0, 0, 0])])
    for idx in block_indices:
        # 2000 kg * 1 m/s2
        assert approx(loads[idx]["force"]) == [2000.0, 0.0, 0.0]
        assert approx(loads[idx]["moment"]) == [0.0, 0.0, 0.0]


def test_point_load_at_vertex_produces_eccentric_moment(unit_boxes, block_indices):
    lower = block_indices[0]
    # Vertex 0 of the lower cube is at (-0.5, -0.5, 0.0); its centroid is (0, 0, 0.5).
    # lever = (-0.5, -0.5, -0.5), force = (0, 0, -1000) -> moment = lever x force.
    loads = resolve_centroidal_loads(unit_boxes, [PointLoad.at_vertex(block=lower, vertex=0, force=[0, 0, -1000])])
    assert approx(loads[lower]["force"]) == [0.0, 0.0, -1000.0]
    assert approx(loads[lower]["moment"]) == [500.0, -500.0, 0.0]


def test_surface_load_is_a_traction_scaled_by_face_area(unit_boxes, block_indices):
    lower = block_indices[0]
    # Face 0 is the bottom face: centre (0, 0, 0), area 1.0. lever = (0, 0, -0.5).
    loads = resolve_centroidal_loads(unit_boxes, [SurfaceLoad(block=lower, face=0, traction=[100.0, 0, 0])])
    assert approx(loads[lower]["force"]) == [100.0, 0.0, 0.0]
    assert approx(loads[lower]["moment"]) == [0.0, -50.0, 0.0]


def test_loads_on_different_blocks_do_not_leak(unit_boxes, block_indices):
    lower, upper = block_indices
    loads = resolve_centroidal_loads(unit_boxes, [PointLoad.at_face(block=upper, face=0, force=[0, 0, -1000])])
    assert approx(loads[lower]["force"]) == [0.0, 0.0, 0.0]
    assert approx(loads[upper]["force"]) == [0.0, 0.0, -1000.0]


def test_loads_are_summed(unit_boxes, block_indices):
    lower = block_indices[0]
    loads = resolve_centroidal_loads(
        unit_boxes,
        [
            PointLoad.at_face(block=lower, face=0, force=[0, 0, -1000]),
            PointLoad.at_face(block=lower, face=0, force=[0, 0, -250]),
        ],
    )
    assert approx(loads[lower]["force"]) == [0.0, 0.0, -1250.0]


def test_loading_types_are_split_but_also_totalled(unit_boxes, block_indices):
    lower = block_indices[0]
    loads = resolve_centroidal_loads(
        unit_boxes,
        [
            PointLoad.at_face(block=lower, face=0, force=[0, 0, -1000], loading_type="ramp"),
            PointLoad.at_face(block=lower, face=0, force=[0, 0, -250], loading_type="instantaneous"),
        ],
    )
    by_type = loads[lower]["by_loading_type"]
    assert approx(by_type["ramp"]["force"]) == [0.0, 0.0, -1000.0]
    assert approx(by_type["instantaneous"]["force"]) == [0.0, 0.0, -250.0]
    assert approx(loads[lower]["force"]) == [0.0, 0.0, -1250.0]


def test_displacements_are_ignored_by_the_load_resolver(unit_boxes, block_indices):
    """The full problem.boundary_conditions list is passed in, so the filter matters."""
    lower = block_indices[0]
    loads = resolve_centroidal_loads(unit_boxes, [Translation(block=lower, dx=1.0), Rotation(block=lower, rz=1.0)])
    assert approx(loads[lower]["force"]) == [0.0, 0.0, 0.0]


def test_self_weight_is_not_applied_by_the_resolver(unit_boxes, block_indices):
    """Self-weight is each solver's own business; the resolver only does applied loads."""
    loads = resolve_centroidal_loads(unit_boxes, [])
    for idx in block_indices:
        assert approx(loads[idx]["force"]) == [0.0, 0.0, 0.0]


# =============================================================================
# Load errors
# =============================================================================


def test_load_on_missing_block_is_rejected(unit_boxes):
    with pytest.raises(ValueError, match="references block 999"):
        resolve_centroidal_loads(unit_boxes, [PointLoad.at_face(block=999, face=0, force=[0, 0, -1])])


def test_point_load_on_missing_vertex_is_rejected(unit_boxes, block_indices):
    with pytest.raises(ValueError, match="anchored to vertex 99"):
        resolve_centroidal_loads(unit_boxes, [PointLoad.at_vertex(block=block_indices[0], vertex=99, force=[0, 0, -1])])


def test_point_load_on_missing_face_is_rejected(unit_boxes, block_indices):
    with pytest.raises(ValueError, match="anchored to face 99"):
        resolve_centroidal_loads(unit_boxes, [PointLoad.at_face(block=block_indices[0], face=99, force=[0, 0, -1])])


def test_surface_load_on_missing_face_is_rejected(unit_boxes, block_indices):
    with pytest.raises(ValueError, match="face 99, which does not exist"):
        resolve_centroidal_loads(unit_boxes, [SurfaceLoad(block=block_indices[0], face=99, traction=[0, 0, -1])])


# =============================================================================
# Displacements
# =============================================================================


def test_translation_resolves_per_component(unit_boxes, block_indices):
    lower = block_indices[0]
    disps = resolve_centroidal_displacements([Translation(block=lower, dx=0.5)])
    assert disps[lower]["translation"] == [0.5, None, None]
    assert disps[lower]["rotation"] == [None, None, None]


def test_translation_and_rotation_on_one_block_merge(unit_boxes, block_indices):
    lower = block_indices[0]
    disps = resolve_centroidal_displacements([Translation(block=lower, dx=0.5), Rotation(block=lower, rz=0.01)])
    assert disps[lower]["translation"] == [0.5, None, None]
    assert disps[lower]["rotation"] == [None, None, 0.01]


def test_later_displacement_overrides_earlier_on_the_same_component(unit_boxes, block_indices):
    lower = block_indices[0]
    disps = resolve_centroidal_displacements([Translation(block=lower, dx=0.5), Translation(block=lower, dx=0.9, dy=0.1)])
    assert disps[lower]["translation"] == [0.9, 0.1, None]


def test_loads_are_ignored_by_the_displacement_resolver(unit_boxes, block_indices):
    disps = resolve_centroidal_displacements([PointLoad.at_face(block=block_indices[0], face=0, force=[0, 0, -1])])
    assert disps == {}


def test_unconstrained_blocks_get_no_entry(unit_boxes, block_indices):
    disps = resolve_centroidal_displacements([Translation(block=block_indices[0], dx=0.5)])
    assert block_indices[1] not in disps
