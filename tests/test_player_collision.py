"""Verify the player's footprint collision, the locked exit, and barrier jumps."""

from __future__ import annotations

import math
from unittest.mock import patch

import pygame
import pytest

from shooter import map as gmap
from shooter.constants import (
    DOOR_ANIM_DURATION,
    DOOR_RETRY_DELAY,
    GRAVITY,
    JUMP_VELOCITY,
    PLAYER_MARGIN,
    PLAYER_MOVE_SPEED,
    PLAYER_SPRINT_MULT,
)
from shooter.entities import Boss, Enemy
from shooter.input import handle_events
from shooter.map import LevelState
from shooter.simulation import update_doors, update_game, update_player
from shooter.state import GameState, check_win_lose
from shooter.types import DoorAnim, Sfx
from tests.support import Keys, SoundMocks


def distance_to_tile(x: float, y: float, col: int, row: int) -> float:
    return math.hypot(max(col - x, 0.0, x - col - 1), max(row - y, 0.0, y - row - 1))


def walk(
    sfx: Sfx, state: GameState, frames: int, keys: Keys | None = None, dt: int = 16
) -> list[tuple[float, float]]:
    """Hold W for some frames and return the path the player took."""
    path: list[tuple[float, float]] = []
    for _ in range(frames):
        update_player(state, dt, keys or Keys(), {pygame.KSCAN_W}, sfx)
        path.append((state.px, state.py))
    return path


@pytest.mark.parametrize(
    "key_code, scancode, dx, dy",
    (
        (pygame.K_w, pygame.KSCAN_W, 1, 0),
        (pygame.K_s, pygame.KSCAN_S, -1, 0),
        (pygame.K_a, pygame.KSCAN_A, 0, -1),
        (pygame.K_d, pygame.KSCAN_D, 0, 1),
        (pygame.K_z, pygame.KSCAN_W, 1, 0),
        (pygame.K_q, pygame.KSCAN_A, 0, -1),
    ),
    ids=("forward", "back", "left", "right", "azerty-forward", "azerty-left"),
)
def test_movement_key_events_start_hold_and_stop_motion(
    key_code: int,
    scancode: int,
    dx: int,
    dy: int,
    pressed: set[int],
    sfx: Sfx,
    state: GameState,
) -> None:
    state.px, state.py = 5.5, 5.5
    press = pygame.event.Event(pygame.KEYDOWN, key=key_code, scancode=scancode)
    with patch("shooter.input.pygame.event.get", return_value=[press]):
        assert handle_events(state, sfx, pressed)
    assert scancode in pressed

    for frame in (1, 2):
        assert update_game(state, 16, Keys(), pressed, sfx)
        distance = PLAYER_MOVE_SPEED * 16 * frame
        assert (state.px, state.py) == pytest.approx(
            (5.5 + dx * distance, 5.5 + dy * distance), rel=0, abs=1e-9
        )

    release = pygame.event.Event(pygame.KEYUP, key=key_code, scancode=scancode)
    with patch("shooter.input.pygame.event.get", return_value=[release]):
        assert handle_events(state, sfx, pressed)
    assert scancode not in pressed
    stopped = state.px, state.py
    assert not update_game(state, 16, Keys(), pressed, sfx)
    assert (state.px, state.py) == stopped


@pytest.mark.parametrize(
    "shift", (None, pygame.K_LSHIFT, pygame.K_RSHIFT), ids=("walk", "left-shift", "right-shift")
)
@pytest.mark.parametrize("angle", (0.0, math.pi / 3), ids=("east", "turned"))
@pytest.mark.parametrize("dt", (16, 50))
@pytest.mark.parametrize(
    "scancodes",
    (
        (pygame.KSCAN_W,),
        (pygame.KSCAN_W, pygame.KSCAN_A),
        (pygame.KSCAN_W, pygame.KSCAN_D),
        (pygame.KSCAN_S, pygame.KSCAN_A),
        (pygame.KSCAN_S, pygame.KSCAN_D),
    ),
    ids=("straight", "forward-left", "forward-right", "back-left", "back-right"),
)
def test_straight_and_diagonal_movement_share_walk_and_sprint_speeds(
    shift: int | None,
    angle: float,
    dt: int,
    scancodes: tuple[int, ...],
    sfx: Sfx,
    state: GameState,
) -> None:
    state.px, state.py, state.pa = 5.5, 5.5, angle
    keys = Keys() if shift is None else Keys(shift)

    assert update_player(state, dt, keys, set(scancodes), sfx)

    distance = math.hypot(state.px - 5.5, state.py - 5.5)
    expected = PLAYER_MOVE_SPEED * dt * (1 if shift is None else PLAYER_SPRINT_MULT)
    assert distance == pytest.approx(expected, rel=0, abs=1e-9)


