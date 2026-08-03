********************************************************************************
Problem Setup
********************************************************************************

.. rst-class:: lead

A :class:`~compas_dem.models.BlockModel` describes the geometry and topology
of an assembly, but says nothing yet about what we want to compute. That is
the job of :class:`~compas_dem.problem.Problem` — it ties a model to its
boundary conditions and contact properties so a solver can take it through.


Load the model
==============

We pick up the JSON dumped on the previous page and reconstruct the model.
COMPAS handles the serialisation transparently — what comes back is the
same :class:`~compas_dem.models.BlockModel` instance with all blocks,
contacts, and material assignments intact.

.. code-block:: python

    import os
    import compas

    HERE = os.path.dirname(__file__)
    model = compas.json_load(os.path.join(HERE, "DEM_model.json"))


Create the problem
==================

A :class:`~compas_dem.problem.Problem` holds the model together with its
boundary conditions, its contact properties and its solver.

.. code-block:: python

    from compas_dem.problem import Problem

    problem = Problem(model, name="Self-weight")


Boundary conditions
===================

A boundary condition is either a :class:`~compas_dem.problem.Load` or a
:class:`~compas_dem.problem.Displacement`, built as an object and registered
with :meth:`~compas_dem.problem.Problem.add`. This model only has to carry its
own weight, so it needs none at all: every solver applies self-weight from the
block densities, and there is no gravity switch to set.

Supports are not boundary conditions either. In the previous step we marked the
base plate with ``block.is_support``, and the solvers read that off the model
directly, so the same supports apply to every problem defined over it.

A load would be added like this:

.. code-block:: python

    from compas_dem.problem import PointLoad

    problem.add(PointLoad.at_face(block=2, face=4, force=[0, 0, -50000]))


Contact properties
==================

Contact behaviour is governed by a :class:`~compas_dem.interactions.ContactModel`.
Here we use a Mohr–Coulomb friction model with a friction coefficient of
``0.5`` — a typical value for limestone-on-limestone interfaces.

.. code-block:: python

    problem.set_contact_model("MohrCoulomb", mu=0.5)


Serialise the analysis
======================

A problem holds its model as a live object but writes it out as a guid
reference, so dumping a problem on its own would leave it without geometry.
:class:`~compas_dem.models.Analysis` is the container that keeps them together:
it writes the model exactly once, and on load hands the real model back to every
problem. The next page loads exactly this file and runs the analysis.

.. code-block:: python

    from compas_dem.models import Analysis

    analysis = Analysis(model, name="Three blocks")
    analysis.add_problem(problem)

    compas.json_dump(analysis, os.path.join(HERE, "DEM_analysis.json"))


Inspect the setup
=================

Before solving, it is useful to view the model with supports and load
arrows in place. :class:`~compas_dem.viewer.DEMViewer` renders the
problem interactively.

.. code-block:: python

    from compas_dem.viewer import DEMViewer

    viewer = DEMViewer(problem.model)
    viewer.setup()
    viewer.show()

The complete script is available at
:download:`200_SW_Problem.py <200_SW_Problem.py>`.
