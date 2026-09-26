"""Render small scenes to verify visible openings and opaque wall coverage."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pygame
import pygame.freetype

from shooter import map as gmap
from shooter.constants import EXPLOSION_DURATION, EYE_HEIGHT, HEIGHT, WIDTH, Weapon
from shooter.entities import Boss, Enemy, HealthPack, Rocket, Scout, Spider, WeaponPickup
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_sprites import (
    Billboard,
    Camera,
    draw_billboard,
    draw_enemy,
    draw_health_pack,
    draw_rocket,
    draw_weapon_pickup,
)
from shooter.render_world import draw_3d
from shooter.types import DoorAnim, DoorAnimMap
from tests.support import open_world


class SpriteOcclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = open_world()
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        self.depth = DepthBuffer()
        self.enemy = Enemy(6.5, 5.5)
        self.enemy.anim_time = 0.0
        self.camera = Camera(2.5, 5.5, 0.0)
        self.doors: DoorAnimMap = {}

    def draw_world(self, eye_height: float = EYE_HEIGHT) -> None:
        self.screen.fill((9, 11, 13))
        walls = cast_rays(self.world, 2.5, 5.5, 0.0, self.doors)
        draw_3d(self.screen, walls, self.depth, None, None, eye_height, self.doors)

    def draw_clipped_enemy(self, eye_height: float = EYE_HEIGHT) -> None:
        draw_enemy(self.screen, self.enemy, Camera(2.5, 5.5, 0.0, eye_height), self.depth)

    def test_barrier_hides_feet_until_a_jump_sees_over_it(self) -> None:
        self.world.maze[5][4] = gmap.BARRIER_TILE
        self.enemy.x = 5.5
        self.draw_world()
        before = pygame.surfarray.array3d(self.screen)
        unclipped = self.screen.copy()
        draw_enemy(unclipped, self.enemy, self.camera, DepthBuffer())
        self.draw_clipped_enemy()
        after = pygame.surfarray.array3d(self.screen)
        # Standing, the barrier covers rows 469-639, over the enemy's feet.
        self.assertTrue(
            np.any(pygame.surfarray.array3d(unclipped)[:, 469:640] != before[:, 469:640])
        )
        self.assertTrue(np.any(after[:, :469] != before[:, :469]))
        np.testing.assert_array_equal(after[:, 469:640], before[:, 469:640])

        # At the top of a jump the eye clears the barrier, so the whole enemy shows.
        eye = EYE_HEIGHT + 0.4
        self.draw_world(eye)
        expected = self.screen.copy()
        draw_enemy(expected, self.enemy, Camera(2.5, 5.5, 0.0, eye), DepthBuffer())
        self.draw_clipped_enemy(eye)
        self.assertEqual(
            pygame.image.tobytes(self.screen, "RGB"), pygame.image.tobytes(expected, "RGB")
        )

    def test_full_wall_hides_every_enemy_type(self) -> None:
        self.world.maze[5][4] = 1
        for enemy_type in (Enemy, Boss, Scout, Spider):
            with self.subTest(enemy_type=enemy_type.__name__):
                self.enemy = enemy_type(6.5, 5.5)
                self.draw_world()
                before = pygame.image.tobytes(self.screen, "RGB")
                self.draw_clipped_enemy()
                self.assertEqual(pygame.image.tobytes(self.screen, "RGB"), before)

    def test_enemy_in_front_of_barrier_is_not_clipped(self) -> None:
        self.world.maze[5][4] = gmap.BARRIER_TILE
        self.enemy.x = 3.5
        self.draw_world()
        expected = self.screen.copy()
        draw_enemy(expected, self.enemy, self.camera, DepthBuffer())
        self.draw_clipped_enemy()
        self.assertEqual(
            pygame.image.tobytes(self.screen, "RGB"), pygame.image.tobytes(expected, "RGB")
        )

    def test_opening_door_reveals_only_the_gap(self) -> None:
        self.world.maze[5][4] = gmap.DOOR_TILE
        self.draw_world()
        before = pygame.image.tobytes(self.screen, "RGB")
        self.draw_clipped_enemy()
        self.assertEqual(pygame.image.tobytes(self.screen, "RGB"), before)

        for phase in ("opening", "closing"):
            with self.subTest(phase=phase):
                self.doors[(4, 5)] = DoorAnim(phase=phase, progress=0.5, timer=0)
                self.draw_world()
                before = pygame.surfarray.array3d(self.screen)
                self.draw_clipped_enemy()
                after = pygame.surfarray.array3d(self.screen)
                np.testing.assert_array_equal(after[:, :384], before[:, :384])
                self.assertTrue(np.any(after[:, 384:] != before[:, 384:]))

        self.doors[(4, 5)] = DoorAnim(phase="open", progress=1.0, timer=5000)
        self.draw_world()
        expected = self.screen.copy()
        draw_enemy(expected, self.enemy, self.camera, DepthBuffer())
        self.draw_clipped_enemy()
        self.assertEqual(
            pygame.image.tobytes(self.screen, "RGB"), pygame.image.tobytes(expected, "RGB")
        )

    def test_background_wall_or_closed_door_still_hides_enemies(self) -> None:
        for foreground, background in ((gmap.BARRIER_TILE, 1), (gmap.DOOR_TILE, gmap.DOOR_TILE)):
            with self.subTest(foreground=foreground, background=background):
                self.world.maze[5][4] = foreground
                self.world.maze[5][5] = background
                self.doors[(4, 5)] = DoorAnim(phase="opening", progress=0.5, timer=0)
                self.draw_world()
                before = pygame.image.tobytes(self.screen, "RGB")
                self.draw_clipped_enemy()
                self.assertEqual(pygame.image.tobytes(self.screen, "RGB"), before)

    def test_stacked_barriers_preserve_the_farther_barriers_coverage(self) -> None:
        self.world.maze[5][4] = gmap.BARRIER_TILE
        self.world.maze[5][5] = gmap.BARRIER_TILE
        self.draw_world()
        before = pygame.surfarray.array3d(self.screen)
        self.draw_clipped_enemy()
        after = pygame.surfarray.array3d(self.screen)
        # The farther barrier rises to row 435, above the nearer one's row 469.
        self.assertTrue(np.any(after[:, :435] != before[:, :435]))
        np.testing.assert_array_equal(after[:, 435:640], before[:, 435:640])

    def test_depth_is_cleared_between_frames(self) -> None:
        self.world.maze[5][4] = 1
        self.draw_world()
        self.world.maze[5][4] = 0
        self.draw_world()
        before = pygame.image.tobytes(self.screen, "RGB")
        self.draw_clipped_enemy()
        self.assertNotEqual(pygame.image.tobytes(self.screen, "RGB"), before)

    def test_pickups_labels_and_projectiles_use_the_same_height_clipping(self) -> None:
        pygame.freetype.init()
        font = pygame.freetype.Font(None, 20)
        health = HealthPack(6.5, 5.5)
        weapon = WeaponPickup(6.5, 5.5, Weapon.SHOTGUN)
        rocket = Rocket(6.5, 5.5, 0.0)
        explosion = Rocket(6.5, 5.5, 0.0)
        explosion.exploded = True
        explosion.explosion_timer = EXPLOSION_DURATION // 4
        label = Billboard("TEST", 6.5, 5.5, (20, 20, 80))
        health.anim_time = weapon.anim_time = 0.0
        drawers = {
            "health": lambda: draw_health_pack(self.screen, health, self.camera, self.depth),
            "weapon": lambda: draw_weapon_pickup(self.screen, weapon, self.camera, self.depth),
            "rocket": lambda: draw_rocket(self.screen, rocket, self.camera, self.depth),
            "explosion": lambda: draw_rocket(self.screen, explosion, self.camera, self.depth),
            "label": lambda: draw_billboard(self.screen, font, label, self.camera, self.depth),
        }
        for tile in (gmap.BARRIER_TILE, 1):
            self.world.maze[5][4] = tile
            for name, draw in drawers.items():
                with self.subTest(tile=tile, sprite=name):
                    self.draw_world()
                    before = pygame.surfarray.array3d(self.screen)
                    draw()
                    after = pygame.surfarray.array3d(self.screen)
                    if tile == 1:
                        np.testing.assert_array_equal(after, before)
                    else:
                        self.assertTrue(np.any(after != before))
                        np.testing.assert_array_equal(after[:, 469:640], before[:, 469:640])

    def test_partially_hidden_close_explosion_keeps_allocations_bounded(self) -> None:
        self.screen.fill((9, 11, 13))
        self.depth.block_column(0, WIDTH, 0.01, HEIGHT // 2)
        rocket = Rocket(0.15, 0.0, 0.0)
        rocket.exploded = True
        rocket.explosion_timer = EXPLOSION_DURATION // 4
        surface_type = pygame.Surface

        def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
            self.assertLessEqual(size[0], WIDTH)
            self.assertLessEqual(size[1], HEIGHT)
            return surface_type(size, flags)

        with patch("shooter.render_sprites.pygame.Surface", side_effect=bounded_surface):
            draw_rocket(self.screen, rocket, Camera(0.0, 0.0, 0.0), self.depth)
        self.assertNotEqual(self.screen.get_at((WIDTH // 2, 100))[:3], (9, 11, 13))
        self.assertEqual(self.screen.get_at((WIDTH // 2, HEIGHT - 100))[:3], (9, 11, 13))


if __name__ == "__main__":
    unittest.main()
