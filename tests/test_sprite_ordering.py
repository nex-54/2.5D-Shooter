"""Verify that world sprites overlap according to depth across entity types."""

from __future__ import annotations

import math
import unittest
from collections.abc import Sequence

import pygame
import pygame.freetype

from shooter.constants import EXPLOSION_DURATION, EYE_HEIGHT, HEIGHT, WIDTH
from shooter.entities import Boss, Enemy, HealthPack, Rocket, WeaponPickup
from shooter.game import GameState, draw_frame
from shooter.occlusion import DepthBuffer
from shooter.render_sprites import Billboard, draw_enemies, draw_world_sprites
from shooter.textures import generate_textures
from tests.support import open_world

Sprite = Enemy | HealthPack | WeaponPickup | Rocket | Billboard


class SpriteOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.freetype.init()
        self.font = pygame.freetype.Font(None, 20)
        self.depth = DepthBuffer()

    def make_screen(self) -> pygame.Surface:
        screen = pygame.Surface((WIDTH, HEIGHT))
        screen.fill((17, 29, 41))
        return screen

    def draw_sprites(
        self,
        screen: pygame.Surface,
        sprites: Sequence[Sprite],
        angle: float = 0.0,
        eye_height: float = EYE_HEIGHT,
    ) -> None:
        draw_world_sprites(
            screen,
            2.5,
            5.5,
            angle,
            self.depth,
            self.font,
            enemies=[s for s in sprites if isinstance(s, Enemy)],
            health_packs=[s for s in sprites if isinstance(s, HealthPack)],
            weapon_pickups=[s for s in sprites if isinstance(s, WeaponPickup)],
            rockets=[s for s in sprites if isinstance(s, Rocket)],
            billboards=[s for s in sprites if isinstance(s, Billboard)],
            eye_height=eye_height,
        )

    def assert_composition(
        self, farther: Sprite, nearer: Sprite, angle: float = 0.0, eye_height: float = EYE_HEIGHT
    ) -> None:
        # Single-object passes give a reference image with a known physical order.
        expected = self.make_screen()
        self.draw_sprites(expected, [farther], angle, eye_height)
        self.draw_sprites(expected, [nearer], angle, eye_height)
        expected_pixels = pygame.image.tobytes(expected, "RGB")
        reversed_order = self.make_screen()
        self.draw_sprites(reversed_order, [nearer], angle, eye_height)
        self.draw_sprites(reversed_order, [farther], angle, eye_height)
        self.assertNotEqual(
            expected_pixels,
            pygame.image.tobytes(reversed_order, "RGB"),
            "The scene must visibly distinguish the two draw orders",
        )

        for sprites in ([nearer, farther], [farther, nearer]):
            actual = self.make_screen()
            self.draw_sprites(actual, sprites, angle, eye_height)
            self.assertEqual(pygame.image.tobytes(actual, "RGB"), expected_pixels)

    def make_foreground_objects(self, x: float) -> list[Sprite]:
        health = HealthPack(x, 5.5)
        weapon = WeaponPickup(x, 5.5, 1)
        health.anim_time = weapon.anim_time = 0.0
        rocket = Rocket(x, 5.5, 0.0)
        explosion = Rocket(x, 5.5, 0.0)
        explosion.exploded = True
        explosion.explosion_timer = EXPLOSION_DURATION // 4
        label = Billboard("TEST", x, 5.5, (20, 20, 80))
        return [health, weapon, rocket, explosion, label]

    def test_near_enemy_covers_distant_pickups_effects_and_labels(self) -> None:
        enemy = Enemy(4.5, 5.5)
        enemy.anim_time = 0.0
        for farther in self.make_foreground_objects(6.5):
            with self.subTest(
                sprite=type(farther).__name__,
                exploded=isinstance(farther, Rocket) and farther.exploded,
            ):
                self.assert_composition(farther, enemy)

    def test_near_pickups_effects_and_labels_cover_distant_enemy(self) -> None:
        enemy = Enemy(6.5, 5.5)
        enemy.anim_time = 0.0
        for nearer in self.make_foreground_objects(4.5):
            with self.subTest(
                sprite=type(nearer).__name__,
                exploded=isinstance(nearer, Rocket) and nearer.exploded,
            ):
                self.assert_composition(enemy, nearer)

    def test_pickups_sort_within_and_between_types(self) -> None:
        for nearer in self.make_foreground_objects(4.5)[:2]:
            for farther in self.make_foreground_objects(6.5)[:2]:
                with self.subTest(nearer=type(nearer).__name__, farther=type(farther).__name__):
                    self.assert_composition(farther, nearer)

    def test_order_uses_camera_depth_when_euclidean_distances_disagree(self) -> None:
        for angle in (0.0, math.pi / 2):
            with self.subTest(angle=angle):
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                enemy = Enemy(2.5 + 2.0 * cos_a - 0.7 * sin_a, 5.5 + 2.0 * sin_a + 0.7 * cos_a)
                health = HealthPack(
                    2.5 + 2.01 * cos_a - 0.6 * sin_a, 5.5 + 2.01 * sin_a + 0.6 * cos_a
                )
                enemy.anim_time = health.anim_time = 0.0
                # The enemy's camera depth is smaller despite its longer radial distance.
                self.assertGreater(
                    math.hypot(enemy.x - 2.5, enemy.y - 5.5),
                    math.hypot(health.x - 2.5, health.y - 5.5),
                )
                self.assert_composition(health, enemy, angle)

    def test_boss_label_stays_over_its_boss_at_equal_depth(self) -> None:
        boss = Boss(4.5, 5.5)
        boss.anim_time = 0.0
        label = Billboard("BOSS", boss.x, boss.y, (80, 20, 80))
        self.assert_composition(boss, label)

    def test_mixed_sprites_preserve_wall_clipping_at_jump_height(self) -> None:
        self.depth.block_column(0, WIDTH, 1.0, 0, HEIGHT // 2)
        enemy = Enemy(4.5, 5.5)
        enemy.anim_time = 0.0
        for farther in self.make_foreground_objects(6.5):
            with self.subTest(sprite=type(farther).__name__):
                self.assert_composition(farther, enemy, eye_height=EYE_HEIGHT + 0.4)

        screen = self.make_screen()
        covered = pygame.Rect(0, 0, WIDTH, HEIGHT // 2)
        before = pygame.image.tobytes(screen.subsurface(covered), "RGB")
        self.draw_sprites(
            screen, [enemy, *self.make_foreground_objects(6.5)], eye_height=EYE_HEIGHT + 0.4
        )
        self.assertEqual(pygame.image.tobytes(screen.subsurface(covered), "RGB"), before)

    def test_game_frame_keeps_distant_pickup_behind_enemy(self) -> None:
        self.world = open_world()

        state = GameState()
        state.world = self.world
        state.px, state.py = 2.5, 5.5
        enemy = Enemy(4.5, 5.5)
        health = HealthPack(6.5, 5.5)
        enemy.anim_time = health.anim_time = 0.0
        state.enemies = [enemy]
        state.health_packs = [health]

        expected = pygame.Surface((WIDTH, HEIGHT))
        draw_enemies(expected, [enemy], state.px, state.py, state.pa, DepthBuffer())
        actual = pygame.Surface((WIDTH, HEIGHT))
        draw_frame(state, actual, self.font, generate_textures(), self.depth, False)
        # Opaque enemy torso, away from the crosshair and other HUD elements.
        point = (WIDTH // 2 + 16, HEIGHT // 2 + 16)
        self.assertEqual(actual.get_at(point), expected.get_at(point))


if __name__ == "__main__":
    unittest.main()