def test_exit_stays_shut_until_the_boss_dies(sfx: Sfx, state: GameState, world: LevelState) -> None:
    exit_x = gmap.MAP_W - 1
    world.maze[5][exit_x] = gmap.EXIT_TILE
    world.exit_pos = exit_x, 5
    state.boss = Boss(10.5, 10.5)
    state.px, state.py, state.pa = exit_x - 2.5, 5.5, 0.0
    walk(sfx, state, 60)
    assert state.px == pytest.approx(exit_x - PLAYER_MARGIN, rel=0, abs=5e-6)
    with patch("shooter.state.start_level") as start_level:
        check_win_lose(state)
        start_level.assert_not_called()

        state.boss.alive = False
        walk(sfx, state, 10)
        assert int(state.px) == exit_x
        check_win_lose(state)
        start_level.assert_called_once_with(state, state.level + 1)


@pytest.mark.parametrize(
    "wall_tiles, start, angle",
    (
        (((6, 6),), (5.0, 5.0), math.pi / 4),
        (tuple((8, row) for row in range(1, gmap.MAP_H - 1)), (6.5, 2.5), math.radians(80)),
    ),
    ids=("corner", "glancing-wall"),
)
def test_footprint_keeps_its_margin_from_corners_and_glancing_walls(
    wall_tiles: tuple[tuple[int, int], ...],
    start: tuple[float, float],
    angle: float,
    sfx: Sfx,
    state: GameState,
    world: LevelState,
) -> None:
    for col, row in wall_tiles:
        world.maze[row][col] = 1
    state.px, state.py = start
    state.pa = angle
    path = walk(sfx, state, 200)
    closest = min(distance_to_tile(x, y, col, row) for x, y in path for col, row in wall_tiles)
    assert closest >= PLAYER_MARGIN - 1e-05


@pytest.mark.parametrize("dt", (16, 50))
def test_walls_stop_the_player_flush_at_any_frame_rate(
    dt: int, sfx: Sfx, state: GameState, world: LevelState
) -> None:
    world.maze[5][5] = 1
    state.px, state.py, state.pa = 2.5, 5.5, 0.0
    walk(sfx, state, 100, dt=dt)
    assert state.px == pytest.approx(5 - PLAYER_MARGIN, rel=0, abs=5e-6)


def test_barriers_block_on_foot_but_can_be_jumped(
    sfx: Sfx, state: GameState, world: LevelState
) -> None:
    world.maze[5][5] = gmap.BARRIER_TILE
    state.px, state.py, state.pa = 2.5, 5.5, 0.0
    walk(sfx, state, 100)
    assert state.px == pytest.approx(5 - PLAYER_MARGIN, rel=0, abs=5e-6)

    walk(sfx, state, 100, Keys(pygame.K_SPACE))
    assert state.px > 6 + PLAYER_MARGIN


def test_jump_clears_barriers_but_stays_below_the_ceiling(sfx: Sfx, state: GameState) -> None:
    state.px, state.py = 5.5, 5.5
    update_player(state, 16, Keys(pygame.K_SPACE), set(), sfx)
    peak = 0.0
    for _ in range(60):
        update_player(state, 16, Keys(), set(), sfx)
        peak = max(peak, state.jump_height)
    assert state.on_ground
    assert peak > 0.35
    assert peak < 0.45


