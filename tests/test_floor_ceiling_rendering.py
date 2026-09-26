"""Headless rendering checks for texture sampling and cache invalidation."""

from __future__ import annotations

import unittest

import numpy as np
import pygame

from shooter import map as gmap
from shooter.constants import EYE_HEIGHT, HEIGHT, TEX_SIZE, WIDTH
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
            ((1.5, 1.5, 0.0, EYE_HEIGHT),
             ((73, 173, 103), (94, 20, 62), (75, 90, 75), (8, 79, 34),
              (13, 5, 9), (43, 50, 54), (141, 71, 99), (107, 35, 70))),
            ((5.125, 8.375, 1.9, 0.7),
             ((45, 18, 37), (29, 32, 34), (97, 104, 92), (26, 111, 56),
              (24, 17, 19), (142, 76, 99), (142, 28, 77), (172, 77, 112))),
            ((1.5, 1.5, 3.9, 0.9),
             ((48, 92, 64), (48, 83, 60), (37, 47, 43), (13, 153, 66),
              (11, 12, 12), (132, 37, 74), (144, 44, 85), (166, 83, 113))),
            ((3.25, 6.75, 6.2, 0.25),
             ((90, 137, 99), (121, 168, 125), (47, 80, 57), (3, 13, 8),
              (8, 17, 13), (124, 27, 71), (174, 105, 128), (161, 150, 146))),
        )
        # Return to the initial view after changing both angle and eye height.
        for (px, py, pa, eye), colors in (*cases, cases[0]):
            self.screen.fill((1, 2, 3))
            draw_floor_ceiling(self.screen, px, py, pa, self.textures, eye)
            for point, color in zip(points, colors):
                with self.subTest(pose=(px, py, pa, eye), pixel=point):
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
