"""Verify hitscan hit zones match enemy bodies and gatling barrels spin down forward."""

from __future__ import annotations

import math
import unittest
from unittest.mock import MagicMock

from shooter import map as gmap
from shooter.entities import Boss, Enemy, Scout, hitscan
from shooter.game import GameState, update_combat


class HitscanTests(unittest.TestCase):
    def setUp(self) -> None:
        saved_maze = [row.copy() for row in gmap.MAZE]
        self.addCleanup(lambda: gmap.MAZE.__setitem__(slice(None), saved_maze))
        for y, row in enumerate(gmap.MAZE):
            row[:] = [int(x in (0, gmap.MAP_W - 1) or y in (0, gmap.MAP_H - 1))
                      for x in range(gmap.MAP_W)]

    def test_hit_zone_matches_the_body_width_at_any_distance(self) -> None:
        for distance in (0.8, 3.0, 8.0, 15.0):
            enemy = Enemy(2.5 + distance, 5.5)
            for across, hits in ((enemy.hit_radius * 0.95, True),
                                 (enemy.hit_radius * 1.05, False)):
                with self.subTest(distance=distance, across=across):
                    aim = math.asin(across / distance)
                    self.assertIs(hitscan([enemy], 2.5, 5.5, aim) is enemy, hits)

    def test_far_misses_miss_and_point_blank_body_shots_hit(self) -> None:
        # A fixed 0.15 rad cone hit the first and missed the second.
        far = Enemy(2.5 + 8 * math.cos(0.14), 5.5 + 8 * math.sin(0.14))
        self.assertIsNone(hitscan([far], 2.5, 5.5, 0.0))
        near = Enemy(2.5 + 0.8 * math.cos(0.17), 5.5 + 0.8 * math.sin(0.17))
        self.assertIs(hitscan([near], 2.5, 5.5, 0.0), near)

    def test_nearer_enemy_beside_the_line_does_not_take_the_shot(self) -> None:
        beside = Enemy(5.5, 5.9)
        target = Enemy(8.5, 5.5)
        self.assertIs(hitscan([beside, target], 2.5, 5.5, 0.0), target)
        self.assertIs(hitscan([beside, target], 2.5, 5.5, math.atan2(0.4, 3.0)), beside)

    def test_bigger_bodies_are_easier_to_hit(self) -> None:
        aim = math.asin(0.3 / 5.0)
        self.assertIsNotNone(hitscan([Boss(7.5, 5.5)], 2.5, 5.5, aim))
        self.assertIsNone(hitscan([Scout(7.5, 5.5)], 2.5, 5.5, aim))

    def test_shots_hit_the_part_of_an_enemy_showing_past_a_corner(self) -> None:
        gmap.MAZE[4][3] = 1
        px, py = 1.5, 5.5
        center = math.radians(-43)
        enemy = Enemy(px + 3.5 * math.cos(center), py + 3.5 * math.sin(center))
        self.assertFalse(gmap.has_line_of_sight(px, py, enemy.x, enemy.y))
        self.assertIsNone(hitscan([enemy], px, py, center))
        # Aiming 3 degrees above the corner still passes through the body.
        self.assertIs(hitscan([enemy], px, py, math.radians(-46)), enemy)

    def test_shots_do_not_hit_enemies_behind_the_shooter(self) -> None:
        self.assertIsNone(hitscan([Enemy(1.5, 5.5)], 2.5, 5.5, 0.0))


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
        self.assertTrue(all(a >= b for a, b in zip(steps, steps[1:])))
        self.assertEqual(steps[-1], 0.0)


if __name__ == '__main__':
    unittest.main()
