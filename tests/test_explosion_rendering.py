"""Headless regression checks for explosion allocation and viewport clipping."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pygame

from shooter.constants import EXPLOSION_DURATION, HEIGHT, WIDTH
from shooter.entities import Rocket
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import draw_rockets


class ExplosionRenderingTests(unittest.TestCase):
    background = (17, 29, 41)

    def setUp(self) -> None:
        self.depth = DepthBuffer()

    def make_screen(self) -> pygame.Surface:
        screen = pygame.Surface((WIDTH, HEIGHT))
        screen.fill(self.background)
        return screen

    def draw_explosion(self, screen: pygame.Surface, distance: float = 4.0,
                       horizon_offset: int = 0) -> None:
        rocket = Rocket(distance, 0.0, 0.0)
        rocket.exploded = True
        rocket.explosion_timer = EXPLOSION_DURATION // 4
        draw_rockets(screen, [rocket], 0.0, 0.0, 0.0,
                     self.depth, horizon_offset)

    def test_close_explosions_bound_allocations_and_preserve_fade(self) -> None:
        # At this age the core is one-quarter opaque and covers the viewport.
        expected = pygame.Surface((1, 1))
        expected.fill(self.background)
        core = pygame.Surface((1, 1), pygame.SRCALPHA)
        core.fill((255, 240, 180, 63))
        expected.blit(core, (0, 0))
        surface_type = pygame.Surface

        def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
            # Fail before attempting the old gigabyte-scale allocation.
            self.assertLessEqual(size[0], WIDTH)
            self.assertLessEqual(size[1], HEIGHT)
            return surface_type(size, flags)

        for distance in (0.101, 0.15, 0.4):
            with self.subTest(distance=distance):
                screen = self.make_screen()
                with patch('shooter.render_sprites.pygame.Surface',
                           side_effect=bounded_surface):
                    self.draw_explosion(screen, distance)
                for point in ((0, 0), (WIDTH // 2, HEIGHT // 2),
                              (WIDTH - 1, HEIGHT - 1)):
                    self.assertEqual(screen.get_at(point), expected.get_at((0, 0)))

    def test_offscreen_centers_preserve_visible_circle_shape(self) -> None:
        reference = self.make_screen()
        self.draw_explosion(reference)

        for offset in (-HEIGHT // 2 - 32, HEIGHT // 2 + 32):
            with self.subTest(horizon_offset=offset):
                expected = self.make_screen()
                expected.blit(reference, (0, offset))
                actual = self.make_screen()
                self.draw_explosion(actual, horizon_offset=offset)
                self.assertEqual(pygame.image.tobytes(actual, 'RGB'),
                                 pygame.image.tobytes(expected, 'RGB'))

    def test_allocation_respects_surface_clip(self) -> None:
        reference = self.make_screen()
        self.draw_explosion(reference)
        clip = pygame.Rect(WIDTH // 2, HEIGHT // 2, 80, 60)
        expected = self.make_screen()
        expected.set_clip(clip)
        expected.blit(reference, (0, 0))
        actual = self.make_screen()
        actual.set_clip(clip)

        with patch('shooter.render_sprites.pygame.Surface',
                   wraps=pygame.Surface) as allocate:
            self.draw_explosion(actual)

        self.assertEqual(allocate.call_args.args[0], clip.size)
        self.assertEqual(pygame.image.tobytes(actual, 'RGB'),
                         pygame.image.tobytes(expected, 'RGB'))

    def test_fully_offscreen_explosion_allocates_nothing(self) -> None:
        screen = self.make_screen()
        before = pygame.image.tobytes(screen, 'RGB')
        with patch('shooter.render_sprites.pygame.Surface') as allocate:
            self.draw_explosion(screen, horizon_offset=HEIGHT * 2)
        allocate.assert_not_called()
        self.assertEqual(pygame.image.tobytes(screen, 'RGB'), before)


if __name__ == '__main__':
    unittest.main()
