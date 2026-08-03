from typing import TYPE_CHECKING
from typing import Optional

from compas.data import Data
from compas_dem.models.blockmodel import BlockModel

if TYPE_CHECKING:
    from compas_dem.problem import Problem
    from compas_dem.problem import Results


class Analysis(Data):
    """A block model, the problems defined over it, and the results they produced.

    The model and the problems are independent objects; the results are owned. A
    problem holds its model as a live object reference, but writes it out as a guid
    only — the analysis is what writes the model itself, exactly once, and what hands
    the real object back to every problem on load. So a serialized analysis round-trips
    whole, and ``analysis.problems[0].solve()`` works straight after loading.

    Results are recorded automatically: solving a problem that belongs to an analysis
    stores its results under that problem's guid.

    Parameters
    ----------
    model : :class:`~compas_dem.models.BlockModel`, optional
        The model to be analyzed. If omitted, it is adopted from the first problem
        added.
    name : str, optional
        Name of the analysis.

    Examples
    --------
    >>> analysis = Analysis(model)  # doctest: +SKIP
    >>> analysis.add_problem(problem)  # doctest: +SKIP
    >>> results = problem.solve()  # doctest: +SKIP
    >>> compas.json_dump(analysis, "analysis.json")  # doctest: +SKIP
    >>> analysis = compas.json_load("analysis.json")  # doctest: +SKIP
    >>> analysis.results_for(analysis.problems[0])  # doctest: +SKIP
    """

    def __init__(self, model: Optional[BlockModel] = None, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.model: Optional[BlockModel] = model
        self.problems: list = []
        self.results: dict = {}

    @property
    def __data__(self) -> dict:
        return {
            "model": self.model,
            "problems": self.problems,
            "results": self.results,
        }

    @classmethod
    def __from_data__(cls, data: dict) -> "Analysis":
        obj = cls(model=data["model"])
        obj.problems = list(data["problems"])
        obj.results = dict(data.get("results", {}))
        # Problems serialize their model as a guid reference only; give the real
        # object back and take ownership of them again.
        for problem in obj.problems:
            if obj.model is not None:
                problem._bind_model(obj.model)
            problem._analysis = obj
        return obj

    def add_problem(self, problem: "Problem") -> "Problem":
        """Add a problem to the analysis and take ownership of its results.

        If the analysis has no model yet, it adopts the problem's model.

        Parameters
        ----------
        problem : :class:`~compas_dem.problem.Problem`
            The problem to add.

        Returns
        -------
        :class:`~compas_dem.problem.Problem`
            The problem that was added.

        Raises
        ------
        ValueError
            If the problem is defined over a different model than the analysis, or
            if it is unbound.
        """
        if self.model is None:
            self.model = problem.model
        elif problem.model_guid != str(self.model.guid):
            raise ValueError(
                f"Problem '{problem.name or problem.guid}' is defined over model {problem.model_guid}, "
                f"but this analysis holds model {self.model.guid}. An analysis covers one model; use a second analysis."
            )
        else:
            # Same model by guid, but possibly a different object after a round-trip.
            problem._bind_model(self.model)
        self.problems.append(problem)
        problem._analysis = self
        return problem

    def _record_results(self, problem: "Problem", results: "Results") -> None:
        """Store the results of a problem. Called by :meth:`~compas_dem.problem.Problem.solve`."""
        self.results[str(problem.guid)] = results

    def results_for(self, problem: "Problem") -> Optional["Results"]:
        """Return the stored results for a problem, or ``None`` if it has not been solved.

        Parameters
        ----------
        problem : :class:`~compas_dem.problem.Problem`

        Returns
        -------
        :class:`~compas_dem.problem.Results` | None
        """
        return self.results.get(str(problem.guid))
