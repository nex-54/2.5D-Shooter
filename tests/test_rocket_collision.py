"""Projectile contact must agree with walls and splash visibility at every step."""

import math
from unittest.mock import patch

import pygame
import pytest

from shooter.combat import update_rockets
from shooter.constants import WEAPONS, Weapon
from shooter.entities import Enemy, Rocket
from shooter.input import handle_events
from shooter.map import BARRIER_TILE, DOOR_TILE
from shooter.state import GameState
from shooter.types import Sfx
from tests.support import SoundMocks


@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
@pytest.mark.parametrize(
    "start, end",
    (
        ((2.9, 3.2), (3.2, 2.9)),
        ((3.8, 2.9), (4.1, 3.2)),
        ((4.1, 3.8), (3.8, 4.1)),
        ((3.2, 4.1), (2.9, 3.8)),
        ((2.9, 3.1), (3.1, 2.9)),
    ),
    ids=("northwest", "northeast", "southeast", "southwest", "exact-corner"),
)
@pytest.mark.parametrize("tile", (1, DOOR_TILE), ids=("wall", "door"))
def test_corners_stop_rockets_even_when_both_endpoints_are_clear(
    reverse: bool,
    start: tuple[float, float],
    end: tuple[float, float],
    tile: int,
    sfx: Sfx,
    state: GameState,
) -> None:
    state.world.maze[3][3] = tile
    source, target = (end, start) if reverse else (start, end)
    rocket = Rocket(*source, math.atan2(target[1] - source[1], target[0] - source[0]))
    state.rockets = [rocket]
    update_rockets(state, 50, sfx)
    assert rocket.exploded
    assert not state.world.blocks_sight(rocket.x, rocket.y)
    assert state.world.has_line_of_sight(*source, rocket.x, rocket.y)


@pytest.mark.parametrize("dt", (8, 16, 50))
def test_wall_contact_is_independent_of_frame_size(dt: int, sfx: Sfx, state: GameState) -> None:
    state.world.maze[5][5] = 1
    rocket = Rocket(2.9, 5.5, 0.0)
    state.rockets = [rocket]
    for _ in range(100):
        update_rockets(state, dt, sfx)
        if rocket.exploded:
            break
    assert rocket.exploded
    assert rocket.x == pytest.approx(5.0, rel=0, abs=5e-6)
    assert rocket.x < 5.0


def test_muzzle_hits_close_wall_and_applies_self_damage_on_clear_side(
    sfx: Sfx, sounds: SoundMocks, state: GameState
) -> None:
    state.world.maze[5][5] = 1
    state.px, state.py = 4.79, 5.5
    state.weapon = Weapon.ROCKETS
    state.owned[Weapon.ROCKETS] = True
    state.ammo[WEAPONS[Weapon.ROCKETS].ammo_pool] = 1
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    with patch("shooter.input.pygame.event.get", return_value=[click]):
        handle_events(state, sfx, set())
    rocket = state.rockets[0]
    assert rocket.exploded
    assert rocket.x < 5
    assert not state.world.blocks_sight(rocket.x, rocket.y)
    assert state.hp < 100
    hp = state.hp
    update_rockets(state, 16, sfx)
    assert state.hp == hp
    sounds["explosion"].play.assert_called_once()


@pytest.mark.parametrize(
    "tile, source",
    ((1, (2.8, 3.1)), (BARRIER_TILE, (2.9, 3.2))),
    ids=("wall-miss", "barrier-crossing"),
)
def test_near_corner_miss_and_barriers_remain_clear(
    tile: int, source: tuple[float, float], sfx: Sfx, state: GameState
) -> None:
    state.world.maze[3][3] = tile
    rocket = Rocket(*source, -math.pi / 4)
    state.rockets = [rocket]
    update_rockets(state, 50, sfx)
    assert not rocket.exploded


def test_enemy_contacts_are_swept_and_nearest_contact_wins(sfx: Sfx, state: GameState) -> None:
    near = Enemy(5.0, 5.5)
    far = Enemy(8.0, 5.5)
    state.enemies = [far, near]
    rocket = Rocket(2.9, 5.5, 0.0)
    state.rockets = [rocket]
    update_rockets(state, 1000, sfx)
    assert rocket.exploded
    assert rocket.x == pytest.approx(4.4, rel=0, abs=5e-8)
    assert not near.alive
    assert far.hp == far.max_hp
    assert state.kills == 1
