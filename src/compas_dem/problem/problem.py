from typing import Optional

import compas.geometry as cg
from compas.colors import Color
from compas.data import Data
from compas.geometry import Vector
from compas_dem.interactions import ContactProperties
from compas_dem.interactions import JointModel
from compas_dem.interactions import MohrCoulomb
from compas_dem.models import BlockModel
from compas_dem.problem.boundary_condition import BodyForce
from compas_dem.problem.boundary_condition import BoundaryCondition
from compas_dem.problem.boundary_condition import Displacement
from compas_dem.problem.boundary_condition import Load
from compas_dem.problem.boundary_condition import Moment
from compas_dem.problem.boundary_condition import PointLoad
from compas_dem.problem.boundary_condition import Rotation
from compas_dem.problem.boundary_condition import SurfaceLoad
from compas_dem.problem.boundary_condition import Translation
from compas_dem.problem.solvers import Solver


class Problem(Data):
    """A structural problem defined over a block model.

    A problem holds the boundary conditions (loads and prescribed movements), the
    contact properties, and the solver configuration. It holds the model itself as a
    live object reference — there is no indirection to pay for while working in
    memory.

    Serializing a problem writes the model as a guid reference, never the model
    itself. Rebinding that reference on load is the job of
    :class:`~compas_dem.models.Analysis`, which is what owns the model and its
    problems together. A problem loaded on its own is unbound: reading
    :attr:`model` or calling :meth:`solve` on it raises.

    All registered boundary conditions are solved together. To solve a different set
    of them, build a second problem — the order they were added in is the order they
    are applied, and there is no way to reorder or select a subset.

    Parameters
    ----------
    model : :class:`compas_dem.models.BlockModel`
        The discrete element model this problem is defined over.
    name : str, optional
        Name of the problem.

    Examples
    --------
    >>> from compas_dem.models import BlockModel
    >>> from compas_dem.problem import PointLoad, Problem, Solver
    >>> model = BlockModel()
    >>> problem = Problem(model, name="ULS")
    >>> _ = problem.add(PointLoad.at_face(block=10, face=2, force=[0, 0, -5000]))
    >>> problem.set_contact_model("MohrCoulomb", mu=0.6)
    >>> problem.set_solver(Solver.CRA())
    >>> results = problem.solve()  # doctest: +SKIP
    """

    def __init__(self, model: BlockModel, name: Optional[str] = None, **kwargs) -> None:
        super().__init__(name=name)
        self._model: Optional[BlockModel] = model
        self._model_guid: str = str(model.guid)
        self._analysis = None
        self._boundary_conditions: list = []
        self._contact_properties = ContactProperties()
        self._solver: Optional[Solver] = None

    @property
    def __data__(self) -> dict:
        return {
            "model_guid": self._model_guid,
            "boundary_conditions": self._boundary_conditions,
            "contact_properties": self._contact_properties,
            "solver": self._solver,
        }

    @classmethod
    def __from_data__(cls, data: dict) -> "Problem":
        # The model is written as a guid reference only. Reconstruct unbound and let
        # Analysis hand the real model back; see Analysis.__from_data__.
        obj = cls.__new__(cls)
        Data.__init__(obj)
        obj._model = None
        obj._model_guid = data["model_guid"]
        obj._analysis = None
        obj._boundary_conditions = list(data.get("boundary_conditions", []))
        obj._contact_properties = data["contact_properties"]
        obj._solver = data["solver"]
        return obj

    # ============================================================================
    # Model
    # ============================================================================

    @property
    def model(self) -> BlockModel:
        """The block model this problem is defined over.

        Serialized as a guid reference rather than as the model itself.

        Raises
        ------
        ValueError
            If the problem is unbound, i.e. it was deserialized on its own rather
            than as part of an :class:`~compas_dem.models.Analysis`.
        """
        if self._model is None:
            raise ValueError(
                f"This problem is not bound to a model (model_guid={self._model_guid}). "
                "A problem only carries a guid reference to its model when serialized; "
                "load it as part of an Analysis, or add it to one with analysis.add_problem(problem)."
            )
        return self._model

    @property
    def model_guid(self) -> str:
        """Guid of the model this problem is defined over, as a string."""
        return self._model_guid

    def _bind_model(self, model: BlockModel) -> None:
        """Bind the real model object to this problem. Called by :class:`Analysis`.

        Raises
        ------
        ValueError
            If the model's guid does not match the one this problem was defined over.
        """
        if str(model.guid) != self._model_guid:
            raise ValueError(f"Model {model.guid} does not match the model this problem was defined over ({self._model_guid}).")
        self._model = model

    # ============================================================================
    # Boundary conditions
    # ============================================================================

    def add(self, boundary_condition: BoundaryCondition) -> BoundaryCondition:
        """Register a load or a prescribed movement on this problem.

        Parameters
        ----------
        boundary_condition : :class:`~compas_dem.problem.BoundaryCondition`
            A :class:`~compas_dem.problem.Load` or
            :class:`~compas_dem.problem.Displacement` instance.

        Returns
        -------
        :class:`~compas_dem.problem.BoundaryCondition`
            The boundary condition that was registered, so it can be kept for
            reference.

        Raises
        ------
        TypeError
            If the argument is not a boundary condition.
        ValueError
            If the same boundary condition object is registered twice.

        Examples
        --------
        >>> from compas_dem.models import BlockModel
        >>> from compas_dem.problem import Problem, SurfaceLoad, Translation
        >>> problem = Problem(BlockModel())
        >>> _ = problem.add(SurfaceLoad(block=4, face=4, traction=[0, 0, -10000]))
        >>> _ = problem.add(Translation(block=0, dx=0.5))
        """
        if not isinstance(boundary_condition, BoundaryCondition):
            raise TypeError(
                f"Expected a Load or a Displacement, got {type(boundary_condition).__name__}. Build one first, e.g. PointLoad.at_face(block=10, face=2, force=[0, 0, -5000])."
            )
        if any(bc is boundary_condition for bc in self._boundary_conditions):
            raise ValueError("That boundary condition object is already registered on this problem.")
        self._boundary_conditions.append(boundary_condition)
        return boundary_condition

    # ----------------------------------------------------------------------------
    # Convenience: build a boundary condition and register it in one call
    # ----------------------------------------------------------------------------
    # Each of these constructs the corresponding class and hands it to add(). They are
    # sugar, not a second implementation: the class is the only place the data lives,
    # and every method returns the object it built so it can be kept for reference.
    #
    # Unlike the pre-6e5dd23 versions, none of them takes a boundary_condition= keyword.
    # There is nothing to forget and nothing to target: a problem is the load case.

    def add_point_load_at_vertex(self, block: int, vertex: int, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> PointLoad:
        """Add a concentrated force at a vertex of a block. See :class:`~compas_dem.problem.PointLoad`."""
        return self.add(PointLoad.at_vertex(block=block, vertex=vertex, force=force, loading_type=loading_type, name=name))

    def add_point_load_at_face(self, block: int, face: int, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> PointLoad:
        """Add a concentrated force at the centroid of a face of a block. See :class:`~compas_dem.problem.PointLoad`."""
        return self.add(PointLoad.at_face(block=block, face=face, force=force, loading_type=loading_type, name=name))

    def add_point_load_at_point(self, block: int, point: list, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> PointLoad:
        """Add a concentrated force at explicit coordinates on a block. See :class:`~compas_dem.problem.PointLoad`."""
        return self.add(PointLoad.at_point(block=block, point=point, force=force, loading_type=loading_type, name=name))

    def add_point_load_at_centroid(self, block: int, force: list, loading_type: str = "ramp", name: Optional[str] = None) -> PointLoad:
        """Add a concentrated force at the centroid of a block, inducing no moment. See :class:`~compas_dem.problem.PointLoad`."""
        return self.add(PointLoad.at_centroid(block=block, force=force, loading_type=loading_type, name=name))

    def add_moment(self, block: int, moment: list, loading_type: str = "ramp", name: Optional[str] = None) -> Moment:
        """Add a pure couple about a block centroid. See :class:`~compas_dem.problem.Moment`."""
        return self.add(Moment(block=block, moment=moment, loading_type=loading_type, name=name))

    def add_surface_load(self, block: int, face: int, traction: list, loading_type: str = "ramp", name: Optional[str] = None) -> SurfaceLoad:
        """Add a distributed traction over a block face. See :class:`~compas_dem.problem.SurfaceLoad`."""
        return self.add(SurfaceLoad(block=block, face=face, traction=traction, loading_type=loading_type, name=name))

    def add_body_force(self, acceleration: list, loading_type: str = "ramp", name: Optional[str] = None) -> BodyForce:
        """Add a global body acceleration applied to every block. See :class:`~compas_dem.problem.BodyForce`."""
        return self.add(BodyForce(acceleration=acceleration, loading_type=loading_type, name=name))

    def add_translation(
        self,
        block: int,
        dx: Optional[float] = None,
        dy: Optional[float] = None,
        dz: Optional[float] = None,
        name: Optional[str] = None,
    ) -> Translation:
        """Prescribe a translation of a block, per component. See :class:`~compas_dem.problem.Translation`."""
        return self.add(Translation(block=block, dx=dx, dy=dy, dz=dz, name=name))

    def add_rotation(
        self,
        block: int,
        rx: Optional[float] = None,
        ry: Optional[float] = None,
        rz: Optional[float] = None,
        name: Optional[str] = None,
    ) -> Rotation:
        """Prescribe a rotation of a block about its centroid, per component. See :class:`~compas_dem.problem.Rotation`."""
        return self.add(Rotation(block=block, rx=rx, ry=ry, rz=rz, name=name))

    @property
    def boundary_conditions(self) -> list:
        """Every boundary condition registered on this problem, in the order added."""
        return self._boundary_conditions

    @property
    def loads(self) -> list:
        """The registered boundary conditions that are loads."""
        return [bc for bc in self._boundary_conditions if isinstance(bc, Load)]

    @property
    def displacements(self) -> list:
        """The registered boundary conditions that are prescribed movements."""
        return [bc for bc in self._boundary_conditions if isinstance(bc, Displacement)]

    # ============================================================================
    # Pre-visualization utilities
    # ============================================================================

    def inspect_model(
        self,
        show_blocks: bool = False,
        face_indices: bool = True,
        show_loads: bool = True,
        show_supports: bool = True,
        grid: bool = False,
        kill: bool = True,
    ) -> None:
        """Visualize the block model with block indices, loads and boundary conditions.

        Each kind of boundary condition gets its own group in the scene tree — "Point
        Loads", "Surface Loads", "Body Forces", "Supports" and "Prescribed
        Displacements" — so they can be toggled independently. A group is only created
        if boundary conditions of that kind are registered.

        .. danger::

           With the default ``kill=True`` this method is for inspection only, and
           halts the script once the viewer is closed. **Comment out or remove
           before solving** — leaving it in will block the solver. Pass
           ``kill=False`` to inspect and then carry on to the solve.

        Parameters
        ----------
        show_blocks : bool, optional
            Draw the block volumes. Default ``False``.
        face_indices : bool, optional
            Draw each face separately so faces can be identified by index.
            Default ``True``.
        show_loads : bool, optional
            Draw point loads, surface loads and body forces. Default ``True``.
        show_supports : bool, optional
            Draw supports and prescribed movements. Default ``True``.
        grid : bool, optional
            Show the viewer grid. Default ``False``.
        kill : bool, optional
            Stop the script once the viewer is closed, by raising
            :class:`ChildProcessError`. Default ``True``. Set to ``False`` to
            let execution continue on to the solve.

        Raises
        ------
        ChildProcessError
            If ``kill`` is ``True``, once the viewer is closed.
        """
        from compas_viewer.scene import Tag  # noqa: F401
        from compas_viewer.viewer import Viewer

        viewer = Viewer()
        model = self.model
        if not grid:
            viewer.config.renderer.show_grid = False

        blocks = {block.graphnode: block for block in model.elements()}

        def label(bc: BoundaryCondition) -> str:
            """Append the boundary condition's own name, when one was actually given.

            ``Data.name`` falls back to the class name, which is already in the entry
            label, so test the underlying attribute rather than the property.
            """
            return f"  [{bc._name}]" if bc._name else ""

        def block_scale(block) -> float:
            return block.modelgeometry.edge_length([0, 1]) / 2

        def arrow(point, vector: Vector, scale: float):
            """A line running from ``point`` back along ``vector``, i.e. pointing at ``point``."""
            if vector.length == 0:
                return None
            return cg.Line(point, [p - v for p, v in zip(point, vector.unitized() * scale)])

        def resolve_block(bc: BoundaryCondition, index: int):
            """Look up a block, warning instead of raising so inspection still runs."""
            if index not in blocks:
                print(f"{type(bc).__name__} references block {index}, which does not exist in the model.{label(bc)}")
                return None
            return blocks[index]

        def of_type(bc_type) -> list:
            return [bc for bc in self._boundary_conditions if isinstance(bc, bc_type)]

        if show_loads:
            point_loads = of_type(PointLoad)
            surface_loads = of_type(SurfaceLoad)
            body_forces = of_type(BodyForce)

            if not point_loads:
                print("No point loads registered on the problem.")
            else:
                loads_view = viewer.scene.add_group(name="Point Loads")
                for bc in point_loads:
                    block = resolve_block(bc, bc.block)
                    if block is None:
                        continue
                    mesh = block.modelgeometry
                    if bc.anchor == "centroid":
                        point = list(block.point)
                    elif bc.anchor == "point":
                        point = list(bc.anchor_value)
                    elif bc.anchor == "vertex":
                        if bc.anchor_value not in list(mesh.vertices()):
                            print(f"Point load on block {bc.block} is anchored to vertex {bc.anchor_value}, which does not exist.{label(bc)}")
                            continue
                        point = mesh.vertex_coordinates(bc.anchor_value)
                    else:
                        if bc.anchor_value not in list(mesh.faces()):
                            print(f"Point load on block {bc.block} is anchored to face {bc.anchor_value}, which does not exist.{label(bc)}")
                            continue
                        point = mesh.face_center(bc.anchor_value)
                    force = Vector(*bc.force)
                    line = arrow(point, force, block_scale(block))
                    if line is None:
                        continue
                    where = "centroid" if bc.anchor == "centroid" else f"{bc.anchor} {bc.anchor_value}"
                    loads_view.add(
                        line,
                        name=f"Point Load: [{force.x:.1f}, {force.y:.1f}, {force.z:.1f}] at {where} of block {bc.block}{label(bc)}",
                        linewidth=2.5,
                        linecolor=Color.red(),
                    )

            if not surface_loads:
                print("No surface loads registered on the problem.")
            else:
                surface_view = viewer.scene.add_group(name="Surface Loads")
                for bc in surface_loads:
                    block = resolve_block(bc, bc.block)
                    if block is None:
                        continue
                    mesh = block.modelgeometry
                    if bc.face not in list(mesh.faces()):
                        print(f"Surface load on block {bc.block} references face {bc.face}, which does not exist.{label(bc)}")
                        continue
                    traction = Vector(*bc.traction)
                    # The solver multiplies the traction by the face area to get the resultant.
                    resultant = traction * mesh.face_area(bc.face)
                    surface_view.add(
                        mesh.face_polygon(bc.face),
                        name=f"Loaded Face: block {bc.block}, face {bc.face}{label(bc)}",
                        color=Color.cyan(),
                        opacity=0.5,
                    )
                    line = arrow(mesh.face_center(bc.face), traction, block_scale(block))
                    if line is not None:
                        surface_view.add(
                            line,
                            name=(
                                f"Surface Load: [{traction.x:.1f}, {traction.y:.1f}, {traction.z:.1f}] on block {bc.block}, face {bc.face} \n"
                                f" Resultant: [{resultant.x:.1f}, {resultant.y:.1f}, {resultant.z:.1f}]{label(bc)}"
                            ),
                            linewidth=2.5,
                            linecolor=Color.cyan(),
                        )

            if body_forces:
                # Body forces are global, so they are drawn once at the centre of the model.
                body_view = viewer.scene.add_group(name="Body Forces")
                origin = cg.centroid_points([list(block.point) for block in blocks.values()])
                scale = max(block_scale(block) for block in blocks.values()) if blocks else 1.0
                for bc in body_forces:
                    vector = Vector(*bc.acceleration)
                    line = arrow(origin, vector, scale)
                    if line is None:
                        continue
                    body_view.add(
                        line,
                        name=f"Body Force: [{vector.x:.2f}, {vector.y:.2f}, {vector.z:.2f}] m/s² ({bc.loading_type}){label(bc)}",
                        linewidth=2.5,
                        linecolor=Color.orange(),
                    )

            moments = of_type(Moment)
            if moments:
                # A couple has no line of action, so it is drawn along its own axis at
                # the block centroid rather than as a force arrow.
                moment_view = viewer.scene.add_group(name="Moments")
                for bc in moments:
                    block = resolve_block(bc, bc.block)
                    if block is None:
                        continue
                    vector = Vector(*bc.moment)
                    line = arrow(list(block.point), vector, block_scale(block))
                    if line is None:
                        continue
                    moment_view.add(
                        line,
                        name=f"Moment: [{vector.x:.1f}, {vector.y:.1f}, {vector.z:.1f}] Nm about block {bc.block}{label(bc)}",
                        linewidth=2.5,
                        linecolor=Color.magenta(),
                    )

        if show_supports:
            # Supports live on the model (block.is_support); the boundary conditions
            # only hold prescribed movements.
            support_blocks = list(model.supports())
            if not support_blocks:
                print("No supports defined in the model.")
            else:
                supports_view = viewer.scene.add_group(name="Supports")
                for block in support_blocks:
                    supports_view.add(
                        block.modelgeometry,
                        name=f"Support: block {block.graphnode}",
                        color=Color.red(),
                        opacity=0.5,
                    )

            prescribed = of_type(Displacement)
            if prescribed:
                prescribed_view = viewer.scene.add_group(name="Prescribed Displacements")
                for bc in prescribed:
                    block = resolve_block(bc, bc.block)
                    if block is None:
                        continue
                    # Unconstrained components come through as None.
                    vector = Vector(*[c or 0.0 for c in bc.components])
                    units = "m" if isinstance(bc, Translation) else "rad"
                    line = arrow(list(block.point), vector, block_scale(block))
                    if line is None:
                        continue
                    prescribed_view.add(
                        line,
                        name=f"Prescribed {type(bc).__name__}: {bc.components} {units} on block {bc.block}{label(bc)}",
                        linewidth=2.5,
                        linecolor=Color.violet(),
                    )

        blocks_view = viewer.scene.add_group(name="Blocks")

        for element in model.elements():
            block_view = viewer.scene.add_group(name=f"Block {element.graphnode}")
            if show_blocks:
                blocks_view.add(
                    element.modelgeometry,
                    opacity=0.25,
                    name=f"Block {element.graphnode}",
                    color=Color.grey(),
                )
            if face_indices:
                for idx in element.modelgeometry.faces():
                    block_view.add(
                        element.modelgeometry.face_polygon(idx),
                        name=f"Face {idx}",
                        color=Color.grey(),
                        opacity=0.25,
                    )
        viewer.show()

        if kill:
            raise ChildProcessError("Model inspection complete. Please comment out or remove the call to inspect_model(), or pass kill=False, to proceed.")

    # =============================================================================
    # Contact properties
    # =============================================================================

    _CONTACT_MODELS: dict = {
        "MohrCoulomb": MohrCoulomb,
    }

    def set_contact_model(self, model: str, **kwargs) -> None:
        """Set the contact model by name.

        Parameters
        ----------
        model : str
            Contact model type. Supported: ``"MohrCoulomb"``.
        **kwargs
            Parameters forwarded to the contact model constructor.

        Raises
        ------
        ValueError
            If the model name is not recognised.
        """
        if model not in self._CONTACT_MODELS:
            raise ValueError(f"Contact model '{model}' is not recognised. Available: {list(self._CONTACT_MODELS)}.")
        self._contact_properties.contact_model = self._CONTACT_MODELS[model](**kwargs)

    def set_joint_model(self, kn: float, kt: float) -> None:
        """Set the joint stiffness model.

        Parameters
        ----------
        kn : float
            Normal stiffness [N/m].
        kt : float
            Tangential stiffness [N/m].
        """
        self._contact_properties.joint_model = JointModel(kn=kn, kt=kt)

    @property
    def contact_properties(self) -> ContactProperties:
        """The contact properties attached to this problem."""
        return self._contact_properties

    # =============================================================================
    # Solve
    # =============================================================================

    def set_solver(self, solver: Solver) -> None:
        """Set the solver configuration.

        Parameters
        ----------
        solver : :class:`~compas_dem.problem.Solver`
            A solver configuration, e.g. ``Solver.CRA()`` or ``Solver.LMGC90(...)``.
        """
        self._solver = solver

    @property
    def solver(self) -> Optional[Solver]:
        """The solver configuration set on this problem, if any."""
        return self._solver

    def solve(self):
        """Solve the problem on its model using the configured solver.

        Every registered boundary condition is applied. If the problem belongs to an
        :class:`~compas_dem.models.Analysis`, the results are recorded on it.

        Returns
        -------
        :class:`~compas_dem.problem.Results`

        Raises
        ------
        ValueError
            If the problem is unbound, no solver is configured, the model is invalid,
            or the solver name is not recognised.
        """
        model = self.model
        if self._solver is None:
            raise ValueError("No solver configured. Call problem.set_solver(Solver.CRA()) before solving.")
        self._check_model_validity(model)
        solver = self._solver
        params = {k: v for k, v in solver.parameters.items() if v is not None}

        if solver.name == "LMGC90":
            from compas_dem.analysis.lmgc90 import lmgc90_solve

            results = lmgc90_solve(self, model, **params)
        elif solver.name == "CRA":
            from compas_dem.analysis.cra import cra_solve

            results = cra_solve(self, model, **params)
        elif solver.name == "RBE":
            from compas_dem.analysis.cra import rbe_solve

            results = rbe_solve(self, model, **params)
        elif solver.name == "PRD":
            from compas_dem.analysis.prd import prd_solve

            results = prd_solve(self, model, **params)
        elif solver.name == "BLA":
            from compas_dem.analysis.bla import bla_solve

            results = bla_solve(self, model, **params)
        else:
            raise ValueError(f"Solver '{solver.name}' is not recognised. Available: 'LMGC90', 'CRA', 'RBE', 'PRD', 'BLA'.")

        if self._analysis is not None:
            self._analysis._record_results(self, results)
        return results

    # ============================================================================
    # Validation
    # ============================================================================

    def _check_model_validity(self, model: BlockModel) -> None:
        """Check that the model is valid for solving.

        Parameters
        ----------
        model : :class:`compas_dem.models.BlockModel`

        Raises
        ------
        ValueError
            If the model is invalid.
        """
        if not any(element.is_support for element in model.elements()):
            raise ValueError("The model has no supports defined. Flag support blocks with block.is_support = True before solving.")
        if not self.contact_properties.contact_model:
            raise ValueError("No contact model defined. Please add a contact model before solving.")
