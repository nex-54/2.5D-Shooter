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

    def test_sampled_pixels_match_original_renderer(self) -> None:
        # Baseline pixels recorded before optimization, with coordinate-coded
        # textures so shifts, wrapping, shading and x/y swaps are observable.
        points = ((0, 0), (173, 61), (512, 200), (1023, 333),
                  (91, 385), (780, 527), (411, 703), (1023, 767))
        cases = (
            ((1.5, 1.5, 0.0, 0),
             ((56, 9, 39), (85, 25, 59), (75, 90, 75), (8, 27, 17),
              (12, 7, 10), (28, 47, 47), (139, 71, 98), (82, 27, 58))),
            ((5.125, 8.375, 1.9, 137),
             ((46, 26, 40), (29, 46, 38), (99, 97, 90), (76, 126, 88),
              (53, 34, 45), (21, 4, 11), (121, 71, 92), (178, 71, 111))),
            ((1.5, 1.5, 3.9, 514),
             ((24, 82, 48), (24, 67, 43), (25, 29, 31), (50, 163, 88),
              (108, 54, 81), (128, 117, 112), (118, 57, 86), (78, 115, 85))),
            ((3.25, 6.75, 6.2, -400),
             ((1, 2, 3), (110, 74, 85), (20, 92, 69), (59, 51, 62),
              (32, 59, 57), (190, 134, 148), (160, 107, 125), (146, 146, 140))),
        )
        # Return to the initial view after changing both angle and horizon.
        for (px, py, pa, offset), colors in (*cases, cases[0]):
            self.screen.fill((1, 2, 3))
            draw_floor_ceiling(self.screen, px, py, pa, self.textures, offset)
            for point, color in zip(points, colors):
                with self.subTest(pose=(px, py, pa, offset), pixel=point):
                    self.assertEqual(self.screen.get_at(point)[:3], color)
            self.assertFalse(self.screen.get_locked())

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
        self.assertEqual(self.screen.get_at((411, 703))[:3], (139, 71, 98))

    def test_reused_buffers_render_to_a_new_surface(self) -> None:
        for bits in (24, 32):
            with self.subTest(bits=bits):
                screen = pygame.Surface((WIDTH, HEIGHT), depth=bits)
                screen.fill((1, 2, 3))
                draw_floor_ceiling(screen, 1.5, 1.5, 0.0, self.textures)
                self.assertEqual(screen.get_at((512, 200))[:3], (75, 90, 75))
                self.assertEqual(screen.get_at((411, 703))[:3], (139, 71, 98))
                self.assertFalse(screen.get_locked())


if __name__ == '__main__':
    unittest.main()
