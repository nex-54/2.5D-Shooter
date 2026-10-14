"""Headless regression checks for explosion allocation and viewport clipping."""

from __future__ import annotations

from unittest.mock import patch

import pygame
import pytest

from shooter.constants import EXPLOSION_DURATION, EYE_HEIGHT, HEIGHT, WIDTH
from shooter.entities import Rocket
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import Camera, draw_rocket

BACKGROUND = (17, 29, 41)


def make_screen() -> pygame.Surface:
    screen = pygame.Surface((WIDTH, HEIGHT))
    screen.fill(BACKGROUND)
    return screen


def draw_explosion(
    depth: DepthBuffer, screen: pygame.Surface, distance: float = 4.0, shift: int = 0
) -> None:
    rocket = Rocket(distance, 0.0, 0.0)
    rocket.exploded = True
    rocket.explosion_timer = EXPLOSION_DURATION // 4
    # Raising the eye by shift * depth / HEIGHT lowers the sprite by shift pixels.
    camera = Camera(0.0, 0.0, 0.0, EYE_HEIGHT + shift * distance / HEIGHT)
    draw_rocket(screen, rocket, camera, depth)


@pytest.mark.parametrize("distance", (0.101, 0.15, 0.4))
def test_close_explosions_bound_allocations_and_preserve_fade(
    distance: float, depth: DepthBuffer
) -> None:
    # At this age the core is one-quarter opaque and covers the viewport.
    expected = pygame.Surface((1, 1))
    expected.fill(BACKGROUND)
    core = pygame.Surface((1, 1), pygame.SRCALPHA)
    core.fill((255, 240, 180, 63))
    expected.blit(core, (0, 0))
    surface_type = pygame.Surface

    def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
        # Fail before attempting the old gigabyte-scale allocation.
        assert size[0] <= WIDTH
        assert size[1] <= HEIGHT
        return surface_type(size, flags)

    screen = make_screen()
    with patch("shooter.render_sprites.pygame.Surface", side_effect=bounded_surface):
        draw_explosion(depth, screen, distance)
    for point in ((0, 0), (WIDTH // 2, HEIGHT // 2), (WIDTH - 1, HEIGHT - 1)):
        assert screen.get_at(point) == expected.get_at((0, 0))


@pytest.mark.parametrize("shift", (-HEIGHT // 2 - 48, HEIGHT // 2 + 48), ids=("above", "below"))
def test_offscreen_centers_preserve_visible_circle_shape(shift: int, depth: DepthBuffer) -> None:
    reference = make_screen()
    draw_explosion(depth, reference)

    expected = make_screen()
    expected.blit(reference, (0, shift))
    actual = make_screen()
    draw_explosion(depth, actual, shift=shift)
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected, "RGB")


def test_allocation_respects_surface_clip(depth: DepthBuffer) -> None:
    reference = make_screen()
    draw_explosion(depth, reference)
    clip = pygame.Rect(WIDTH // 2, HEIGHT // 2, 80, 60)
    expected = make_screen()
    expected.set_clip(clip)
    expected.blit(reference, (0, 0))
    actual = make_screen()
    actual.set_clip(clip)

    with patch("shooter.render_sprites.pygame.Surface", wraps=pygame.Surface) as allocate:
        draw_explosion(depth, actual)

    assert allocate.call_args.args[0] == clip.size
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected, "RGB")


def test_fully_offscreen_explosion_allocates_nothing(depth: DepthBuffer) -> None:
    screen = make_screen()
    before = pygame.image.tobytes(screen, "RGB")
    with patch("shooter.render_sprites.pygame.Surface") as allocate:
        draw_explosion(depth, screen, shift=HEIGHT * 2)
    allocate.assert_not_called()
    assert pygame.image.tobytes(screen, "RGB") == before
