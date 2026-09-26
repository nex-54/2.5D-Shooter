"""Verify that jumping raises the camera instead of tilting the view."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pygame

from shooter import map as gmap
from shooter.constants import EYE_HEIGHT, HEIGHT, PLAYER_MARGIN, TEX_SIZE, WIDTH
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_world import draw_3d, draw_floor_ceiling
from shooter.types import Textures
from tests.support import open_world

JUMP_PEAK = EYE_HEIGHT + 0.4
HORIZON = HEIGHT // 2


class CameraHeightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = open_world()
        self.screen = pygame.Surface((WIDTH, HEIGHT))

    def test_horizon_stays_level_at_the_top_of_a_jump(self) -> None:
        # A red floor and blue ceiling show which plane each row samples.
        red = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
        red[..., 0] = 200
        blue = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
        blue[..., 2] = 200
        textures: Textures = Textures(samples={"floor": red, "ceil": blue, "door": blue})
        for eye in (EYE_HEIGHT, JUMP_PEAK):
            with self.subTest(eye=eye):
                draw_floor_ceiling(self.world, self.screen, 2.5, 5.5, 0.0, textures, eye)
                pixels = pygame.surfarray.array3d(self.screen)
                self.assertTrue((pixels[:, :HORIZON, 0] == 0).all())
                self.assertTrue((pixels[:, :HORIZON, 2] > 0).all())
                self.assertTrue((pixels[:, HORIZON + 1 :, 0] > 0).all())
                self.assertTrue((pixels[:, HORIZON + 1 :, 2] == 0).all())

    def wall_rows(self, eye: float) -> tuple[int, int]:
        """First and last+1 rows of the flat-shaded wall in the center column."""
        draw_floor_ceiling(self.world, self.screen, 2.5, 5.5, 0.0, None, eye)
        before = pygame.surfarray.array3d(self.screen)[WIDTH // 2]
        draw_3d(self.screen, cast_rays(self.world, 2.5, 5.5, 0.0), DepthBuffer(), None, None, eye)
        after = pygame.surfarray.array3d(self.screen)[WIDTH // 2]
        rows = np.flatnonzero((after != before).any(axis=1))
        return int(rows[0]), int(rows[-1]) + 1

    def test_rising_eye_sinks_near_walls_more_than_far_walls(self) -> None:
        # Walls are one unit tall; the eye sees their tops at (1 - eye) above it.
        for wall_x, depth in ((4, 1.5), (8, 5.5)):
            self.world.maze[5][wall_x] = 1
            for eye in (EYE_HEIGHT, JUMP_PEAK):
                with self.subTest(depth=depth, eye=eye):
                    scale = HEIGHT / depth
                    top, bottom = self.wall_rows(eye)
                    self.assertAlmostEqual(top, HORIZON - (1 - eye) * scale, delta=1)
                    self.assertAlmostEqual(bottom, min(HEIGHT, HORIZON + eye * scale), delta=1)
            self.world.maze[5][wall_x] = 0

    def test_barriers_stand_on_the_floor(self) -> None:
        self.world.maze[5][4] = gmap.BARRIER_TILE
        scale = HEIGHT / 1.5
        for eye in (EYE_HEIGHT, JUMP_PEAK):
            with self.subTest(eye=eye):
                depth = DepthBuffer()
                draw_3d(self.screen, cast_rays(self.world, 2.5, 5.5, 0.0), depth, None, None, eye)
                rows = np.flatnonzero(np.isclose(depth.pixels[WIDTH // 2], 1.5))
                floor_row = HORIZON + eye * scale
                self.assertAlmostEqual(rows[-1] + 1, min(HEIGHT, floor_row), delta=1)
                self.assertAlmostEqual(rows[0], floor_row - gmap.BARRIER_HEIGHT * scale, delta=1)

    def test_walls_at_arms_length_fill_the_view_with_bounded_scaling(self) -> None:
        self.world.maze[5][3] = 1
        column = pygame.Surface((1, TEX_SIZE))
        column.fill((200, 0, 0))
        textures: Textures = Textures(columns={"wall": [column] * TEX_SIZE})
        walls = cast_rays(self.world, 3 - PLAYER_MARGIN, 5.5, 0.0)
        self.screen.fill((0, 0, 255))
        sizes: list[tuple[int, int]] = []
        scale = pygame.transform.scale

        def recording_scale(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
            sizes.append(size)
            return scale(surface, size)

        with patch("shooter.render_world.pygame.transform.scale", side_effect=recording_scale):
            draw_3d(self.screen, walls, DepthBuffer(), None, textures, JUMP_PEAK)
        pixels = pygame.surfarray.array3d(self.screen)
        self.assertTrue((pixels[..., 0] > 0).all())
        self.assertTrue((pixels[..., 1:] == 0).all())
        self.assertLessEqual(max(height for _, height in sizes), 2 * HEIGHT)


if __name__ == "__main__":
    unittest.main()
