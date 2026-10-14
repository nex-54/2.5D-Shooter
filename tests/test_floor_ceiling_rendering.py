"""Headless rendering checks for texture sampling and cache invalidation."""

from __future__ import annotations

import numpy as np
import pygame
import pytest

from shooter.constants import EYE_HEIGHT, HEIGHT, TEX_SIZE, WIDTH
from shooter.map import LevelState
from shooter.render_world import draw_floor_ceiling
from shooter.types import Textures


@pytest.fixture
def world() -> LevelState:
    return LevelState()


@pytest.fixture
def textures() -> Textures:
    x, y = np.indices((TEX_SIZE, TEX_SIZE))
    return Textures(
        samples={
            "floor": np.stack((20 + x * 3, 30 + y * 2, 40 + x + y), axis=-1).astype(np.float32),
            "ceil": np.stack((15 + x * 2, 10 + y * 3, 20 + x + y), axis=-1).astype(np.float32),
            "door": np.full((TEX_SIZE, TEX_SIZE, 3), (100, 120, 140), np.float32),
        }
    )


def test_sampled_pixels_match_recorded_baseline(
    screen: pygame.Surface, textures: Textures, world: LevelState
) -> None:
    # Baseline pixels cross-checked against a per-pixel scalar reference,
    # with coordinate-coded textures so shifts, wrapping, shading and x/y
    # swaps are observable.
    points = (
        (0, 0),
        (173, 61),
        (512, 200),
        (1023, 333),
        (91, 385),
        (780, 527),
        (411, 703),
        (1023, 767),
    )
    cases = (
        (
            (1.5, 1.5, 0.0, EYE_HEIGHT),
            (
                (73, 173, 103),
                (94, 20, 62),
                (75, 90, 75),
                (8, 79, 34),
                (13, 5, 9),
                (43, 50, 54),
                (141, 71, 99),
                (107, 35, 70),
            ),
        ),
        (
            (5.125, 8.375, 1.9, 0.7),
            (
                (45, 18, 37),
                (29, 32, 34),
                (97, 104, 92),
                (26, 111, 56),
                (24, 17, 19),
                (142, 76, 99),
                (142, 28, 77),
                (172, 77, 112),
            ),
        ),
        (
            (1.5, 1.5, 3.9, 0.9),
            (
                (48, 92, 64),
                (48, 83, 60),
                (37, 47, 43),
                (13, 153, 66),
                (11, 12, 12),
                (132, 37, 74),
                (144, 44, 85),
                (166, 83, 113),
            ),
        ),
        (
            (3.25, 6.75, 6.2, 0.25),
            (
                (90, 137, 99),
                (121, 168, 125),
                (47, 80, 57),
                (3, 13, 8),
                (8, 17, 13),
                (124, 27, 71),
                (174, 105, 128),
                (161, 150, 146),
            ),
        ),
    )
    for (px, py, pa, eye), colors in (*cases, cases[0]):
        screen.fill((1, 2, 3))
        draw_floor_ceiling(world, screen, px, py, pa, textures, eye)
        for point, color in zip(points, colors, strict=True):
            assert screen.get_at(point)[:3] == color, ((px, py, pa, eye), point)
        assert not screen.get_locked()


@pytest.mark.parametrize("x", (0, WIDTH // 4, WIDTH - 1), ids=("left", "quarter", "right"))
def test_lines_facing_the_camera_stay_straight(
    x: int, screen: pygame.Surface, world: LevelState
) -> None:
    # Texel column 0 marks every integer x on the floor and ceiling. Facing
    # +x, each mark lies at one perpendicular distance, so every screen
    # column must show it on the same rows; unit-length rays bent them.
    stripes = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
    stripes[0] = 255
    textures: Textures = Textures(samples={"floor": stripes, "ceil": stripes, "door": stripes})
    screen.fill((0, 0, 0))
    draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, textures)
    pixels: np.typing.NDArray[np.uint8] = pygame.surfarray.array3d(screen)
    marked = pixels.any(axis=2)
    assert marked[WIDTH // 2].any()
    np.testing.assert_array_equal(marked[x], marked[WIDTH // 2])


def test_door_ceiling_updates_after_level_layout_changes(
    screen: pygame.Surface, textures: Textures, world: LevelState
) -> None:
    # This pixel looks up at tile (3, 1). Mutate the door list to catch a stale mask.
    for doors, color in (
        ([], (75, 90, 75)),
        ([(3, 1)], (55, 66, 77)),
        ([(4, 1)], (75, 90, 75)),
        ([(3, 1)], (55, 66, 77)),
        ([], (75, 90, 75)),
    ):
        world.door_positions[:] = doors
        draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, textures)
        assert screen.get_at((512, 200))[:3] == color, doors


def test_replacing_textures_refreshes_cached_samples(
    screen: pygame.Surface, textures: Textures, world: LevelState
) -> None:
    dark_textures: Textures = Textures(
        samples={key: np.zeros_like(value) for key, value in textures.samples.items()}
    )
    draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, textures)
    draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, dark_textures)
    assert screen.get_at((512, 200))[:3] == (0, 0, 0)
    assert screen.get_at((411, 703))[:3] == (0, 0, 0)
    draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, textures)
    assert screen.get_at((512, 200))[:3] == (75, 90, 75)
    assert screen.get_at((411, 703))[:3] == (141, 71, 99)


def test_reused_buffers_render_to_a_new_surface(textures: Textures, world: LevelState) -> None:
    # Reuse the same world's cached buffers across surfaces with different pixel formats.
    for bits in (24, 32):
        screen = pygame.Surface((WIDTH, HEIGHT), depth=bits)
        screen.fill((1, 2, 3))
        draw_floor_ceiling(world, screen, 1.5, 1.5, 0.0, textures)
        assert screen.get_at((512, 200))[:3] == (75, 90, 75), bits
        assert screen.get_at((411, 703))[:3] == (141, 71, 99), bits
        assert not screen.get_locked()
