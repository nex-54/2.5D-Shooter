"""Verify that barriers block movement but not sight lines, shots, or rockets."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from shooter import map as gmap
from shooter.entities import Enemy, Rocket, hitscan
from shooter.game import GameState, update_rockets


class LineOfSightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_maze = [row.copy() for row in gmap.MAZE]
        self.addCleanup(self.restore_maze)
        for y, row in enumerate(gmap.MAZE):
            row[:] = [int(x in (0, gmap.MAP_W - 1) or y in (0, gmap.MAP_H - 1))
                      for x in range(gmap.MAP_W)]

    def restore_maze(self) -> None:
        gmap.MAZE[:] = self.saved_maze

    def fire_rocket(self, enemy: Enemy) -> Rocket:
        state = GameState()
        state.px, state.py = 2.5, 5.5
        state.enemies = [enemy]
        rocket = Rocket(2.9, 5.5, 0.0)
        state.rockets = [rocket]
        for _ in range(100):
            update_rockets(state, 16, MagicMock())
            if rocket.exploded:
                return rocket
        self.fail('rocket never detonated')

    def test_barriers_do_not_block_sight_shots_or_rockets(self) -> None:
        gmap.MAZE[5][4] = gmap.BARRIER_TILE
        enemy = Enemy(6.5, 5.5)
        self.assertIs(hitscan([enemy], 2.5, 5.5, 0.0), enemy)
        enemy.update(2.5, 5.5, 16)
        self.assertTrue(enemy.alert)
        rocket = self.fire_rocket(enemy)
        self.assertGreater(rocket.x, 5.0)
        self.assertFalse(enemy.alive)

    def test_walls_and_closed_doors_still_block(self) -> None:
        for tile in (1, gmap.DOOR_TILE):
            with self.subTest(tile=tile):
                gmap.MAZE[5][4] = tile
                enemy = Enemy(6.5, 5.5)
                self.assertIsNone(hitscan([enemy], 2.5, 5.5, 0.0))
                enemy.update(2.5, 5.5, 16)
                self.assertFalse(enemy.alert)
                rocket = self.fire_rocket(enemy)
                self.assertLess(rocket.x, 4.0)
                self.assertTrue(enemy.alive)


if __name__ == '__main__':
    unittest.main()
