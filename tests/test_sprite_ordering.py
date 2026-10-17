"""Verify that world sprites overlap according to depth across entity types."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pygame
import pygame.freetype
import pytest

from shooter.constants import EYE_HEIGHT, HEIGHT, WIDTH
from shooter.entities import Boss, Enemy, HealthPack, Rocket, WeaponPickup
from shooter.occlusion import DepthBuffer
from shooter.render_game import draw_frame
from shooter.render_sprites import Billboard, Camera, draw_enemy, draw_world_sprites
from shooter.state import GameState
from shooter.textures import generate_textures
from tests.support import ForegroundSprites, foreground_sprites, make_screen

Sprite = Enemy | HealthPack | WeaponPickup | Rocket | Billboard


def draw_sprites(
    depth: DepthBuffer,
    font: pygame.freetype.Font,
    screen: pygame.Surface,
    sprites: Sequence[Sprite],
    angle: float = 0.0,
    eye_height: float = EYE_HEIGHT,
) -> None:
    draw_world_sprites(
        screen,
        Camera(2.5, 5.5, angle, eye_height),
        depth,
        font,
        enemies=[s for s in sprites if isinstance(s, Enemy)],
        health_packs=[s for s in sprites if isinstance(s, HealthPack)],
        weapon_pickups=[s for s in sprites if isinstance(s, WeaponPickup)],
        rockets=[s for s in sprites if isinstance(s, Rocket)],
        billboards=[s for s in sprites if isinstance(s, Billboard)],
    )


def assert_composition(
    depth: DepthBuffer,
    font: pygame.freetype.Font,
    farther: Sprite,
    nearer: Sprite,
    angle: float = 0.0,
    eye_height: float = EYE_HEIGHT,
) -> None:
    # Single-object passes give a reference image with a known physical order.
    expected = make_screen()
    draw_sprites(depth, font, expected, [farther], angle, eye_height)
    draw_sprites(depth, font, expected, [nearer], angle, eye_height)
    expected_pixels = pygame.image.tobytes(expected, "RGB")
    reversed_order = make_screen()
    draw_sprites(depth, font, reversed_order, [nearer], angle, eye_height)
    draw_sprites(depth, font, reversed_order, [farther], angle, eye_height)
    assert expected_pixels != pygame.image.tobytes(reversed_order, "RGB"), (
        "The scene must visibly distinguish the two draw orders"
    )

    for sprites in ([nearer, farther], [farther, nearer]):
        actual = make_screen()
        draw_sprites(depth, font, actual, sprites, angle, eye_height)
        assert pygame.image.tobytes(actual, "RGB") == expected_pixels


@pytest.mark.parametrize("sprite_index", range(5), ids=ForegroundSprites._fields)
def test_near_enemy_covers_distant_pickups_effects_and_labels(
    sprite_index: int, depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    enemy = Enemy(4.5, 5.5)
    enemy.anim_time = 0.0
    farther = foreground_sprites(6.5)[sprite_index]
    assert_composition(depth, font, farther, enemy)


@pytest.mark.parametrize("sprite_index", range(5), ids=ForegroundSprites._fields)
def test_near_pickups_effects_and_labels_cover_distant_enemy(
    sprite_index: int, depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    enemy = Enemy(6.5, 5.5)
    enemy.anim_time = 0.0
    nearer = foreground_sprites(4.5)[sprite_index]
    assert_composition(depth, font, enemy, nearer)


@pytest.mark.parametrize("farther_index", range(2), ids=("health", "weapon"))
@pytest.mark.parametrize("nearer_index", range(2), ids=("health", "weapon"))
def test_pickups_sort_within_and_between_types(
    farther_index: int, nearer_index: int, depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    nearer = foreground_sprites(4.5)[nearer_index]
    farther = foreground_sprites(6.5)[farther_index]
    assert_composition(depth, font, farther, nearer)


@pytest.mark.parametrize("angle", (0.0, math.pi / 2), ids=("east", "south"))
def test_order_uses_camera_depth_when_euclidean_distances_disagree(
    angle: float, depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    enemy = Enemy(2.5 + 2.0 * cos_a - 0.7 * sin_a, 5.5 + 2.0 * sin_a + 0.7 * cos_a)
    health = HealthPack(2.5 + 2.01 * cos_a - 0.6 * sin_a, 5.5 + 2.01 * sin_a + 0.6 * cos_a)
    enemy.anim_time = health.anim_time = 0.0
    # The enemy's camera depth is smaller despite its longer radial distance.
    assert math.hypot(enemy.x - 2.5, enemy.y - 5.5) > math.hypot(health.x - 2.5, health.y - 5.5)
    assert_composition(depth, font, health, enemy, angle)


def test_boss_label_stays_over_its_boss_at_equal_depth(
    depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    boss = Boss(4.5, 5.5)
    boss.anim_time = 0.0
    label = Billboard("BOSS", boss.x, boss.y, (80, 20, 80))
    assert_composition(depth, font, boss, label)


@pytest.mark.parametrize("sprite_index", range(5), ids=ForegroundSprites._fields)
def test_partial_wall_cover_keeps_depth_order_at_jump_height(
    sprite_index: int, depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    depth.block_column(0, WIDTH, 1.0, 0, HEIGHT // 2)
    enemy = Enemy(4.5, 5.5)
    enemy.anim_time = 0.0
    farther = foreground_sprites(6.5)[sprite_index]
    assert_composition(depth, font, farther, enemy, eye_height=EYE_HEIGHT + 0.4)


def test_mixed_sprites_preserve_wall_clipping_at_jump_height(
    depth: DepthBuffer, font: pygame.freetype.Font
) -> None:
    depth.block_column(0, WIDTH, 1.0, 0, HEIGHT // 2)
    enemy = Enemy(4.5, 5.5)
    enemy.anim_time = 0.0
    screen = make_screen()
    blank = pygame.image.tobytes(screen, "RGB")
    covered = pygame.Rect(0, 0, WIDTH, HEIGHT // 2)
    before = pygame.image.tobytes(screen.subsurface(covered), "RGB")
    draw_sprites(
        depth, font, screen, [enemy, *foreground_sprites(6.5)], eye_height=EYE_HEIGHT + 0.4
    )
    assert pygame.image.tobytes(screen, "RGB") != blank
    assert pygame.image.tobytes(screen.subsurface(covered), "RGB") == before


def test_game_frame_keeps_distant_pickup_behind_enemy(
    depth: DepthBuffer, font: pygame.freetype.Font, state: GameState
) -> None:
    state.px, state.py = 2.5, 5.5
    enemy = Enemy(4.5, 5.5)
    health = HealthPack(6.5, 5.5)
    enemy.anim_time = health.anim_time = 0.0
    state.enemies = [enemy]
    state.health_packs = [health]

    expected = pygame.Surface((WIDTH, HEIGHT))
    draw_enemy(expected, enemy, Camera(state.px, state.py, state.pa), DepthBuffer())
    actual = pygame.Surface((WIDTH, HEIGHT))
    draw_frame(state, actual, font, generate_textures(), depth, False)
    # Opaque enemy torso, away from the crosshair and other HUD elements.
    point = (WIDTH // 2 + 16, HEIGHT // 2 + 16)
    assert actual.get_at(point) == expected.get_at(point)
