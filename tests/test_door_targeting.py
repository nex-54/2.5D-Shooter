"""Door interaction stops at the first obstacle, including thin corner crossings."""

import math
import unittest

from shooter.map import BARRIER_TILE, DOOR_TILE, EXIT_TILE, WALL_TILE
from tests.support import open_world


class DoorTargetingTests(unittest.TestCase):
    def test_wall_corner_cannot_be_skipped_to_open_a_hidden_door(self) -> None:
        world = open_world()
        world.maze[3][3] = WALL_TILE
        world.maze[2][4] = DOOR_TILE
        self.assertIsNone(world.find_door_in_front(2.3, 3.3, -0.404))

    def test_door_corner_cannot_be_skipped_for_a_farther_door(self) -> None:
        world = open_world()
        world.maze[3][3] = DOOR_TILE
        world.maze[2][4] = DOOR_TILE
        self.assertEqual(world.find_door_in_front(2.3, 3.3, -0.404), (3, 3))

    def test_door_is_targeted_from_all_four_sides_at_its_actual_range(self) -> None:
        world = open_world()
        world.maze[5][5] = DOOR_TILE
        for x, y, angle in (
            (4.3, 5.5, 0.0),
            (6.7, 5.5, math.pi),
            (5.5, 4.3, math.pi / 2),
            (5.5, 6.7, -math.pi / 2),
        ):
            with self.subTest(position=(x, y)):
                self.assertIsNone(world.find_door_in_front(x, y, angle, max_range=0.69))
                self.assertEqual(world.find_door_in_front(x, y, angle, max_range=0.71), (5, 5))

    def test_other_solid_tiles_block_interaction(self) -> None:
        for tile in (WALL_TILE, BARRIER_TILE, EXIT_TILE):
            with self.subTest(tile=tile):
                world = open_world()
                world.maze[5][5] = tile
                world.maze[5][6] = DOOR_TILE
                self.assertIsNone(world.find_door_in_front(4.5, 5.5, 0))

    def test_clear_space_and_map_boundaries_have_no_door(self) -> None:
        world = open_world()
        for angle in (0, math.pi / 2, math.pi, -math.pi / 2):
            with self.subTest(angle=angle):
                self.assertIsNone(world.find_door_in_front(1.5, 1.5, angle))
