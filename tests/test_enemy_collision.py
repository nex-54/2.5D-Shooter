"""Wandering and chasing enemies respect solid tiles while moving through clear space."""

import math
import random

import pytest

from shooter.entities import Boss, Enemy, Scout, Spider
from shooter.map import BARRIER_TILE, DOOR_TILE, EXIT_TILE, WALL_TILE, LevelState
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


@pytest.mark.parametrize(
    "dx, dy",
    ((1, 0), (-1, 0), (0, 1), (0, -1)),
    ids=("east", "west", "south", "north"),
)
@pytest.mark.parametrize(
    "enemy_type, tile",
    [
        pytest.param(enemy_type, tile, id=f"{enemy_type.__name__.lower()}-{name}")
        for enemy_type in (Enemy, Scout, Spider, Boss)
        for tile, name in (
            (WALL_TILE, "wall"),
            (DOOR_TILE, "door"),
            (BARRIER_TILE, "barrier"),
            (EXIT_TILE, "exit"),
        )
        # Bosses only chase with line of sight; opaque tiles trigger wandering instead.
        if enemy_type is not Boss or tile in (BARRIER_TILE, EXIT_TILE)
    ],
)
def test_chasing_enemies_cannot_cross_solid_tiles(
    dx: int, dy: int, enemy_type: type[Enemy], tile: int, world: LevelState
) -> None:
    world.maze[10][10] = tile
    x, y = 10.5 - dx * 0.501, 10.5 - dy * 0.501
    enemy = enemy_type(x, y, random.Random(0))
    enemy.alert = True

    enemy.update(world, x + dx * 4, y + dy * 4, 50)

    assert enemy.alert
    assert not enemy.attacking
    assert (enemy.x, enemy.y) == (x, y)


@pytest.mark.parametrize(
    "enemy_type", (Enemy, Scout, Spider, Boss), ids=("enemy", "scout", "spider", "boss")
)
def test_chasing_enemies_advance_toward_a_visible_player(
    enemy_type: type[Enemy], world: LevelState
) -> None:
    enemy = enemy_type(10.5, 10.5, random.Random(0))

    enemy.update(world, 14.5, 14.5, 50)

    assert enemy.alert
    assert enemy.moving
    assert not enemy.attacking
    assert enemy.x > 10.5
    assert enemy.y > 10.5
    assert math.hypot(enemy.x - 10.5, enemy.y - 10.5) == pytest.approx(enemy.speed * 50)
