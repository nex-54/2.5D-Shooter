"""Verify that jumping raises the camera instead of tilting the view."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pygame
import pytest

from shooter import map as gmap
from shooter.constants import EYE_HEIGHT, HEIGHT, PLAYER_MARGIN, TEX_SIZE, WIDTH
from shooter.entities import Boss, Enemy, Scout, Spider
from shooter.map import LevelState
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_sprites import Camera, draw_enemy
from shooter.render_world import draw_3d, draw_floor_ceiling
from shooter.types import Textures

JUMP_PEAK = EYE_HEIGHT + 0.4
HORIZON = HEIGHT // 2


@pytest.mark.parametrize("eye", (EYE_HEIGHT, JUMP_PEAK), ids=("standing", "jumping"))
def test_horizon_stays_level_at_the_top_of_a_jump(
    eye: float, screen: pygame.Surface, world: LevelState
) -> None:
    red = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
    red[..., 0] = 200
    blue = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
    blue[..., 2] = 200
    textures: Textures = Textures(samples={"floor": red, "ceil": blue, "door": blue})
    draw_floor_ceiling(world, screen, 2.5, 5.5, 0.0, textures, eye)
    pixels = pygame.surfarray.array3d(screen)
    assert (pixels[:, :HORIZON, 0] == 0).all()
    assert (pixels[:, :HORIZON, 2] > 0).all()
    assert (pixels[:, HORIZON + 1 :, 0] > 0).all()
    assert (pixels[:, HORIZON + 1 :, 2] == 0).all()


def wall_rows(screen: pygame.Surface, world: LevelState, eye: float) -> tuple[int, int]:
    """First and last+1 rows of the flat-shaded wall in the center column."""
    draw_floor_ceiling(world, screen, 2.5, 5.5, 0.0, None, eye)
    before = pygame.surfarray.array3d(screen)[WIDTH // 2]
    draw_3d(screen, cast_rays(world, 2.5, 5.5, 0.0), DepthBuffer(), None, None, eye)
    after = pygame.surfarray.array3d(screen)[WIDTH // 2]
    rows = np.flatnonzero((after != before).any(axis=1))
    return int(rows[0]), int(rows[-1]) + 1


@pytest.mark.parametrize("wall_x, depth", ((4, 1.5), (8, 5.5)), ids=("near", "far"))
@pytest.mark.parametrize("eye", (EYE_HEIGHT, JUMP_PEAK), ids=("standing", "jumping"))
def test_rising_eye_sinks_near_walls_more_than_far_walls(
    wall_x: int, depth: float, eye: float, screen: pygame.Surface, world: LevelState
) -> None:
    # Walls are one unit tall; the eye sees their tops at (1 - eye) above it.
    world.maze[5][wall_x] = 1
    scale = HEIGHT / depth
    top, bottom = wall_rows(screen, world, eye)
    assert top == pytest.approx(HORIZON - (1 - eye) * scale, rel=0, abs=1)
    assert bottom == pytest.approx(min(HEIGHT, HORIZON + eye * scale), rel=0, abs=1)


@pytest.mark.parametrize("eye", (EYE_HEIGHT, JUMP_PEAK), ids=("standing", "jumping"))
def test_barriers_stand_on_the_floor(eye: float, screen: pygame.Surface, world: LevelState) -> None:
    world.maze[5][4] = gmap.BARRIER_TILE
    scale = HEIGHT / 1.5
    depth = DepthBuffer()
    draw_3d(screen, cast_rays(world, 2.5, 5.5, 0.0), depth, None, None, eye)
    rows = np.flatnonzero(np.isclose(depth.pixels[WIDTH // 2], 1.5))
    floor_row = HORIZON + eye * scale
    assert rows[-1] + 1 == pytest.approx(min(HEIGHT, floor_row), rel=0, abs=1)
    assert rows[0] == pytest.approx(floor_row - gmap.BARRIER_HEIGHT * scale, rel=0, abs=1)


def test_walls_at_arms_length_fill_the_view_with_bounded_scaling(
    screen: pygame.Surface, world: LevelState
) -> None:
    world.maze[5][3] = 1
    column = pygame.Surface((1, TEX_SIZE))
    column.fill((200, 0, 0))
    textures: Textures = Textures(columns={"wall": [column] * TEX_SIZE})
    walls = cast_rays(world, 3 - PLAYER_MARGIN, 5.5, 0.0)
    screen.fill((0, 0, 255))
    sizes: list[tuple[int, int]] = []
    scale = pygame.transform.scale

    def recording_scale(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        sizes.append(size)
        return scale(surface, size)

    with patch("shooter.render_world.pygame.transform.scale", side_effect=recording_scale):
        draw_3d(screen, walls, DepthBuffer(), None, textures, JUMP_PEAK)
    pixels = pygame.surfarray.array3d(screen)
    assert (pixels[..., 0] > 0).all()
    assert (pixels[..., 1:] == 0).all()
    assert max((height for _, height in sizes)) <= 2 * HEIGHT


@pytest.mark.parametrize(
    "depth, eye",
    ((2.0, EYE_HEIGHT), (4.0, EYE_HEIGHT), (3.0, JUMP_PEAK)),
    ids=("near-standing", "far-standing", "jumping"),
)
@pytest.mark.parametrize(
    "enemy_type", (Enemy, Scout, Spider, Boss), ids=("enemy", "scout", "spider", "boss")
)
def test_enemies_stand_on_the_floor_and_fit_under_the_ceiling(
    depth: float, eye: float, enemy_type: type[Enemy], screen: pygame.Surface
) -> None:
    # Sprites used to hang from eye height: small ones floated, the boss sank.
    enemy = enemy_type(2.5 + depth, 5.5)
    enemy.anim_time = 0.0
    screen.fill((0, 0, 0))
    draw_enemy(screen, enemy, Camera(2.5, 5.5, 0.0, eye), DepthBuffer())
    pixels = pygame.surfarray.array3d(screen).any(axis=2)
    rows = np.flatnonzero(pixels.any(axis=0))
    scale = HEIGHT / depth
    assert rows[-1] + 1 == pytest.approx(HORIZON + eye * scale, rel=0, abs=2)
    ceiling = HORIZON - (1 - eye) * scale
    if enemy_type is Boss:
        # The head reaches the ceiling; only the horns beside it rise past.
        head = np.flatnonzero(pixels[WIDTH // 2])
        assert head[0] >= ceiling - 1
        assert head[0] < ceiling + 0.05 * scale
    else:
        assert rows[0] > ceiling
