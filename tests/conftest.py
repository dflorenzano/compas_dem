import pytest
from compas.geometry import Box
from compas_dem.material import Stone
from compas_dem.models import BlockModel


@pytest.fixture
def unit_boxes() -> BlockModel:
    """A model of two stacked 1 m unit cubes with a known density.

    Each block has a volume of 1 m³ and a density of 2000 kg/m³, so its mass is
    exactly 2000 kg — which makes body force resultants checkable by hand. The lower
    block (graph node 0) is a support.
    """
    model = BlockModel.from_boxes(
        [
            Box(xsize=1, ysize=1, zsize=1, frame=None).translated([0, 0, 0.5]),
            Box(xsize=1, ysize=1, zsize=1, frame=None).translated([0, 0, 1.5]),
        ]
    )
    stone = Stone(density=2000)
    model.add_material(stone)
    model.assign_material(stone, elements=list(model.elements()))
    blocks = list(model.elements())
    blocks[0].is_support = True
    return model


@pytest.fixture
def block_indices(unit_boxes) -> list:
    """The graph node indices of the fixture blocks, lower first."""
    return [block.graphnode for block in unit_boxes.elements()]
