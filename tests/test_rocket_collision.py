"""Projectile contact must agree with walls and splash visibility at every step."""

import math
import unittest
from unittest.mock import patch

import pygame

from shooter.combat import update_rockets
from shooter.constants import WEAPONS, Weapon
from shooter.entities import Enemy, Rocket
from shooter.input import handle_events
from shooter.map import BARRIER_TILE, DOOR_TILE
from shooter.state import GameState
from tests.support import SoundMocks, open_world


class RocketCollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(seed=0)
        self.state.world = open_world()
        self.state.px, self.state.py = 1.5, 1.5
        self.sounds = SoundMocks()
        self.sfx = self.sounds.sfx

    def test_corners_stop_rockets_even_when_both_endpoints_are_clear(self) -> None:
        paths = (
            ((2.9, 3.2), (3.2, 2.9)),
            ((3.8, 2.9), (4.1, 3.2)),
            ((4.1, 3.8), (3.8, 4.1)),
            ((3.2, 4.1), (2.9, 3.8)),
            ((2.9, 3.1), (3.1, 2.9)),
        )
        for tile in (1, DOOR_TILE):
            self.state.world.maze[3][3] = tile
            for start, end in paths:
                for source, target in ((start, end), (end, start)):
                    with self.subTest(tile=tile, source=source, target=target):
                        rocket = Rocket(
                            *source, math.atan2(target[1] - source[1], target[0] - source[0])
                        )
                        self.state.rockets = [rocket]
                        update_rockets(self.state, 50, self.sfx)
                        self.assertTrue(rocket.exploded)
                        self.assertFalse(self.state.world.blocks_sight(rocket.x, rocket.y))
                        self.assertTrue(
                            self.state.world.has_line_of_sight(*source, rocket.x, rocket.y)
                        )

    def test_wall_contact_is_independent_of_frame_size(self) -> None:
        self.state.world.maze[5][5] = 1
        for dt in (8, 16, 50):
            with self.subTest(dt=dt):
                rocket = Rocket(2.9, 5.5, 0.0)
                self.state.rockets = [rocket]
                for _ in range(100):
                    update_rockets(self.state, dt, self.sfx)
                    if rocket.exploded:
                        break
                self.assertTrue(rocket.exploded)
                self.assertAlmostEqual(rocket.x, 5.0, places=5)
                self.assertLess(rocket.x, 5.0)

    def test_muzzle_hits_close_wall_and_applies_self_damage_on_clear_side(self) -> None:
        self.state.world.maze[5][5] = 1
        self.state.px, self.state.py = 4.79, 5.5
        self.state.weapon = Weapon.ROCKETS
        self.state.owned[Weapon.ROCKETS] = True
        self.state.ammo[WEAPONS[Weapon.ROCKETS].ammo_pool] = 1
        click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
        with patch("shooter.input.pygame.event.get", return_value=[click]):
            handle_events(self.state, self.sfx, set())
        rocket = self.state.rockets[0]
        self.assertTrue(rocket.exploded)
        self.assertLess(rocket.x, 5)
        self.assertFalse(self.state.world.blocks_sight(rocket.x, rocket.y))
        self.assertLess(self.state.hp, 100)
        hp = self.state.hp
        update_rockets(self.state, 16, self.sfx)
        self.assertEqual(self.state.hp, hp)
        self.sounds["explosion"].play.assert_called_once()

    def test_near_corner_miss_and_barriers_remain_clear(self) -> None:
        for tile, source in ((1, (2.8, 3.1)), (BARRIER_TILE, (2.9, 3.2))):
            with self.subTest(tile=tile):
                self.state.world.maze[3][3] = tile
                rocket = Rocket(*source, -math.pi / 4)
                self.state.rockets = [rocket]
                update_rockets(self.state, 50, self.sfx)
                self.assertFalse(rocket.exploded)

    def test_enemy_contacts_are_swept_and_nearest_contact_wins(self) -> None:
        near = Enemy(5.0, 5.5)
        far = Enemy(8.0, 5.5)
        self.state.enemies = [far, near]
        rocket = Rocket(2.9, 5.5, 0.0)
        self.state.rockets = [rocket]
        update_rockets(self.state, 1000, self.sfx)
        self.assertTrue(rocket.exploded)
        self.assertAlmostEqual(rocket.x, 4.4)
        self.assertFalse(near.alive)
        self.assertEqual(far.hp, far.max_hp)
        self.assertEqual(self.state.kills, 1)
