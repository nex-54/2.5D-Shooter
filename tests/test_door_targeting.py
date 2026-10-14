"""Door interaction stops at the first obstacle, including thin corner crossings."""

import math

import pytest

from shooter.map import BARRIER_TILE, DOOR_TILE, EXIT_TILE, WALL_TILE
from tests.support import open_world


def test_wall_corner_cannot_be_skipped_to_open_a_hidden_door() -> None:
    world = open_world()
    world.maze[3][3] = WALL_TILE
    world.maze[2][4] = DOOR_TILE
    assert world.find_door_in_front(2.3, 3.3, -0.404) is None


def test_door_corner_cannot_be_skipped_for_a_farther_door() -> None:
    world = open_world()
    world.maze[3][3] = DOOR_TILE
    world.maze[2][4] = DOOR_TILE
    assert world.find_door_in_front(2.3, 3.3, -0.404) == (3, 3)


@pytest.mark.parametrize(
    "x, y, angle",
    ((4.3, 5.5, 0.0), (6.7, 5.5, math.pi), (5.5, 4.3, math.pi / 2), (5.5, 6.7, -math.pi / 2)),
    ids=("west", "east", "north", "south"),
)
def test_door_is_targeted_from_all_four_sides_at_its_actual_range(
    x: float, y: float, angle: float
) -> None:
    world = open_world()
    world.maze[5][5] = DOOR_TILE
    assert world.find_door_in_front(x, y, angle, max_range=0.69) is None
    assert world.find_door_in_front(x, y, angle, max_range=0.71) == (5, 5)


@pytest.mark.parametrize(
    "tile", (WALL_TILE, BARRIER_TILE, EXIT_TILE), ids=("wall", "barrier", "exit")
)
def test_other_solid_tiles_block_interaction(tile: int) -> None:
    world = open_world()
    world.maze[5][5] = tile
    world.maze[5][6] = DOOR_TILE
    assert world.find_door_in_front(4.5, 5.5, 0) is None


@pytest.mark.parametrize(
    "angle", (0, math.pi / 2, math.pi, -math.pi / 2), ids=("east", "south", "west", "north")
)
def test_clear_space_and_map_boundaries_have_no_door(angle: float) -> None:
    world = open_world()
    assert world.find_door_in_front(1.5, 1.5, angle) is None
