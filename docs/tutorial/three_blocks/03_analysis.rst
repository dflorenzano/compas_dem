********************************************************************************
Analysis and Visualisation
********************************************************************************

.. rst-class:: lead

With a fully configured :class:`~compas_dem.problem.Problem` we can hand it
off to a solver. ``compas_dem`` ships with bindings for three engines:

- **LMGC90** Discrete Element Analysis
- **CRA** - Coubpled-Rigid Body Analysis
- **RBE** - Rigid-Body Equilibrium

All reachable through the same :class:`~compas_dem.problem.Solver` API.


Load the analysis
=================

We start by deserialising the analysis from the previous page. Because the
analysis holds the model and the problem together, the problem comes back
already bound to its model — there is nothing to re-link by hand.

.. code-block:: python

    import os
    import compas

    HERE = os.path.dirname(__file__)
    analysis = compas.json_load(os.path.join(HERE, "DEM_analysis.json"))
    problem = analysis.problems[0]


Solve with LMGC90
=================

LMGC90 runs a discrete element simulation through ``n_steps`` time
increments of size ``dt``. Set the solver on the problem, then call
:meth:`~compas_dem.problem.Problem.solve`, which takes no arguments because
the model comes from the problem itself.

.. code-block:: python

    from compas_dem.problem import Solver

    problem.set_solver(Solver.LMGC90(n_steps=100, dt=0.001))
    results = problem.solve()

    compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))

Solving a problem that belongs to an analysis records its results on that
analysis, so dumping the analysis persists the model, the problem and the
results as one object.


Solve with CRA
==============

For a static limit-state check, the CRA solver is a better fit. It uses a
penalty formulation to compute admissible contact forces under self-weight.
The interface is identical, only the solver configuration was swapped.

.. code-block:: python

    problem.set_solver(Solver.CRA(verbose=True))
    results = problem.solve()

.. note::

   CRA and RBE resolve self-weight against contact forces and have no
   mechanism for applied loads or prescribed movements. Rather than dropping
   them silently, they refuse a problem that carries any. Solve those with
   LMGC90, PRD or BLA instead. This problem is self-weight alone, so either
   family works.


Inspect the results
===================

:class:`~compas_dem.problem.Results` is a standalone object, keyed by block
index and contact edge, serialisable on its own. It is never written back
into the model.

.. code-block:: python

    results = analysis.results_for(problem)

    for node in results.nodes():
        block_transformation = results.transformation(node)

    for edge in results.edges():
        gap = results.gap(edge)
        magnitude = results.force_magnitude(edge)
        print(f"Edge {edge} gap: {gap}, force magnitude: {magnitude}")


Visualise the results
=====================

:class:`~compas_dem.viewer.DEMViewer` renders the deformed model, the
contact polygons, and the resultant force vectors. The ``scale`` argument
amplifies the displacements so they are visible in static configurations.

.. code-block:: python

    from compas_dem.viewer import DEMViewer

    viewer = DEMViewer(analysis.model)
    viewer.add_solution(results, scale=0.5)
    viewer.show()


.. figure:: /_images/three_blocks_results_0.png
   :align: center
   :width: 80%

.. note::
    Inside the viewer panel, you can access each force line's vector (in global coordinate system) and magnitude.



The complete scripts are available at
:download:`300_SW_Analysis.py <300_SW_Analysis.py>` (LMGC90),
:download:`300_SW_Analysis_CRA.py <300_SW_Analysis_CRA.py>` (CRA), and
:download:`301_SW_Viz.py <301_SW_Viz.py>` (visualisation).
