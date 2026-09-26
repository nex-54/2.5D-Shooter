"""Weapon definitions drive firing, shared ammo, pickups, and kill accounting."""

import unittest
from unittest.mock import patch

import pygame

from shooter.combat import update_combat
from shooter.constants import MAX_AMMO, WEAPONS
from shooter.entities import Boss, Enemy, WeaponPickup
from shooter.input import handle_events
from shooter.simulation import update_pickups
from shooter.state import GameState
from tests.support import SoundMocks, open_world


class WeaponRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(seed=0)
        self.state.world = open_world()
        self.state.px, self.state.py = 2.5, 5.5
        self.sounds = SoundMocks()

    def fire(self) -> None:
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
        with patch("shooter.input.pygame.event.get", return_value=[event]):
            handle_events(self.state, self.sounds.sfx, set())
        if self.state.weapon == 2:
            update_combat(self.state, 0, self.sounds.sfx)

    def test_every_weapon_consumes_one_round_and_respects_cooldown(self) -> None:
        for index, weapon in enumerate(WEAPONS):
            with self.subTest(weapon=weapon.name):
                self.state.weapon = index
                self.state.owned[index] = True
                self.state.ammo = [3, 3, 3, 3]
                self.state.shoot_timer = 0
                self.fire()
                expected = [3, 3, 3, 3]
                expected[weapon.ammo_pool] -= 1
                self.assertEqual(self.state.ammo, expected)
                self.assertEqual(self.state.shoot_timer, weapon.fire_interval_ms)
                self.fire()
                self.assertEqual(self.state.ammo, expected)

    def test_unowned_and_empty_weapons_cannot_deal_damage(self) -> None:
        target = Enemy(3.5, 5.5)
        self.state.enemies = [target]
        for index in range(len(WEAPONS)):
            with self.subTest(weapon=index):
                self.state.weapon = index
                self.state.owned[index] = False
                self.state.shoot_timer = 0
                self.state.ammo = [3, 3, 3, 3]
                self.fire()
                self.assertEqual(self.state.ammo, [3, 3, 3, 3])
                self.state.owned[index] = True
                self.state.ammo = [0, 0, 0, 0]
                self.fire()
                self.assertEqual(self.state.ammo, [0, 0, 0, 0])
                self.assertEqual(target.hp, target.max_hp)
                self.assertEqual(self.state.kills, 0)
                self.assertEqual(self.state.rockets, [])

    def test_pistol_and_gatling_share_ammo_when_switching(self) -> None:
        self.state.ammo[0] = 10
        self.fire()
        self.state.owned[2] = True
        switch = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3, scancode=pygame.KSCAN_3)
        with patch("shooter.input.pygame.event.get", return_value=[switch]):
            handle_events(self.state, self.sounds.sfx, set())
        self.fire()
        self.assertEqual(self.state.ammo[0], 8)

    def test_gatling_pickup_unlocks_weapon_and_caps_shared_ammo(self) -> None:
        self.state.ammo[0] = MAX_AMMO[0] - 1
        pickup = WeaponPickup(self.state.px, self.state.py, 2)
        self.state.weapon_pickups = [pickup]
        update_pickups(self.state, 16, self.sounds.sfx)
        self.assertTrue(self.state.owned[2])
        self.assertEqual(self.state.weapon, 2)
        self.assertEqual(self.state.ammo[0], MAX_AMMO[0])
        self.assertFalse(pickup.active)

    def test_shotgun_counts_a_kill_once_despite_multiple_pellets(self) -> None:
        target = Enemy(3.5, 5.5)
        self.state.enemies = [target]
        self.state.weapon = 1
        self.state.owned[1] = True
        self.state.ammo[1] = 3
        self.fire()
        self.assertFalse(target.alive)
        self.assertEqual(self.state.kills, 1)
        self.sounds["enemy_die"].play.assert_called_once()

    def test_nuke_kills_regular_enemies_but_spares_boss(self) -> None:
        enemy, boss = Enemy(4.5, 5.5), Boss(6.5, 5.5)
        self.state.enemies = [enemy, boss]
        self.state.weapon = 4
        self.fire()
        self.assertFalse(enemy.alive)
        self.assertEqual(boss.hp, boss.max_hp)
        self.assertEqual(self.state.kills, 1)
        self.sounds["enemy_die"].play.assert_called_once()
        self.sounds["boss_die"].play.assert_not_called()
