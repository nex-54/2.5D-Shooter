"""Headless regression checks for explosion allocation and viewport clipping."""

from __future__ import annotations

import pygame
import pytest

from shooter.constants import EYE_HEIGHT, HEIGHT, WIDTH
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import Camera, draw_rocket
from tests.support import BACKGROUND, exploding_rocket, make_screen, surface_allocations


def draw_explosion(
    depth: DepthBuffer, screen: pygame.Surface, distance: float = 4.0, shift: int = 0
) -> None:
    # Raising the eye by shift * depth / HEIGHT lowers the sprite by shift pixels.
    camera = Camera(0.0, 0.0, 0.0, EYE_HEIGHT + shift * distance / HEIGHT)
    draw_rocket(screen, exploding_rocket(distance, 0.0), camera, depth)


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

    screen = make_screen()
    with surface_allocations():
        draw_explosion(depth, screen, distance)
    for point in ((0, 0), (WIDTH // 2, HEIGHT // 2), (WIDTH - 1, HEIGHT - 1)):
        assert screen.get_at(point) == expected.get_at((0, 0))


def test_partially_hidden_close_explosion_keeps_allocations_bounded(depth: DepthBuffer) -> None:
    depth.block_column(0, WIDTH, 0.01, HEIGHT // 2)
    screen = make_screen()
    with surface_allocations():
        draw_explosion(depth, screen, 0.15)
    assert screen.get_at((WIDTH // 2, 100))[:3] != BACKGROUND
    assert screen.get_at((WIDTH // 2, HEIGHT - 100))[:3] == BACKGROUND


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

    with surface_allocations() as allocate:
        draw_explosion(depth, actual)

    assert allocate.call_args.args[0] == clip.size
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected, "RGB")


def test_fully_offscreen_explosion_allocates_nothing(depth: DepthBuffer) -> None:
    screen = make_screen()
    before = pygame.image.tobytes(screen, "RGB")
    with surface_allocations() as allocate:
        draw_explosion(depth, screen, shift=HEIGHT * 2)
    allocate.assert_not_called()
    assert pygame.image.tobytes(screen, "RGB") == before
