"""Keep pickup halo allocations bounded without changing visible pixels."""

from __future__ import annotations

import math
from unittest.mock import patch

import pygame
import pytest

from shooter.constants import EYE_HEIGHT, HEIGHT, WIDTH, Weapon
from shooter.entities import PICKUP_WEAPONS, WeaponPickup
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import Camera, draw_weapon_pickup

BACKGROUND = (17, 29, 41)


@pytest.fixture
def pickup() -> WeaponPickup:
    pickup = WeaponPickup(4.0, 0.0, Weapon.PISTOL)
    pickup.anim_time = math.pi / 4
    return pickup


def make_screen() -> pygame.Surface:
    screen = pygame.Surface((WIDTH, HEIGHT))
    screen.fill(BACKGROUND)
    return screen


def draw_pickup(
    depth: DepthBuffer, pickup: WeaponPickup, screen: pygame.Surface, shift: int = 0
) -> None:
    # Translate vertically without changing the pickup's projected size.
    eye_height = EYE_HEIGHT + shift * pickup.x / HEIGHT
    draw_weapon_pickup(screen, pickup, Camera(0.0, 0.0, 0.0, eye_height), depth)


@pytest.mark.parametrize("distance", (0.301, 0.31, 0.6))
@pytest.mark.parametrize(
    "weapon_type", PICKUP_WEAPONS, ids=tuple(weapon.name.lower() for weapon in PICKUP_WEAPONS)
)
def test_close_pickups_keep_allocations_within_viewport(
    distance: float, weapon_type: Weapon, depth: DepthBuffer, pickup: WeaponPickup
) -> None:
    surface_type = pygame.Surface

    def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
        assert size[0] <= WIDTH
        assert size[1] <= HEIGHT
        return surface_type(size, flags)

    pickup.weapon_type = weapon_type
    pickup.x = distance
    screen = make_screen()
    with patch("shooter.render_sprites.pygame.Surface", side_effect=bounded_surface) as allocate:
        draw_pickup(depth, pickup, screen)
    allocate.assert_called_once()
    assert screen.get_at((0, 0))[:3] != BACKGROUND


@pytest.mark.parametrize("shift", (-HEIGHT // 2 - 48, HEIGHT // 2 + 48), ids=("above", "below"))
@pytest.mark.parametrize("phase", (0.0, math.pi / 4), ids=("zero-phase", "quarter-phase"))
def test_offscreen_centers_preserve_halo_shape_and_alpha(
    shift: int, phase: float, depth: DepthBuffer, pickup: WeaponPickup
) -> None:
    pickup.anim_time = phase
    reference = make_screen()
    draw_pickup(depth, pickup, reference)
    expected = make_screen()
    expected.blit(reference, (0, shift))
    actual = make_screen()
    draw_pickup(depth, pickup, actual, shift)
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected, "RGB")


@pytest.mark.parametrize("occluded", (False, True), ids=("visible", "occluded"))
@pytest.mark.parametrize("distance", (0.31, 4.0))
def test_surface_clip_and_wall_occlusion_preserve_visible_pixels(
    occluded: bool, distance: float, depth: DepthBuffer, pickup: WeaponPickup
) -> None:
    clip = pygame.Rect(80, 120, WIDTH - 160, HEIGHT - 240)
    pickup.x = distance
    depth.clear()
    reference = make_screen()
    draw_pickup(depth, pickup, reference)
    expected = make_screen()
    expected.set_clip(clip)
    expected.blit(reference, (0, 0))
    if occluded:
        depth.block_column(0, WIDTH, 0.01, HEIGHT // 2)
        expected.fill(BACKGROUND, (0, HEIGHT // 2, WIDTH, HEIGHT // 2))
    actual = make_screen()
    actual.set_clip(clip)
    with patch("shooter.render_sprites.pygame.Surface", wraps=pygame.Surface) as allocate:
        draw_pickup(depth, pickup, actual)
    assert allocate.call_count == (2 if occluded else 1)
    for call in allocate.call_args_list:
        width, height = call.args[0]
        assert width <= clip.width
        assert height <= clip.height
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected, "RGB")


@pytest.mark.parametrize("hidden_by_wall", (False, True), ids=("offscreen", "behind-wall"))
def test_invisible_pickup_allocates_nothing(
    hidden_by_wall: bool, depth: DepthBuffer, pickup: WeaponPickup
) -> None:
    screen = make_screen()
    before = pygame.image.tobytes(screen, "RGB")
    if hidden_by_wall:
        depth.block_column(0, WIDTH, 0.01)
    with patch("shooter.render_sprites.pygame.Surface") as allocate:
        draw_pickup(depth, pickup, screen, shift=0 if hidden_by_wall else HEIGHT * 2)
    allocate.assert_not_called()
    assert pygame.image.tobytes(screen, "RGB") == before
