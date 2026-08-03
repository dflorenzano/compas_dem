from typing import Optional

from compas.data import Data

LOADING_TYPES = ("ramp", "instantaneous")
ANCHORS = ("vertex", "face")


def check_loading_type(loading_type: str) -> str:
    """Validate a loading type, returning it unchanged."""
    if loading_type not in LOADING_TYPES:
        raise ValueError(f"loading_type must be one of {LOADING_TYPES}, got {loading_type!r}.")
    return loading_type


def check_anchor(anchor: str) -> str:
    """Validate a point load anchor, returning it unchanged."""
    if anchor not in ANCHORS:
        raise ValueError(f"anchor must be one of {ANCHORS}, got {anchor!r}.")
    return anchor


class BoundaryCondition(Data):
    """Base class for everything that can be applied to a block model.

    A boundary condition is either a :class:`Load` or a :class:`Displacement`; this
    base class exists only so a problem can hold both in one list. It carries no
    load or displacement data of its own, and is not meant to be instantiated.

    Concrete boundary conditions are constructed standalone and then registered on a
    problem with :meth:`~compas_dem.problem.Problem.add`. They never hold a reference
    to the model: anything that needs geometry (a vertex position, a face area) is
    resolved against the model at solve time.

    Parameters
    ----------
    name : str, optional
        Name for this boundary condition. Used as a label when inspecting a problem.

    Examples
    --------
    >>> from compas_dem.problem import PointLoad, Translation
    >>> load = PointLoad.at_vertex(block=10, vertex=5, force=[0, 0, -5000])
    >>> support_settlement = Translation(block=0, dz=-0.01)
    """

    def __init__(self, name: Optional[str] = None) -> None:
        super().__init__(name=name)


# =============================================================================
# Loads
# =============================================================================


