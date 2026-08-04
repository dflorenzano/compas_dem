from compas.geometry import Vector
from compas_cgal.measure import mesh_volume
from compas_dem.problem.boundary_condition import LOADING_TYPES
from compas_dem.problem.boundary_condition import BodyForce
from compas_dem.problem.boundary_condition import Displacement
from compas_dem.problem.boundary_condition import Load
from compas_dem.problem.boundary_condition import Moment
from compas_dem.problem.boundary_condition import PointLoad
from compas_dem.problem.boundary_condition import Rotation
from compas_dem.problem.boundary_condition import SurfaceLoad
from compas_dem.problem.boundary_condition import Translation


def _element_mass(element) -> float:
    """Return the mass of any model element in [kg].

    Uses the element's `mass` property if available (Block), otherwise
    computes density × volume directly from `material` and `modelgeometry`.
    """
    if hasattr(element, "mass"):
        return element.mass
    if element.material is None or element.material.density is None:
        raise ValueError(f"Element at node {element.graphnode} ({type(element).__name__}) has no material with a density assigned.")
    volume = mesh_volume(element.modelgeometry.to_vertices_and_faces(True))
    return element.material.density * volume


def _as_list(boundary_conditions) -> list:
    """Accept either a single boundary condition or a collection of them."""
    if isinstance(boundary_conditions, (list, tuple)):
        return list(boundary_conditions)
    return [boundary_conditions]


def _anchor_point(block, load: PointLoad):
    """Resolve the application point of a point load against the block geometry.

    Raises
    ------
    ValueError
        If the anchored vertex or face does not exist on the block.
    """
    if load.anchor == "centroid":
        return list(block.point)
    if load.anchor == "point":
        return list(load.anchor_value)

    mesh = block.modelgeometry
    if load.anchor == "vertex":
        try:
            return mesh.vertex_coordinates(load.anchor_value)
        except KeyError:
            raise ValueError(f"Point load on block {load.block} is anchored to vertex {load.anchor_value}, which does not exist on that block.") from None
    try:
        return mesh.face_center(load.anchor_value)
    except KeyError:
        raise ValueError(f"Point load on block {load.block} is anchored to face {load.anchor_value}, which does not exist on that block.") from None


def resolve_centroidal_loads(model, boundary_conditions) -> dict:
    """Resolve the loads among the given boundary conditions to (force, moment) pairs at each block centroid.

    Handles body forces, point loads (anchored to a vertex or a face centroid), and
    surface loads (tractions converted to equivalent point loads at face centroids).
    Anything that is not a :class:`~compas_dem.problem.Load` is ignored, so the full
    ``problem.boundary_conditions`` list can be passed straight in.

    Self-weight is intentionally excluded — each solver applies it through its own
    mechanism, from the block material densities.

    Parameters
    ----------
    model : :class:`~compas_dem.models.BlockModel`
    boundary_conditions : :class:`~compas_dem.problem.BoundaryCondition` | list[:class:`~compas_dem.problem.BoundaryCondition`]
        The boundary condition(s) to resolve. Multiple loads are summed together.

    Returns
    -------
    dict[int, dict]
        ``{block_index: {"force": Vector, "moment": Vector, "by_loading_type": {str: {"force": Vector, "moment": Vector}}}}``

        ``force`` and ``moment`` are the totals over every loading type, which is what
        the static solvers apply. ``by_loading_type`` keeps the same totals split per
        loading type, so a time-stepping solver can give each its own time series
        instead of having to pick one for the whole block.

    Raises
    ------
    ValueError
        If a load references a block, vertex or face that does not exist in the model.
    """
    blocks = {block.graphnode: block for block in model.elements()}

    loads = {
        idx: {
            "force": Vector(0, 0, 0),
            "moment": Vector(0, 0, 0),
            "by_loading_type": {lt: {"force": Vector(0, 0, 0), "moment": Vector(0, 0, 0)} for lt in LOADING_TYPES},
        }
        for idx in blocks
    }

    def accumulate(idx: int, force: Vector, moment: Vector, loading_type: str) -> None:
        loads[idx]["force"] += force
        loads[idx]["moment"] += moment
        bucket = loads[idx]["by_loading_type"][loading_type]
        bucket["force"] += force
        bucket["moment"] += moment

    def require_block(idx: int, load):
        if idx not in blocks:
            raise ValueError(f"{type(load).__name__} references block {idx}, which does not exist in the model.")
        return blocks[idx]

    for bc in _as_list(boundary_conditions):
        if not isinstance(bc, Load):
            continue

        if isinstance(bc, BodyForce):
            a_vec = Vector(*bc.acceleration)
            for idx, block in blocks.items():
                accumulate(idx, a_vec * _element_mass(block), Vector(0, 0, 0), bc.loading_type)

        elif isinstance(bc, PointLoad):
            block = require_block(bc.block, bc)
            force = Vector(*bc.force)
            # A centroid anchor gives a zero lever arm, hence no moment.
            lever = Vector(*_anchor_point(block, bc)) - block.point
            accumulate(bc.block, force, lever.cross(force), bc.loading_type)

        elif isinstance(bc, Moment):
            require_block(bc.block, bc)
            accumulate(bc.block, Vector(0, 0, 0), Vector(*bc.moment), bc.loading_type)

        elif isinstance(bc, SurfaceLoad):
            block = require_block(bc.block, bc)
            mesh = block.modelgeometry
            if bc.face not in list(mesh.faces()):
                raise ValueError(f"Surface load on block {bc.block} references face {bc.face}, which does not exist on that block.")
            force = Vector(*bc.traction) * mesh.face_area(bc.face)
            lever = Vector(*mesh.face_center(bc.face)) - block.point
            accumulate(bc.block, force, lever.cross(force), bc.loading_type)

        else:
            raise TypeError(f"{type(bc).__name__} is a Load but resolve_centroidal_loads does not know how to resolve it.")

    return loads


def resolve_centroidal_displacements(boundary_conditions) -> dict:
    """Resolve the prescribed movements among the given boundary conditions, per block index.

    Anything that is not a :class:`~compas_dem.problem.Displacement` is ignored, so the
    full ``problem.boundary_conditions`` list can be passed straight in. Supports are
    not boundary conditions; they come from the model (``block.is_support``).

    Parameters
    ----------
    boundary_conditions : :class:`~compas_dem.problem.BoundaryCondition` | list[:class:`~compas_dem.problem.BoundaryCondition`]
        The boundary condition(s) to resolve. Movements on the same block are merged
        per component; a later boundary condition overrides an earlier one on the
        components it prescribes.

    Returns
    -------
    dict[int, dict]
        ``{block_index: {"translation": list, "rotation": list}}``
        Components are ``None`` where unconstrained.
    """
    displacements = {}

    for bc in _as_list(boundary_conditions):
        if not isinstance(bc, Displacement):
            continue

        if bc.block not in displacements:
            displacements[bc.block] = {"translation": [None, None, None], "rotation": [None, None, None]}

        if isinstance(bc, Translation):
            key = "translation"
        elif isinstance(bc, Rotation):
            key = "rotation"
        else:
            raise TypeError(f"{type(bc).__name__} is a Displacement but resolve_centroidal_displacements does not know how to resolve it.")

        for j, value in enumerate(bc.components):
            if value is not None:
                displacements[bc.block][key][j] = value

    return displacements
