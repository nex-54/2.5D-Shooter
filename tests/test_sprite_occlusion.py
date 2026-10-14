"""Render small scenes to verify visible openings and opaque wall coverage."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pygame
import pygame.freetype
import pytest

from shooter import map as gmap
from shooter.constants import EXPLOSION_DURATION, EYE_HEIGHT, HEIGHT, WIDTH, Weapon
from shooter.entities import Boss, Enemy, HealthPack, Rocket, Scout, Spider, WeaponPickup
from shooter.map import LevelState
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_sprites import (
    Billboard,
    Camera,
    draw_billboard,
    draw_enemy,
    draw_health_pack,
    draw_rocket,
    draw_weapon_pickup,
)
from shooter.render_world import draw_3d
from shooter.types import DoorAnim, DoorAnimMap


@pytest.fixture
def enemy() -> Enemy:
    enemy = Enemy(6.5, 5.5)
    enemy.anim_time = 0.0
    return enemy


@pytest.fixture
def camera() -> Camera:
    return Camera(2.5, 5.5, 0.0)


@pytest.fixture
def doors() -> DoorAnimMap:
    return {}


def draw_world(
    depth: DepthBuffer,
    doors: DoorAnimMap,
    screen: pygame.Surface,
    world: LevelState,
    eye_height: float = EYE_HEIGHT,
) -> None:
    screen.fill((9, 11, 13))
    walls = cast_rays(world, 2.5, 5.5, 0.0, doors)
    draw_3d(screen, walls, depth, None, None, eye_height, doors)


def draw_clipped_enemy(
    depth: DepthBuffer, enemy: Enemy, screen: pygame.Surface, eye_height: float = EYE_HEIGHT
) -> None:
    draw_enemy(screen, enemy, Camera(2.5, 5.5, 0.0, eye_height), depth)


def test_barrier_hides_feet_until_a_jump_sees_over_it(
    camera: Camera,
    depth: DepthBuffer,
    doors: DoorAnimMap,
    enemy: Enemy,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    world.maze[5][4] = gmap.BARRIER_TILE
    enemy.x = 5.5
    draw_world(depth, doors, screen, world)
    before = pygame.surfarray.array3d(screen)
    unclipped = screen.copy()
    draw_enemy(unclipped, enemy, camera, DepthBuffer())
    draw_clipped_enemy(depth, enemy, screen)
    after = pygame.surfarray.array3d(screen)
    # Standing, the barrier covers rows 469-639, over the enemy's feet.
    assert np.any(pygame.surfarray.array3d(unclipped)[:, 469:640] != before[:, 469:640])
    assert np.any(after[:, :469] != before[:, :469])
    np.testing.assert_array_equal(after[:, 469:640], before[:, 469:640])

    # At the top of a jump the eye clears the barrier, so the whole enemy shows.
    eye = EYE_HEIGHT + 0.4
    draw_world(depth, doors, screen, world, eye)
    expected = screen.copy()
    draw_enemy(expected, enemy, Camera(2.5, 5.5, 0.0, eye), DepthBuffer())
    draw_clipped_enemy(depth, enemy, screen, eye)
    assert pygame.image.tobytes(screen, "RGB") == pygame.image.tobytes(expected, "RGB")


@pytest.mark.parametrize(
    "enemy_type",
    (Enemy, Boss, Scout, Spider),
    ids=("enemy", "boss", "scout", "spider"),
)
def test_full_wall_hides_every_enemy_type(
    enemy_type: type[Enemy],
    depth: DepthBuffer,
    doors: DoorAnimMap,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    world.maze[5][4] = 1
    enemy = enemy_type(6.5, 5.5)
    draw_world(depth, doors, screen, world)
    before = pygame.image.tobytes(screen, "RGB")
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") == before


def test_enemy_in_front_of_barrier_is_not_clipped(
    camera: Camera,
    depth: DepthBuffer,
    doors: DoorAnimMap,
    enemy: Enemy,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    world.maze[5][4] = gmap.BARRIER_TILE
    enemy.x = 3.5
    draw_world(depth, doors, screen, world)
    expected = screen.copy()
    draw_enemy(expected, enemy, camera, DepthBuffer())
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") == pygame.image.tobytes(expected, "RGB")


def test_opening_door_reveals_only_the_gap(
    camera: Camera,
    depth: DepthBuffer,
    doors: DoorAnimMap,
    enemy: Enemy,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    world.maze[5][4] = gmap.DOOR_TILE
    draw_world(depth, doors, screen, world)
    before = pygame.image.tobytes(screen, "RGB")
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") == before

    for phase in ("opening", "closing"):
        doors[(4, 5)] = DoorAnim(phase=phase, progress=0.5, timer=0)
        draw_world(depth, doors, screen, world)
        before = pygame.surfarray.array3d(screen)
        draw_clipped_enemy(depth, enemy, screen)
        after = pygame.surfarray.array3d(screen)
        np.testing.assert_array_equal(after[:, :384], before[:, :384])
        assert np.any(after[:, 384:] != before[:, 384:])

    doors[(4, 5)] = DoorAnim(phase="open", progress=1.0, timer=5000)
    draw_world(depth, doors, screen, world)
    expected = screen.copy()
    draw_enemy(expected, enemy, camera, DepthBuffer())
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") == pygame.image.tobytes(expected, "RGB")


@pytest.mark.parametrize(
    "foreground, background",
    ((gmap.BARRIER_TILE, 1), (gmap.DOOR_TILE, gmap.DOOR_TILE)),
    ids=("barrier-wall", "door-door"),
)
def test_background_wall_or_closed_door_still_hides_enemies(
    foreground: int,
    background: int,
    depth: DepthBuffer,
    doors: DoorAnimMap,
    enemy: Enemy,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    world.maze[5][4] = foreground
    world.maze[5][5] = background
    doors[(4, 5)] = DoorAnim(phase="opening", progress=0.5, timer=0)
    draw_world(depth, doors, screen, world)
    before = pygame.image.tobytes(screen, "RGB")
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") == before


def test_stacked_barriers_preserve_the_farther_barriers_coverage(
    depth: DepthBuffer, doors: DoorAnimMap, enemy: Enemy, screen: pygame.Surface, world: LevelState
) -> None:
    world.maze[5][4] = gmap.BARRIER_TILE
    world.maze[5][5] = gmap.BARRIER_TILE
    draw_world(depth, doors, screen, world)
    before = pygame.surfarray.array3d(screen)
    draw_clipped_enemy(depth, enemy, screen)
    after = pygame.surfarray.array3d(screen)
    # The farther barrier rises to row 435, above the nearer one's row 469.
    assert np.any(after[:, :435] != before[:, :435])
    np.testing.assert_array_equal(after[:, 435:640], before[:, 435:640])


def test_depth_is_cleared_between_frames(
    depth: DepthBuffer, doors: DoorAnimMap, enemy: Enemy, screen: pygame.Surface, world: LevelState
) -> None:
    world.maze[5][4] = 1
    draw_world(depth, doors, screen, world)
    world.maze[5][4] = 0
    draw_world(depth, doors, screen, world)
    before = pygame.image.tobytes(screen, "RGB")
    draw_clipped_enemy(depth, enemy, screen)
    assert pygame.image.tobytes(screen, "RGB") != before


@pytest.mark.parametrize("sprite_name", ("health", "weapon", "rocket", "explosion", "label"))
@pytest.mark.parametrize("tile", (gmap.BARRIER_TILE, 1), ids=("barrier", "wall"))
def test_pickups_labels_and_projectiles_use_the_same_height_clipping(
    sprite_name: str,
    tile: int,
    font: pygame.freetype.Font,
    camera: Camera,
    depth: DepthBuffer,
    doors: DoorAnimMap,
    screen: pygame.Surface,
    world: LevelState,
) -> None:
    health = HealthPack(6.5, 5.5)
    weapon = WeaponPickup(6.5, 5.5, Weapon.SHOTGUN)
    rocket = Rocket(6.5, 5.5, 0.0)
    explosion = Rocket(6.5, 5.5, 0.0)
    explosion.exploded = True
    explosion.explosion_timer = EXPLOSION_DURATION // 4
    label = Billboard("TEST", 6.5, 5.5, (20, 20, 80))
    health.anim_time = weapon.anim_time = 0.0
    drawers = {
        "health": lambda: draw_health_pack(screen, health, camera, depth),
        "weapon": lambda: draw_weapon_pickup(screen, weapon, camera, depth),
        "rocket": lambda: draw_rocket(screen, rocket, camera, depth),
        "explosion": lambda: draw_rocket(screen, explosion, camera, depth),
        "label": lambda: draw_billboard(screen, font, label, camera, depth),
    }
    world.maze[5][4] = tile
    draw = drawers[sprite_name]
    draw_world(depth, doors, screen, world)
    before = pygame.surfarray.array3d(screen)
    draw()
    after = pygame.surfarray.array3d(screen)
    if tile == 1:
        np.testing.assert_array_equal(after, before)
    else:
        assert np.any(after != before)
        np.testing.assert_array_equal(after[:, 469:640], before[:, 469:640])


def test_partially_hidden_close_explosion_keeps_allocations_bounded(
    depth: DepthBuffer, screen: pygame.Surface
) -> None:
    screen.fill((9, 11, 13))
    depth.block_column(0, WIDTH, 0.01, HEIGHT // 2)
    rocket = Rocket(0.15, 0.0, 0.0)
    rocket.exploded = True
    rocket.explosion_timer = EXPLOSION_DURATION // 4
    surface_type = pygame.Surface

    def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
        assert size[0] <= WIDTH
        assert size[1] <= HEIGHT
        return surface_type(size, flags)

    with patch("shooter.render_sprites.pygame.Surface", side_effect=bounded_surface):
        draw_rocket(screen, rocket, Camera(0.0, 0.0, 0.0), depth)
    assert screen.get_at((WIDTH // 2, 100))[:3] != (9, 11, 13)
    assert screen.get_at((WIDTH // 2, HEIGHT - 100))[:3] == (9, 11, 13)
