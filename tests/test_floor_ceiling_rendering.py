"""Headless rendering checks for texture sampling and cache invalidation."""

from __future__ import annotations

import unittest

import numpy as np
import pygame

from shooter import map as gmap
from shooter.constants import HEIGHT, TEX_SIZE, WIDTH
from shooter.render_world import draw_floor_ceiling
from shooter.types import Textures


class FloorCeilingRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        doors = gmap.DOOR_POSITIONS.copy()
        self.addCleanup(lambda: gmap.DOOR_POSITIONS.__setitem__(slice(None), doors))
        gmap.DOOR_POSITIONS.clear()
        x, y = np.indices((TEX_SIZE, TEX_SIZE))
        self.textures: Textures = {
            'floor_np': np.stack((20 + x * 3, 30 + y * 2, 40 + x + y),
                                 axis=-1).astype(np.float32),
            'ceil_np': np.stack((15 + x * 2, 10 + y * 3, 20 + x + y),
                                axis=-1).astype(np.float32),
            'door_np': np.full((TEX_SIZE, TEX_SIZE, 3), (100, 120, 140), np.float32),
        }
        self.screen = pygame.Surface((WIDTH, HEIGHT))

    def test_sampled_pixels_match_recorded_baseline(self) -> None:
        # Baseline pixels cross-checked against a per-pixel scalar reference,
        # with coordinate-coded textures so shifts, wrapping, shading and x/y
        # swaps are observable.
        points = ((0, 0), (173, 61), (512, 200), (1023, 333),
                  (91, 385), (780, 527), (411, 703), (1023, 767))
        cases = (
            ((1.5, 1.5, 0.0, 0),
             ((73, 173, 103), (94, 20, 62), (75, 90, 75), (8, 79, 34),
              (13, 5, 9), (43, 50, 54), (141, 71, 99), (107, 35, 70))),
            ((5.125, 8.375, 1.9, 137),
             ((48, 46, 48), (29, 54, 41), (99, 97, 90), (50, 160, 86),
              (56, 77, 61), (12, 5, 8), (121, 73, 92), (148, 89, 110))),
            ((1.5, 1.5, 3.9, 514),
             ((16, 79, 43), (20, 64, 40), (25, 29, 31), (46, 143, 80),
              (101, 52, 76), (125, 109, 107), (116, 55, 84), (65, 48, 56))),
            ((3.25, 6.75, 6.2, -400),
             ((1, 2, 3), (20, 63, 50), (20, 92, 69), (87, 60, 76),
              (46, 54, 59), (195, 134, 150), (160, 107, 125), (158, 150, 145))),
        )
        # Return to the initial view after changing both angle and horizon.
        for (px, py, pa, offset), colors in (*cases, cases[0]):
            self.screen.fill((1, 2, 3))
            draw_floor_ceiling(self.screen, px, py, pa, self.textures, offset)
            for point, color in zip(points, colors):
                with self.subTest(pose=(px, py, pa, offset), pixel=point):
                    self.assertEqual(self.screen.get_at(point)[:3], color)
            self.assertFalse(self.screen.get_locked())

    def test_lines_facing_the_camera_stay_straight(self) -> None:
        # Texel column 0 marks every integer x on the floor and ceiling. Facing
        # +x, each mark lies at one perpendicular distance, so every screen
        # column must show it on the same rows; unit-length rays bent them.
        stripes = np.zeros((TEX_SIZE, TEX_SIZE, 3), np.float32)
        stripes[0] = 255
        textures: Textures = {'floor_np': stripes, 'ceil_np': stripes,
                              'door_np': stripes}
        self.screen.fill((0, 0, 0))
        draw_floor_ceiling(self.screen, 1.5, 1.5, 0.0, textures)
        marked = pygame.surfarray.array3d(self.screen).any(axis=2)
        self.assertTrue(marked[WIDTH // 2].any())
        for x in (0, WIDTH // 4, WIDTH - 1):
            with self.subTest(column=x):
                np.testing.assert_array_equal(marked[x], marked[WIDTH // 2])

    def test_door_ceiling_updates_after_level_layout_changes(self) -> None:
        # This pixel looks up at tile (3, 1). Move/remove doors in the same list,
        # as generate_level does, to catch a stale mask from the previous level.
        for doors, color in (([], (75, 90, 75)),
                             ([(3, 1)], (55, 66, 77)),
                             ([(4, 1)], (75, 90, 75)),
                             ([(3, 1)], (55, 66, 77)),
                             ([], (75, 90, 75))):
            with self.subTest(doors=doors):
                gmap.DOOR_POSITIONS[:] = doors
                draw_floor_ceiling(self.screen, 1.5, 1.5, 0.0, self.textures)
                self.assertEqual(self.screen.get_at((512, 200))[:3], color)

    def test_replacing_textures_refreshes_cached_samples(self) -> None:
        dark_textures: Textures = {key: np.zeros_like(value)
                                   for key, value in self.textures.items()}
        draw_floor_ceiling(self.screen, 1.5, 1.5, 0.0, self.textures)
        draw_floor_ceiling(self.screen, 1.5, 1.5, 0.0, dark_textures)
        self.assertEqual(self.screen.get_at((512, 200))[:3], (0, 0, 0))
        self.assertEqual(self.screen.get_at((411, 703))[:3], (0, 0, 0))
        draw_floor_ceiling(self.screen, 1.5, 1.5, 0.0, self.textures)
        self.assertEqual(self.screen.get_at((512, 200))[:3], (75, 90, 75))
        self.assertEqual(self.screen.get_at((411, 703))[:3], (141, 71, 99))

    def test_reused_buffers_render_to_a_new_surface(self) -> None:
        for bits in (24, 32):
            with self.subTest(bits=bits):
                screen = pygame.Surface((WIDTH, HEIGHT), depth=bits)
                screen.fill((1, 2, 3))
                draw_floor_ceiling(screen, 1.5, 1.5, 0.0, self.textures)
                self.assertEqual(screen.get_at((512, 200))[:3], (75, 90, 75))
                self.assertEqual(screen.get_at((411, 703))[:3], (141, 71, 99))
                self.assertFalse(screen.get_locked())


if __name__ == '__main__':
    unittest.main()