@pytest.mark.parametrize(
    "schedule",
    (*((dt,) * (300 // dt) for dt in (10, 20, 30, 50)), (17, 43, 31, 9) * 3),
    ids=("10ms", "20ms", "30ms", "50ms", "irregular"),
)
def test_jump_trajectory_is_independent_of_frame_intervals(
    schedule: tuple[int, ...], sfx: Sfx, state: GameState
) -> None:
    elapsed = 0
    for index, dt in enumerate(schedule):
        keys = Keys(pygame.K_SPACE) if index == 0 else Keys()
        update_player(state, dt, keys, set(), sfx)
        elapsed += dt
        expected = JUMP_VELOCITY * elapsed - 0.5 * GRAVITY * elapsed**2
        assert state.jump_height == pytest.approx(expected, rel=0, abs=5e-8)
        assert not state.on_ground
    assert state.jump_height == pytest.approx(0.405, rel=0, abs=5e-8)
    for dt in schedule:
        update_player(state, dt, Keys(), set(), sfx)
    assert state.jump_height == pytest.approx(0, rel=0, abs=5e-11)
    # Step past landing to avoid relying on floating-point equality at t=600.
    update_player(state, 1, Keys(), set(), sfx)
    assert state.on_ground
    assert state.jump_vel == 0


@pytest.mark.parametrize(
    "px, closes",
    ((5 - PLAYER_MARGIN / 2, False), (5 - PLAYER_MARGIN - 0.01, True)),
    ids=("overlapping", "clear"),
)
def test_doors_stay_open_while_the_footprint_overlaps_them(
    px: float, closes: bool, sfx: Sfx, state: GameState, world: LevelState
) -> None:
    state.py = 5.5
    world.maze[5][5] = 0
    state.door_anim = {(5, 5): DoorAnim(phase="open", progress=1.0, timer=0)}
    state.px = px
    update_doors(state, 16, sfx)
    assert (world.tile_at(5.5, 5.5) == gmap.DOOR_TILE) == closes
    assert state.door_anim[5, 5]["phase"] == ("closing" if closes else "open")


@pytest.mark.parametrize("leaves", (True, False), ids=("enemy-leaves", "enemy-dies"))
def test_doors_retry_until_a_living_enemy_leaves_or_dies(
    leaves: bool, sounds: SoundMocks, state: GameState, world: LevelState
) -> None:
    enemy = Enemy(5.5, 5.5)
    state.enemies = [enemy]
    state.door_anim = {(5, 5): DoorAnim(phase="open", progress=1.0, timer=0)}

    update_doors(state, 16, sounds.sfx)
    assert world.tile_at(5.5, 5.5) == gmap.FLOOR_TILE
    assert state.door_anim[5, 5]["phase"] == "open"
    assert state.door_anim[5, 5]["timer"] == DOOR_RETRY_DELAY
    sounds["door_close"].play.assert_not_called()

    if leaves:
        enemy.x = 6.5
    else:
        enemy.take_damage(enemy.hp)
    update_doors(state, DOOR_RETRY_DELAY - 1, sounds.sfx)
    assert world.tile_at(5.5, 5.5) == gmap.FLOOR_TILE
    assert state.door_anim[5, 5]["phase"] == "open"
    sounds["door_close"].play.assert_not_called()

    update_doors(state, 1, sounds.sfx)
    assert world.tile_at(5.5, 5.5) == gmap.DOOR_TILE
    assert state.door_anim[5, 5]["phase"] == "closing"
    sounds["door_close"].play.assert_called_once()
    update_doors(state, DOOR_ANIM_DURATION, sounds.sfx)
    assert (5, 5) not in state.door_anim
    assert world.tile_at(5.5, 5.5) == gmap.DOOR_TILE
    sounds["door_close"].play.assert_called_once()


def test_e_reverses_a_closing_door_from_its_current_position(
    sfx: Sfx, state: GameState, world: LevelState
) -> None:
    world.maze[5][5] = gmap.DOOR_TILE
    state.px, state.py, state.pa = 3.5, 5.5, 0.0
    state.door_anim = {(5, 5): DoorAnim(phase="closing", progress=0.6, timer=0)}
    # The prompt and the key share this rule, so a closing door offers E again.
    assert state.targeted_door() == (5, 5)
    press_e = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, scancode=pygame.KSCAN_E)
    with patch("shooter.input.pygame.event.get", return_value=[press_e]):
        handle_events(state, sfx, set())
    assert state.door_anim[5, 5]["phase"] == "opening"
    assert state.door_anim[5, 5]["progress"] == 0.6
    assert state.targeted_door() is None
    update_doors(state, DOOR_ANIM_DURATION // 2, sfx)
    assert world.tile_at(5.5, 5.5) == gmap.FLOOR_TILE


@pytest.mark.parametrize(
    "down, scancodes",
    (
        ((), (pygame.KSCAN_W, pygame.KSCAN_S)),
        ((), (pygame.KSCAN_A, pygame.KSCAN_D)),
        ((pygame.K_DOWN,), (pygame.KSCAN_W,)),
    ),
    ids=("forward-back", "left-right", "arrow-back"),
)
def test_opposing_movement_keys_cancel_out(
    down: tuple[int, ...], scancodes: tuple[int, ...], sfx: Sfx, state: GameState
) -> None:
    keys = Keys(*down)
    pressed = set(scancodes)
    state.px, state.py = 5.5, 5.5
    assert not update_player(state, 16, keys, pressed, sfx)
    assert (state.px, state.py) == (5.5, 5.5)
