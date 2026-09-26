"""Verify the player's footprint collision, the locked exit, and barrier jumps."""

from __future__ import annotations

import math
import unittest
from unittest.mock import MagicMock, patch

import pygame

from shooter import map as gmap
from shooter.constants import PLAYER_MARGIN
from shooter.entities import Boss
from shooter.game import GameState, check_win_lose, update_doors, update_player
from shooter.types import DoorAnim


class Keys:
    """Stand-in for pygame.key.get_pressed() with only the given keys down."""

    def __init__(self, *down: int) -> None:
        self.down = set(down)

    def __getitem__(self, key: int) -> bool:
        return key in self.down


def distance_to_tile(x: float, y: float, col: int, row: int) -> float:
    return math.hypot(max(col - x, 0.0, x - col - 1), max(row - y, 0.0, y - row - 1))


class PlayerCollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        saved_maze = [row.copy() for row in gmap.MAZE]
        saved_exit = gmap.EXIT_X, gmap.EXIT_Y
        self.addCleanup(self.restore, saved_maze, saved_exit)
        for y, row in enumerate(gmap.MAZE):
            row[:] = [int(x in (0, gmap.MAP_W - 1) or y in (0, gmap.MAP_H - 1))
                      for x in range(gmap.MAP_W)]
        self.state = GameState()
        self.sfx = MagicMock()

    @staticmethod
    def restore(maze: list[list[int]], exit_pos: tuple[int, int]) -> None:
        gmap.MAZE[:] = maze
        gmap.EXIT_X, gmap.EXIT_Y = exit_pos

    def walk(self, frames: int, keys: Keys | None = None,
             dt: int = 16) -> list[tuple[float, float]]:
        """Hold W for some frames and return the path the player took."""
        path: list[tuple[float, float]] = []
        for _ in range(frames):
            update_player(self.state, dt, keys or Keys(), {pygame.KSCAN_W}, self.sfx)
            path.append((self.state.px, self.state.py))
        return path

    def test_exit_stays_shut_until_the_boss_dies(self) -> None:
        exit_x = gmap.MAP_W - 1
        gmap.MAZE[5][exit_x] = gmap.EXIT_TILE
        gmap.EXIT_X, gmap.EXIT_Y = exit_x, 5
        self.state.boss = Boss(10.5, 10.5)
        self.state.px, self.state.py, self.state.pa = exit_x - 2.5, 5.5, 0.0
        self.walk(60)
        self.assertAlmostEqual(self.state.px, exit_x - PLAYER_MARGIN, places=5)
        with patch('shooter.game.start_level') as start_level:
            check_win_lose(self.state)
            start_level.assert_not_called()

            self.state.boss.alive = False
            self.walk(10)
            self.assertEqual(int(self.state.px), exit_x)
            check_win_lose(self.state)
            start_level.assert_called_once_with(self.state, self.state.level + 1)

    def test_footprint_keeps_its_margin_from_corners_and_glancing_walls(self) -> None:
        # A diagonal walk past an outer corner, and a walk that glances off a wall.
        for wall_tiles, start, angle in (
                ([(6, 6)], (5.0, 5.0), math.pi / 4),
                ([(8, row) for row in range(1, gmap.MAP_H - 1)], (6.5, 2.5), math.radians(80)),
        ):
            with self.subTest(walls=wall_tiles[:2], angle=angle):
                for col, row in wall_tiles:
                    gmap.MAZE[row][col] = 1
                self.state.px, self.state.py = start
                self.state.pa = angle
                path = self.walk(200)
                closest = min(distance_to_tile(x, y, col, row)
                              for x, y in path for col, row in wall_tiles)
                self.assertGreaterEqual(closest, PLAYER_MARGIN - 1e-5)
                for col, row in wall_tiles:
                    gmap.MAZE[row][col] = 0

    def test_walls_stop_the_player_flush_at_any_frame_rate(self) -> None:
        gmap.MAZE[5][5] = 1
        for dt in (16, 50):
            with self.subTest(dt=dt):
                self.state.px, self.state.py, self.state.pa = 2.5, 5.5, 0.0
                self.walk(100, dt=dt)
                self.assertAlmostEqual(self.state.px, 5 - PLAYER_MARGIN, places=5)

    def test_barriers_block_on_foot_but_can_be_jumped(self) -> None:
        gmap.MAZE[5][5] = gmap.BARRIER_TILE
        self.state.px, self.state.py, self.state.pa = 2.5, 5.5, 0.0
        self.walk(100)
        self.assertAlmostEqual(self.state.px, 5 - PLAYER_MARGIN, places=5)

        self.walk(100, Keys(pygame.K_SPACE))
        self.assertGreater(self.state.px, 6 + PLAYER_MARGIN)

    def test_jump_clears_barriers_but_stays_below_the_ceiling(self) -> None:
        self.state.px, self.state.py = 5.5, 5.5
        update_player(self.state, 16, Keys(pygame.K_SPACE), set(), self.sfx)
        peak = 0.0
        for _ in range(60):
            update_player(self.state, 16, Keys(), set(), self.sfx)
            peak = max(peak, self.state.jump_height)
        self.assertTrue(self.state.on_ground)
        self.assertGreater(peak, 0.35)
        self.assertLess(peak, 0.45)

    def test_doors_stay_open_while_the_footprint_overlaps_them(self) -> None:
        self.state.py = 5.5
        for px, closes in ((5 - PLAYER_MARGIN / 2, False), (5 - PLAYER_MARGIN - 0.01, True)):
            with self.subTest(px=px):
                gmap.MAZE[5][5] = 0
                self.state.door_anim = {(5, 5): DoorAnim(phase='open', progress=1.0, timer=0)}
                self.state.px = px
                update_doors(self.state, 16, self.sfx)
                self.assertEqual(gmap.MAZE[5][5] == gmap.DOOR_TILE, closes)
                self.assertEqual(self.state.door_anim[(5, 5)]['phase'],
                                 'closing' if closes else 'open')


if __name__ == '__main__':
    unittest.main()
