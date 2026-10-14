"""Wandering enemies respect the same solid tiles as chasing enemies."""

import math
import random

import pytest

from shooter.entities import Boss, Enemy, Scout, Spider
from shooter.map import BARRIER_TILE, DOOR_TILE, EXIT_TILE, WALL_TILE
from tests.support import open_world


@pytest.mark.parametrize("dt", (16, 50))
@pytest.mark.parametrize(
    "dx, dy",
    ((1, 1), (1, -1), (-1, 1), (-1, -1)),
    ids=("southeast", "northeast", "southwest", "northwest"),
)
@pytest.mark.parametrize(
    "tile", (WALL_TILE, DOOR_TILE, BARRIER_TILE, EXIT_TILE), ids=("wall", "door", "barrier", "exit")
)
@pytest.mark.parametrize(
    "enemy_type",
    (Enemy, Boss, Scout, Spider),
    ids=("enemy", "boss", "scout", "spider"),
)
def test_wandering_cannot_enter_solid_tile_corners(
    dt: int, dx: int, dy: int, tile: int, enemy_type: type[Enemy]
) -> None:
    world = open_world()
    world.maze[10][10] = tile
    x = 9.999 if dx > 0 else 11.001
    y = 9.999 if dy > 0 else 11.001
    enemy = enemy_type(x, y, random.Random(0))
    enemy.wander_angle = math.atan2(dy, dx)
    enemy.wander_timer = 1000

    enemy.update(world, 1.5, 1.5, dt)

    assert not world.is_obstacle(enemy.x, enemy.y)
    assert world.tile_at(enemy.x, enemy.y) != EXIT_TILE


@pytest.mark.parametrize(
    "enemy_type",
    (Enemy, Boss, Scout, Spider),
    ids=("enemy", "boss", "scout", "spider"),
)
def test_wandering_still_moves_through_clear_space(enemy_type: type[Enemy]) -> None:
    enemy = enemy_type(10.5, 10.5, random.Random(0))
    enemy.wander_angle = math.pi / 4
    enemy.wander_timer = 1000

    enemy.update(open_world(), 1.5, 1.5, 50)

    assert enemy.x > 10.5
    assert enemy.y > 10.5
    assert enemy.moving