class Load(BoundaryCondition):
    """Base class for applied loads.

    Every load carries a ``loading_type``, which is the time-series shape the solver
    gives it. Static solvers apply the full value regardless; time-stepping solvers
    use it to build a per-block force history.

    Parameters
    ----------
    loading_type : str, optional
        ``"ramp"`` (default) grows from zero to the full value over the simulation
        and holds it; ``"instantaneous"`` applies the full value at t=0 and releases
        it at the end.
    name : str, optional
        Name for this load.

    Notes
    -----
    Self-weight is not a load. Every solver applies it unconditionally from the block
    material densities, so there is nothing to register and no way to switch it off.
    """

    def __init__(self, loading_type: str = "ramp", name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.loading_type = check_loading_type(loading_type)


class PointLoad(Load):
    """A concentrated force applied at a vertex or a face centroid of a block.

    A point load is always anchored to a feature of the block geometry, never to the
    block centroid: a force at the centroid produces no moment and is indistinguishable
    from a :class:`BodyForce`. The eccentric moment about the centroid is computed at
    solve time from the resolved anchor position.

    Use :meth:`at_vertex` or :meth:`at_face` rather than calling the constructor
    directly.

    Parameters
    ----------
    block : int
        Graph node index of the target block.
    force : list[float]
        Force vector [fx, fy, fz] in [N].
    anchor : str
        ``"vertex"`` or ``"face"``.
    anchor_index : int
        Index of the vertex or face on the block, per ``anchor``.
    loading_type : str, optional
        See :class:`Load`.
    name : str, optional
        Name for this load.

    Examples
    --------
    >>> PointLoad.at_vertex(block=10, vertex=5, force=[0, 0, -5000])
    PointLoad(block=10, force=[0, 0, -5000], at vertex 5)
    """

    def __init__(
        self,
        block: int,
        force: list,
        anchor: str,
        anchor_index: int,
        loading_type: str = "ramp",
        name: Optional[str] = None,
    ) -> None:
        super().__init__(loading_type=loading_type, name=name)
        self.block = block
        self.force = list(force)
        self.anchor = check_anchor(anchor)
        self.anchor_index = anchor_index

    def __repr__(self) -> str:
        return f"PointLoad(block={self.block}, force={self.force}, at {self.anchor} {self.anchor_index})"

    @property
    def __data__(self) -> dict:
        return {
            "block": self.block,
            "force": self.force,
            "anchor": self.anchor,
            "anchor_index": self.anchor_index,
            "loading_type": self.loading_type,
        }

    @classmethod
    def at_vertex(cls, block: int, vertex: int, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> "PointLoad":
        """Apply a concentrated force at a vertex of a block.

        Parameters
        ----------
        block : int
            Graph node index of the target block.
        vertex : int
            Index of the vertex on the block geometry.
        force : list[float]
            Force vector [fx, fy, fz] in [N].
        loading_type : str, optional
            See :class:`Load`.
        name : str, optional
            Name for this load.

        Returns
        -------
        :class:`PointLoad`
        """
        return cls(block=block, force=force, anchor="vertex", anchor_index=vertex, loading_type=loading_type, name=name)

    @classmethod
    def at_face(cls, block: int, face: int, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> "PointLoad":
        """Apply a concentrated force at the centroid of a face of a block.

        Parameters
        ----------
        block : int
            Graph node index of the target block.
        face : int
            Index of the face on the block geometry.
        force : list[float]
            Force vector [fx, fy, fz] in [N].
        loading_type : str, optional
            See :class:`Load`.
        name : str, optional
            Name for this load.

        Returns
        -------
        :class:`PointLoad`
        """
        return cls(block=block, force=force, anchor="face", anchor_index=face, loading_type=loading_type, name=name)


class SurfaceLoad(Load):
    """A distributed traction over a block face.

    The equivalent centroidal force and moment are resolved at solve time by
    multiplying the traction by the face area, applied at the face centroid.

    Parameters
    ----------
    block : int
        Graph node index of the target block.
    face : int
        Index of the loaded face on the block geometry.
    traction : list[float]
        Traction vector [tx, ty, tz] in [N/m²]. Multiplied by the face area to give
        the resultant force.
    loading_type : str, optional
        See :class:`Load`.
    name : str, optional
        Name for this load.

    Examples
    --------
    >>> SurfaceLoad(block=4, face=4, traction=[0, 0, -10000])
    SurfaceLoad(block=4, face=4, traction=[0, 0, -10000])
    """

    def __init__(
        self,
        block: int,
        face: int,
        traction: list,
        loading_type: str = "ramp",
        name: Optional[str] = None,
    ) -> None:
        super().__init__(loading_type=loading_type, name=name)
        self.block = block
        self.face = face
        self.traction = list(traction)

    def __repr__(self) -> str:
        return f"SurfaceLoad(block={self.block}, face={self.face}, traction={self.traction})"

    @property
    def __data__(self) -> dict:
        return {
            "block": self.block,
            "face": self.face,
            "traction": self.traction,
            "loading_type": self.loading_type,
        }


class BodyForce(Load):
    """A global body acceleration applied to every block.

    The resultant force on each block is ``acceleration * mass``, where the mass comes
    from the block material density and volume. This is how horizontal seismic
    coefficients are applied.

    Parameters
    ----------
    acceleration : list[float]
        Acceleration components [ax, ay, az] in [m/s²].
    loading_type : str, optional
        See :class:`Load`.
    name : str, optional
        Name for this load.

    Notes
    -----
    This takes an acceleration, not a force. It is applied on top of self-weight,
    which every solver already accounts for; passing ``[0, 0, -9.81]`` here doubles
    the gravity load rather than enabling it.

    Examples
    --------
    >>> BodyForce(acceleration=[1.96, 0, 0], name="0.2g horizontal")
    BodyForce(acceleration=[1.96, 0, 0])
    """

    def __init__(
        self,
        acceleration: list,
        loading_type: str = "ramp",
        name: Optional[str] = None,
    ) -> None:
        super().__init__(loading_type=loading_type, name=name)
        self.acceleration = list(acceleration)

    def __repr__(self) -> str:
        return f"BodyForce(acceleration={self.acceleration})"

    @property
    def __data__(self) -> dict:
        return {
            "acceleration": self.acceleration,
            "loading_type": self.loading_type,
        }


# =============================================================================
# Displacement boundary conditions
# =============================================================================


class Displacement(BoundaryCondition):
    """Base class for prescribed movements of a block.

    A displacement is prescribed per component: a component left as ``None`` is
    unconstrained and the solver is free to resolve it. Prescribing a movement on a
    block flagged ``is_support`` on the model overrides its fixity for that component,
    which is how a support settlement is modelled.

    Parameters
    ----------
    block : int
        Graph node index of the target block.
    name : str, optional
        Name for this boundary condition.

    Notes
    -----
    Supports themselves are not displacement boundary conditions. They live on the
    model as ``block.is_support`` and are read from there by the solvers.
    """

    def __init__(self, block: int, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.block = block


class Translation(Displacement):
    """A prescribed translation of a block, per component.

    Parameters
    ----------
    block : int
        Graph node index of the target block.
    dx, dy, dz : float, optional
        Translation components in [m]. ``None`` (default) leaves that degree of
        freedom unconstrained.
    name : str, optional
        Name for this boundary condition.

    Raises
    ------
    ValueError
        If all three components are ``None``.

    Examples
    --------
    >>> Translation(block=0, dx=0.5)
    Translation(block=0, dx=0.5, dy=None, dz=None)
    """

    def __init__(
        self,
        block: int,
        dx: Optional[float] = None,
        dy: Optional[float] = None,
        dz: Optional[float] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(block=block, name=name)
        if dx is None and dy is None and dz is None:
            raise ValueError("A Translation must prescribe at least one of dx, dy, dz; all three are None, which constrains nothing.")
        self.dx = dx
        self.dy = dy
        self.dz = dz

    def __repr__(self) -> str:
        return f"Translation(block={self.block}, dx={self.dx}, dy={self.dy}, dz={self.dz})"

    @property
    def components(self) -> list:
        """The prescribed translation as ``[dx, dy, dz]``, with ``None`` where unconstrained."""
        return [self.dx, self.dy, self.dz]

    @property
    def __data__(self) -> dict:
        return {"block": self.block, "dx": self.dx, "dy": self.dy, "dz": self.dz}


class Rotation(Displacement):
    """A prescribed rotation of a block about its centroid, per component.

    Parameters
    ----------
    block : int
        Graph node index of the target block.
    rx, ry, rz : float, optional
        Rotation components in [rad]. ``None`` (default) leaves that degree of
        freedom unconstrained.
    name : str, optional
        Name for this boundary condition.

    Raises
    ------
    ValueError
        If all three components are ``None``.

    Examples
    --------
    >>> Rotation(block=0, rz=0.01)
    Rotation(block=0, rx=None, ry=None, rz=0.01)
    """

    def __init__(
        self,
        block: int,
        rx: Optional[float] = None,
        ry: Optional[float] = None,
        rz: Optional[float] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(block=block, name=name)
        if rx is None and ry is None and rz is None:
            raise ValueError("A Rotation must prescribe at least one of rx, ry, rz; all three are None, which constrains nothing.")
        self.rx = rx
        self.ry = ry
        self.rz = rz

    def __repr__(self) -> str:
        return f"Rotation(block={self.block}, rx={self.rx}, ry={self.ry}, rz={self.rz})"

    @property
    def components(self) -> list:
        """The prescribed rotation as ``[rx, ry, rz]``, with ``None`` where unconstrained."""
        return [self.rx, self.ry, self.rz]

    @property
    def __data__(self) -> dict:
        return {"block": self.block, "rx": self.rx, "ry": self.ry, "rz": self.rz}
