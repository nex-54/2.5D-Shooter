"""Verify sight and combat occlusion at walls, doors, barriers, and grid corners."""

from __future__ import annotations

import math
import unittest
from unittest.mock import MagicMock

from shooter import map as gmap
from shooter.entities import Enemy, Rocket, hitscan
from shooter.game import GameState, update_rockets
from tests.support import open_world


class LineOfSightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = open_world()

    def assert_sight_both_directions(
        self, start: tuple[float, float], end: tuple[float, float], expected: bool
    ) -> None:
        for source, target in ((start, end), (end, start)):
            with self.subTest(source=source, target=target):
                self.assertEqual(self.world.has_line_of_sight(*source, *target), expected)

    def test_thin_wall_and_door_corner_crossings_block_sight(self) -> None:
        paths = (
            ((2.9, 3.2), (3.2, 2.9)),
            ((3.8, 2.9), (4.1, 3.2)),
            ((4.1, 3.8), (3.8, 4.1)),
            ((3.2, 4.1), (2.9, 3.8)),
            ((1.5, 4.6), (4.8, 1.3)),
        )
        for tile in (1, gmap.DOOR_TILE, gmap.BARRIER_TILE):
            self.world.maze[3][3] = tile
            for start, end in paths:
                with self.subTest(tile=tile, start=start, end=end):
                    self.assert_sight_both_directions(start, end, tile == gmap.BARRIER_TILE)

    def test_exact_corner_contacts_do_not_allow_sight_through_walls(self) -> None:
        for tile in (1, gmap.DOOR_TILE, gmap.BARRIER_TILE):
            self.world.maze[3][3] = tile
            with self.subTest(tile=tile):
                self.assert_sight_both_directions((2.5, 3.5), (3.5, 2.5), tile == gmap.BARRIER_TILE)

    def test_clear_paths_near_wall_corners_stay_visible(self) -> None:
        self.world.maze[3][3] = 1
        paths = (
            ((2.8, 3.1), (3.1, 2.8)),
            ((2.0, 2.99), (5.0, 2.99)),
            ((2.99, 2.0), (2.99, 5.0)),
        )
        for start, end in paths:
            self.assert_sight_both_directions(start, end, True)

    def test_grid_boundary_endpoints_and_axis_aligned_paths(self) -> None:
        paths = (
            ((2.5, 3.5), (3.0, 3.0)),
            ((3.0, 3.0), (4.0, 4.0)),
            ((2.0, 3.0), (5.0, 3.0)),
            ((3.0, 2.0), (3.0, 5.0)),
            ((3.25, 3.25), (3.25, 3.25)),
            ((3.25, 3.25), (3.26, 3.26)),
        )
        for start, end in paths:
            self.assert_sight_both_directions(start, end, True)

    def test_solid_endpoints_block_even_very_short_sight_lines(self) -> None:
        for tile in (1, gmap.DOOR_TILE):
            self.world.maze[3][3] = tile
            with self.subTest(tile=tile):
                self.assert_sight_both_directions((2.999, 3.5), (3.001, 3.5), False)
                self.assert_sight_both_directions((3.5, 3.5), (3.5, 3.5), False)

    def test_positions_outside_the_map_block_sight(self) -> None:
        # Leave the boundary cell open to distinguish it from a negative coordinate.
        self.world.maze[3][0] = 0
        self.assert_sight_both_directions((-0.01, 3.5), (0.5, 3.5), False)
        self.assert_sight_both_directions((18.5, 3.5), (20.01, 3.5), False)

    def test_wall_corners_block_hitscan_and_enemy_detection(self) -> None:
        self.world.maze[3][3] = 1
        px, py = 2.9, 3.2
        enemy = Enemy(3.2, 2.9)
        angle = math.atan2(enemy.y - py, enemy.x - px)
        self.assertIsNone(hitscan(self.world, [enemy], px, py, angle))
        enemy.update(self.world, px, py, 0)
        self.assertFalse(enemy.alert)
        self.assertFalse(enemy.attacking)

    def test_wall_corner_shields_enemy_from_rocket_splash(self) -> None:
        self.world.maze[3][3] = 1
        state = GameState()
        state.world = self.world
        state.px, state.py = 2.5, 3.2
        sheltered = Enemy(3.2, 2.9)
        exposed = Enemy(2.85, 2.5)
        state.enemies = [sheltered, exposed]
        rocket = Rocket(2.9, 3.2, 0.0)
        state.rockets = [rocket]
        update_rockets(state, 16, MagicMock())
        self.assertTrue(rocket.exploded)
        self.assertEqual(sheltered.hp, sheltered.max_hp)
        self.assertFalse(exposed.alive)

    def fire_rocket(self, enemy: Enemy) -> Rocket:
        state = GameState()
        state.world = self.world
        state.px, state.py = 2.5, 5.5
        state.enemies = [enemy]
        rocket = Rocket(2.9, 5.5, 0.0)
        state.rockets = [rocket]
        for _ in range(100):
            update_rockets(state, 16, MagicMock())
            if rocket.exploded:
                return rocket
        self.fail("rocket never detonated")

    def test_barriers_do_not_block_sight_shots_or_rockets(self) -> None:
        self.world.maze[5][4] = gmap.BARRIER_TILE
        enemy = Enemy(6.5, 5.5)
        self.assertIs(hitscan(self.world, [enemy], 2.5, 5.5, 0.0), enemy)
        enemy.update(self.world, 2.5, 5.5, 16)
        self.assertTrue(enemy.alert)
        rocket = self.fire_rocket(enemy)
        self.assertGreater(rocket.x, 5.0)
        self.assertFalse(enemy.alive)

    def test_walls_and_closed_doors_still_block(self) -> None:
        for tile in (1, gmap.DOOR_TILE):
            with self.subTest(tile=tile):
                self.world.maze[5][4] = tile
                enemy = Enemy(6.5, 5.5)
                self.assertIsNone(hitscan(self.world, [enemy], 2.5, 5.5, 0.0))
                enemy.update(self.world, 2.5, 5.5, 16)
                self.assertFalse(enemy.alert)
                rocket = self.fire_rocket(enemy)
                self.assertLess(rocket.x, 4.0)
                self.assertTrue(enemy.alive)


if __name__ == "__main__":
    unittest.main()
