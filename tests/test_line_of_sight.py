"""Verify sight and combat occlusion at walls, doors, barriers, and grid corners."""

from __future__ import annotations

import math

import pytest

from shooter import map as gmap
from shooter.combat import update_rockets
from shooter.entities import Enemy, Rocket, hitscan
from shooter.map import LevelState
from shooter.state import GameState
from shooter.types import Sfx


def assert_sight_both_directions(
    world: LevelState, start: tuple[float, float], end: tuple[float, float], expected: bool
) -> None:
    for source, target in ((start, end), (end, start)):
        assert world.has_line_of_sight(*source, *target) == expected


@pytest.mark.parametrize(
    "start, end",
    (
        ((2.9, 3.2), (3.2, 2.9)),
        ((3.8, 2.9), (4.1, 3.2)),
        ((4.1, 3.8), (3.8, 4.1)),
        ((3.2, 4.1), (2.9, 3.8)),
        ((1.5, 4.6), (4.8, 1.3)),
    ),
    ids=("northwest", "northeast", "southeast", "southwest", "diagonal"),
)
@pytest.mark.parametrize(
    "tile", (1, gmap.DOOR_TILE, gmap.BARRIER_TILE), ids=("wall", "door", "barrier")
)
def test_thin_wall_and_door_corner_crossings_block_sight(
    start: tuple[float, float], end: tuple[float, float], tile: int, world: LevelState
) -> None:
    world.maze[3][3] = tile
    assert_sight_both_directions(world, start, end, tile == gmap.BARRIER_TILE)


@pytest.mark.parametrize(
    "tile", (1, gmap.DOOR_TILE, gmap.BARRIER_TILE), ids=("wall", "door", "barrier")
)
def test_exact_corner_contacts_do_not_allow_sight_through_walls(
    tile: int, world: LevelState
) -> None:
    world.maze[3][3] = tile
    assert_sight_both_directions(world, (2.5, 3.5), (3.5, 2.5), tile == gmap.BARRIER_TILE)


@pytest.mark.parametrize(
    "start, end",
    (((2.8, 3.1), (3.1, 2.8)), ((2.0, 2.99), (5.0, 2.99)), ((2.99, 2.0), (2.99, 5.0))),
    ids=("diagonal", "horizontal", "vertical"),
)
def test_clear_paths_near_wall_corners_stay_visible(
    start: tuple[float, float], end: tuple[float, float], world: LevelState
) -> None:
    world.maze[3][3] = 1
    assert_sight_both_directions(world, start, end, True)


@pytest.mark.parametrize(
    "start, end",
    (
        ((2.5, 3.5), (3.0, 3.0)),
        ((3.0, 3.0), (4.0, 4.0)),
        ((2.0, 3.0), (5.0, 3.0)),
        ((3.0, 2.0), (3.0, 5.0)),
        ((3.25, 3.25), (3.25, 3.25)),
        ((3.25, 3.25), (3.26, 3.26)),
    ),
    ids=("corner-endpoint", "corner-start", "horizontal", "vertical", "same-point", "short"),
)
def test_grid_boundary_endpoints_and_axis_aligned_paths(
    start: tuple[float, float], end: tuple[float, float], world: LevelState
) -> None:
    assert_sight_both_directions(world, start, end, True)


@pytest.mark.parametrize("tile", (1, gmap.DOOR_TILE), ids=("wall", "door"))
def test_solid_endpoints_block_even_very_short_sight_lines(tile: int, world: LevelState) -> None:
    world.maze[3][3] = tile
    assert_sight_both_directions(world, (2.999, 3.5), (3.001, 3.5), False)
    assert_sight_both_directions(world, (3.5, 3.5), (3.5, 3.5), False)


def test_positions_outside_the_map_block_sight(world: LevelState) -> None:
    # Leave the boundary cell open to distinguish it from a negative coordinate.
    world.maze[3][0] = 0
    assert_sight_both_directions(world, (-0.01, 3.5), (0.5, 3.5), False)
    assert_sight_both_directions(world, (18.5, 3.5), (20.01, 3.5), False)


def test_wall_corners_block_hitscan_and_enemy_detection(world: LevelState) -> None:
    world.maze[3][3] = 1
    px, py = 2.9, 3.2
    enemy = Enemy(3.2, 2.9)
    angle = math.atan2(enemy.y - py, enemy.x - px)
    assert hitscan(world, [enemy], px, py, angle) is None
    enemy.update(world, px, py, 0)
    assert not enemy.alert
    assert not enemy.attacking


def test_wall_corner_shields_enemy_from_rocket_splash(sfx: Sfx, state: GameState) -> None:
    state.world.maze[3][3] = 1
    state.px, state.py = 2.5, 3.2
    sheltered = Enemy(3.2, 2.9)
    exposed = Enemy(2.85, 2.5)
    state.enemies = [sheltered, exposed]
    rocket = Rocket(2.9, 3.2, 0.0)
    state.rockets = [rocket]
    update_rockets(state, 16, sfx)
    assert rocket.exploded
    assert sheltered.hp == sheltered.max_hp
    assert not exposed.alive


def fire_rocket(sfx: Sfx, state: GameState, enemy: Enemy) -> Rocket:
    state.px, state.py = 2.5, 5.5
    state.enemies = [enemy]
    rocket = Rocket(2.9, 5.5, 0.0)
    state.rockets = [rocket]
    for _ in range(100):
        update_rockets(state, 16, sfx)
        if rocket.exploded:
            return rocket
    pytest.fail("rocket never detonated")


def test_barriers_do_not_block_sight_shots_or_rockets(
    sfx: Sfx, state: GameState, world: LevelState
) -> None:
    world.maze[5][4] = gmap.BARRIER_TILE
    enemy = Enemy(6.5, 5.5)
    assert hitscan(world, [enemy], 2.5, 5.5, 0.0) is enemy
    enemy.update(world, 2.5, 5.5, 16)
    assert enemy.alert
    rocket = fire_rocket(sfx, state, enemy)
    assert rocket.x > 5.0
    assert not enemy.alive


@pytest.mark.parametrize("tile", (1, gmap.DOOR_TILE), ids=("wall", "door"))
def test_walls_and_closed_doors_still_block(
    tile: int, sfx: Sfx, state: GameState, world: LevelState
) -> None:
    world.maze[5][4] = tile
    enemy = Enemy(6.5, 5.5)
    assert hitscan(world, [enemy], 2.5, 5.5, 0.0) is None
    enemy.update(world, 2.5, 5.5, 16)
    assert not enemy.alert
    rocket = fire_rocket(sfx, state, enemy)
    assert rocket.x < 4.0
    assert enemy.alive
