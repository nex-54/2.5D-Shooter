"""Wandering enemies respect the same solid tiles as chasing enemies."""

import math
import random
import unittest

from shooter.entities import Boss, Enemy, Scout, Spider
from shooter.map import BARRIER_TILE, DOOR_TILE, EXIT_TILE, WALL_TILE
from tests.support import open_world


class EnemyCollisionTests(unittest.TestCase):
    def test_wandering_cannot_enter_solid_tile_corners(self) -> None:
        for enemy_type in (Enemy, Boss, Scout, Spider):
            for tile in (WALL_TILE, DOOR_TILE, BARRIER_TILE, EXIT_TILE):
                for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    for dt in (16, 50):
                        with self.subTest(
                            enemy=enemy_type.__name__, tile=tile, dx=dx, dy=dy, dt=dt
                        ):
                            world = open_world()
                            world.maze[10][10] = tile
                            x = 9.999 if dx > 0 else 11.001
                            y = 9.999 if dy > 0 else 11.001
                            enemy = enemy_type(x, y, random.Random(0))
                            enemy.wander_angle = math.atan2(dy, dx)
                            enemy.wander_timer = 1000

                            enemy.update(world, 1.5, 1.5, dt)

                            self.assertFalse(world.is_obstacle(enemy.x, enemy.y))
                            self.assertNotEqual(world.tile_at(enemy.x, enemy.y), EXIT_TILE)

    def test_wandering_still_moves_through_clear_space(self) -> None:
        for enemy_type in (Enemy, Boss, Scout, Spider):
            with self.subTest(enemy=enemy_type.__name__):
                enemy = enemy_type(10.5, 10.5, random.Random(0))
                enemy.wander_angle = math.pi / 4
                enemy.wander_timer = 1000

                enemy.update(open_world(), 1.5, 1.5, 50)

                self.assertGreater(enemy.x, 10.5)
                self.assertGreater(enemy.y, 10.5)
                self.assertTrue(enemy.moving)
