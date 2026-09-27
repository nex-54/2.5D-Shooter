"""Viewmodel animation must remain deterministic and independent of combat state."""

from __future__ import annotations

import math
import random
import unittest

import pygame

from shooter.constants import EMPTY_CLICK_DELAY, HEIGHT, WEAPONS, WIDTH, Weapon
from shooter.render_weapon import draw_weapon
from shooter.weapon_models import weapon_frame


class WeaponRenderingTests(unittest.TestCase):
    def render(
        self,
        weapon: Weapon,
        *,
        shooting: bool = False,
        timer: int = 0,
        moving: bool = False,
        time: float = 0.0,
        spin: float = 0.0,
        clip: pygame.Rect | None = None,
    ) -> pygame.Surface:
        screen = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        if clip is not None:
            screen.set_clip(clip)
        draw_weapon(screen, shooting, timer, moving, time, weapon, spin)
        return screen

    def pixels(self, surface: pygame.Surface) -> bytes:
        return pygame.image.tobytes(surface, "RGBA")

    def test_empty_click_and_unequipped_cooldowns_do_not_animate(self) -> None:
        for weapon in Weapon:
            with self.subTest(weapon=weapon):
                idle = self.pixels(self.render(weapon))
                for timer in (EMPTY_CLICK_DELAY, WEAPONS[weapon].fire_interval_ms):
                    self.assertEqual(self.pixels(self.render(weapon, timer=timer)), idle)

    def test_firing_changes_each_weapon_and_returns_to_rest(self) -> None:
        for weapon in Weapon:
            with self.subTest(weapon=weapon):
                idle = self.pixels(self.render(weapon))
                fired = self.render(weapon, shooting=True, timer=WEAPONS[weapon].fire_interval_ms)
                self.assertNotEqual(self.pixels(fired), idle)
                for expired in (0, -16):
                    self.assertEqual(
                        self.pixels(self.render(weapon, shooting=True, timer=expired)), idle
                    )

    def test_walk_sway_and_coasting_barrels_work_without_firing(self) -> None:
        for weapon in Weapon:
            with self.subTest(weapon=weapon):
                self.assertNotEqual(
                    self.pixels(self.render(weapon, time=0.2)),
                    self.pixels(self.render(weapon, time=0.2, moving=True)),
                )
        self.assertNotEqual(
            self.pixels(self.render(Weapon.GATLING, spin=0)),
            self.pixels(self.render(Weapon.GATLING, spin=math.pi / 12)),
        )

    def test_slide_and_pump_move_while_the_weapon_body_stays_fixed(self) -> None:
        for weapon, pose in ((Weapon.PISTOL, 8), (Weapon.SHOTGUN, 12)):
            with self.subTest(weapon=weapon):
                idle = weapon_frame(weapon, 0)
                cycled = weapon_frame(weapon, pose)
                self.assertNotEqual(self.pixels(idle), self.pixels(cycled))
                # The grip / stock must not move along with the slide or forend.
                fixed_body = pygame.Rect(210, 270, 60, 40)
                self.assertEqual(
                    self.pixels(idle.subsurface(fixed_body)),
                    self.pixels(cycled.subsurface(fixed_body)),
                )

    def test_rendering_does_not_consume_randomness_or_mutate_cached_art(self) -> None:
        rng_state = random.getstate()
        for weapon in Weapon:
            with self.subTest(weapon=weapon):
                model = weapon_frame(weapon, 0)
                before = self.pixels(model)
                timer = WEAPONS[weapon].fire_interval_ms
                first = self.render(weapon, shooting=True, timer=timer)
                second = self.render(weapon, shooting=True, timer=timer)
                self.assertEqual(self.pixels(first), self.pixels(second))
                self.assertEqual(self.pixels(model), before)
                self.assertEqual(model.get_alpha(), 255)
                self.assertFalse(model.get_locked())
        self.assertEqual(random.getstate(), rng_state)

    def test_models_and_flashes_preserve_the_aiming_area(self) -> None:
        aiming_area = pygame.Rect(WIDTH // 2 - 50, HEIGHT // 2 - 50, 100, 100)
        for weapon in Weapon:
            interval = WEAPONS[weapon].fire_interval_ms
            for fraction in (0.0, 0.1, 0.4, 0.75, 1.0):
                with self.subTest(weapon=weapon, fraction=fraction):
                    screen = self.render(
                        weapon,
                        shooting=True,
                        timer=round(interval * fraction),
                        moving=True,
                        time=0.2,
                    )
                    self.assertGreater(pygame.mask.from_surface(screen).count(), 1000)
                    self.assertEqual(
                        pygame.mask.from_surface(screen.subsurface(aiming_area)).count(), 0
                    )

    def test_surface_clipping_applies_to_models_and_firing_effects(self) -> None:
        clip = pygame.Rect(600, 530, 100, 120)
        for weapon in Weapon:
            with self.subTest(weapon=weapon):
                timer = WEAPONS[weapon].fire_interval_ms
                reference = self.render(weapon, shooting=True, timer=timer)
                expected = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                expected.set_clip(clip)
                expected.blit(reference, (0, 0))
                actual = self.render(weapon, shooting=True, timer=timer, clip=clip)
                self.assertEqual(self.pixels(actual), self.pixels(expected))


if __name__ == "__main__":
    unittest.main()
