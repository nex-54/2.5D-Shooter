"""Verify hitscan hit zones match enemy bodies and gatling barrels spin down forward."""

from __future__ import annotations

import math
import unittest
from unittest.mock import MagicMock

from shooter.entities import Boss, Enemy, Scout, Spider, apply_hit, hitscan
from shooter.game import GameState, update_combat
from tests.support import SoundMocks, open_world


class HitscanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = open_world()

    def test_hit_zone_matches_the_body_width_at_any_distance(self) -> None:
        for distance in (0.8, 3.0, 8.0, 15.0):
            enemy = Enemy(2.5 + distance, 5.5)
            for across, hits in ((enemy.hit_radius * 0.95, True), (enemy.hit_radius * 1.05, False)):
                with self.subTest(distance=distance, across=across):
                    aim = math.asin(across / distance)
                    self.assertIs(hitscan(self.world, [enemy], 2.5, 5.5, aim) is enemy, hits)

    def test_far_misses_miss_and_point_blank_body_shots_hit(self) -> None:
        # A fixed 0.15 rad cone hit the first and missed the second.
        far = Enemy(2.5 + 8 * math.cos(0.14), 5.5 + 8 * math.sin(0.14))
        self.assertIsNone(hitscan(self.world, [far], 2.5, 5.5, 0.0))
        near = Enemy(2.5 + 0.8 * math.cos(0.17), 5.5 + 0.8 * math.sin(0.17))
        self.assertIs(hitscan(self.world, [near], 2.5, 5.5, 0.0), near)

    def test_nearer_enemy_beside_the_line_does_not_take_the_shot(self) -> None:
        beside = Enemy(5.5, 5.9)
        target = Enemy(8.5, 5.5)
        self.assertIs(hitscan(self.world, [beside, target], 2.5, 5.5, 0.0), target)
        self.assertIs(hitscan(self.world, [beside, target], 2.5, 5.5, math.atan2(0.4, 3.0)), beside)

    def test_bigger_bodies_are_easier_to_hit(self) -> None:
        aim = math.asin(0.3 / 5.0)
        self.assertIsNotNone(hitscan(self.world, [Boss(7.5, 5.5)], 2.5, 5.5, aim))
        self.assertIsNone(hitscan(self.world, [Scout(7.5, 5.5)], 2.5, 5.5, aim))

    def test_shots_hit_the_part_of_an_enemy_showing_past_a_corner(self) -> None:
        self.world.maze[4][3] = 1
        px, py = 1.5, 5.5
        center = math.radians(-43)
        enemy = Enemy(px + 3.5 * math.cos(center), py + 3.5 * math.sin(center))
        self.assertFalse(self.world.has_line_of_sight(px, py, enemy.x, enemy.y))
        self.assertIsNone(hitscan(self.world, [enemy], px, py, center))
        # Aiming 3 degrees above the corner still passes through the body.
        self.assertIs(hitscan(self.world, [enemy], px, py, math.radians(-46)), enemy)

    def test_shots_do_not_hit_enemies_behind_the_shooter(self) -> None:
        self.assertIsNone(hitscan(self.world, [Enemy(1.5, 5.5)], 2.5, 5.5, 0.0))


class GatlingSpinTests(unittest.TestCase):
    def test_released_barrels_coast_forward_to_a_stop(self) -> None:
        state = GameState()
        state.weapon = 2
        state.mouse_held = True
        sfx = MagicMock()
        for _ in range(20):
            update_combat(state, 16, sfx)
        state.mouse_held = False

        steps: list[float] = []
        for _ in range(40):
            before = state.gatling_spin
            update_combat(state, 16, sfx)
            steps.append((state.gatling_spin - before) % (2 * math.pi))
        # Each frame turns the barrels forward by less than half a turn, slowing to rest.
        self.assertGreater(steps[0], 0.0)
        self.assertTrue(all(step < math.pi for step in steps))
        self.assertTrue(all(a >= b for a, b in zip(steps, steps[1:], strict=False)))
        self.assertEqual(steps[-1], 0.0)


class DamageTests(unittest.TestCase):
    def test_multi_damage_plays_one_sound_and_reports_death_only_once(self) -> None:
        for enemy, sound in (
            (Enemy(5.5, 5.5), "enemy_die"),
            (Spider(5.5, 5.5), "spider_die"),
            (Boss(5.5, 5.5), "boss_die"),
        ):
            with self.subTest(enemy=type(enemy).__name__):
                sounds = SoundMocks()
                sfx = sounds.sfx
                self.assertTrue(apply_hit(enemy, sfx, enemy.hp + 10))
                self.assertEqual(enemy.hp, 0)
                self.assertFalse(enemy.alive)
                sounds[sound].play.assert_called_once()
                self.assertFalse(apply_hit(enemy, sfx, 10))
                sounds[sound].play.assert_called_once()
                sounds["enemy_hurt"].play.assert_not_called()

    def test_nonlethal_damage_and_zero_damage(self) -> None:
        enemy = Enemy(5.5, 5.5)
        sounds = SoundMocks()
        sfx = sounds.sfx
        self.assertFalse(apply_hit(enemy, sfx, 2))
        self.assertEqual(enemy.hp, 1)
        self.assertTrue(enemy.alive)
        sounds["enemy_hurt"].play.assert_called_once()
        self.assertFalse(apply_hit(enemy, sfx, 0))
        self.assertEqual(enemy.hp, 1)
        sounds["enemy_hurt"].play.assert_called_once()


if __name__ == "__main__":
    unittest.main()
