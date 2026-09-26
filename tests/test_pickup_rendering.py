"""Keep pickup halo allocations bounded without changing visible pixels."""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import pygame

from shooter.constants import EYE_HEIGHT, HEIGHT, WIDTH
from shooter.entities import WeaponPickup
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import draw_weapon_pickups


class PickupRenderingTests(unittest.TestCase):
    background = (17, 29, 41)

    def setUp(self) -> None:
        self.depth = DepthBuffer()
        self.pickup = WeaponPickup(4.0, 0.0, 0)
        self.pickup.anim_time = math.pi / 4

    def make_screen(self) -> pygame.Surface:
        screen = pygame.Surface((WIDTH, HEIGHT))
        screen.fill(self.background)
        return screen

    def draw_pickup(self, screen: pygame.Surface, shift: int = 0) -> None:
        # Translate vertically without changing the pickup's projected size.
        eye_height = EYE_HEIGHT + shift * self.pickup.x / HEIGHT
        draw_weapon_pickups(screen, [self.pickup], 0.0, 0.0, 0.0, self.depth, eye_height)

    def test_close_pickups_keep_allocations_within_viewport(self) -> None:
        surface_type = pygame.Surface

        def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
            # Reject oversized buffers before allocating them.
            self.assertLessEqual(size[0], WIDTH)
            self.assertLessEqual(size[1], HEIGHT)
            return surface_type(size, flags)

        for weapon_type in range(4):
            for distance in (0.301, 0.31, 0.6):
                with self.subTest(weapon_type=weapon_type, distance=distance):
                    self.pickup.weapon_type = weapon_type
                    self.pickup.x = distance
                    screen = self.make_screen()
                    with patch(
                        "shooter.render_sprites.pygame.Surface", side_effect=bounded_surface
                    ) as allocate:
                        self.draw_pickup(screen)
                    allocate.assert_called_once()
                    self.assertNotEqual(screen.get_at((0, 0))[:3], self.background)

    def test_offscreen_centers_preserve_halo_shape_and_alpha(self) -> None:
        for phase in (0.0, math.pi / 4):
            self.pickup.anim_time = phase
            reference = self.make_screen()
            self.draw_pickup(reference)
            for shift in (-HEIGHT // 2 - 48, HEIGHT // 2 + 48):
                with self.subTest(phase=phase, shift=shift):
                    expected = self.make_screen()
                    expected.blit(reference, (0, shift))
                    actual = self.make_screen()
                    self.draw_pickup(actual, shift)
                    self.assertEqual(
                        pygame.image.tobytes(actual, "RGB"),
                        pygame.image.tobytes(expected, "RGB"),
                    )

    def test_surface_clip_and_wall_occlusion_preserve_visible_pixels(self) -> None:
        clip = pygame.Rect(80, 120, WIDTH - 160, HEIGHT - 240)
        for distance in (0.31, 4.0):
            self.pickup.x = distance
            self.depth.clear()
            reference = self.make_screen()
            self.draw_pickup(reference)
            for occluded in (False, True):
                with self.subTest(distance=distance, occluded=occluded):
                    expected = self.make_screen()
                    expected.set_clip(clip)
                    expected.blit(reference, (0, 0))
                    if occluded:
                        self.depth.block_column(0, WIDTH, 0.01, HEIGHT // 2)
                        expected.fill(self.background, (0, HEIGHT // 2, WIDTH, HEIGHT // 2))
                    actual = self.make_screen()
                    actual.set_clip(clip)
                    with patch(
                        "shooter.render_sprites.pygame.Surface", wraps=pygame.Surface
                    ) as allocate:
                        self.draw_pickup(actual)
                    self.assertEqual(allocate.call_count, 2 if occluded else 1)
                    for call in allocate.call_args_list:
                        width, height = call.args[0]
                        self.assertLessEqual(width, clip.width)
                        self.assertLessEqual(height, clip.height)
                    self.assertEqual(
                        pygame.image.tobytes(actual, "RGB"),
                        pygame.image.tobytes(expected, "RGB"),
                    )

    def test_invisible_pickup_allocates_nothing(self) -> None:
        for hidden_by_wall in (False, True):
            with self.subTest(hidden_by_wall=hidden_by_wall):
                screen = self.make_screen()
                before = pygame.image.tobytes(screen, "RGB")
                if hidden_by_wall:
                    self.depth.block_column(0, WIDTH, 0.01)
                with patch("shooter.render_sprites.pygame.Surface") as allocate:
                    self.draw_pickup(screen, shift=0 if hidden_by_wall else HEIGHT * 2)
                allocate.assert_not_called()
                self.assertEqual(pygame.image.tobytes(screen, "RGB"), before)


if __name__ == "__main__":
    unittest.main()
