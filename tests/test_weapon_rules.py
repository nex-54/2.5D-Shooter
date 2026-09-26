"""Weapon definitions drive firing, shared ammo, pickups, and kill accounting."""

import unittest
from unittest.mock import patch

import pygame

from shooter.combat import update_combat
from shooter.constants import EMPTY_CLICK_DELAY, MAX_AMMO, WEAPONS, Weapon
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
        if self.state.weapon == Weapon.GATLING:
            update_combat(self.state, 0, self.sounds.sfx)

    def test_every_weapon_consumes_one_round_and_respects_cooldown(self) -> None:
        for weapon_id, weapon in zip(Weapon, WEAPONS, strict=True):
            with self.subTest(weapon=weapon.name):
                self.state.weapon = weapon_id
                self.state.owned[weapon_id] = True
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
        for weapon_id in Weapon:
            with self.subTest(weapon=weapon_id.name):
                self.state.weapon = weapon_id
                self.state.owned[weapon_id] = False
                self.state.shoot_timer = 0
                self.state.ammo = [3, 3, 3, 3]
                self.fire()
                self.assertEqual(self.state.ammo, [3, 3, 3, 3])
                self.state.owned[weapon_id] = True
                self.state.ammo = [0, 0, 0, 0]
                self.fire()
                self.assertEqual(self.state.ammo, [0, 0, 0, 0])
                self.assertEqual(target.hp, target.max_hp)
                self.assertEqual(self.state.kills, 0)
                self.assertEqual(self.state.rockets, [])

    def test_pistol_and_gatling_share_ammo_when_switching(self) -> None:
        self.state.ammo[0] = 10
        self.fire()
        self.state.owned[Weapon.GATLING] = True
        switch = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3, scancode=pygame.KSCAN_3)
        with patch("shooter.input.pygame.event.get", return_value=[switch]):
            handle_events(self.state, self.sounds.sfx, set())
        self.fire()
        self.assertEqual(self.state.ammo[0], 8)

    def test_switching_away_and_back_cannot_bypass_any_weapon_cooldown(self) -> None:
        for weapon_id, weapon in zip(Weapon, WEAPONS, strict=True):
            with self.subTest(weapon=weapon.name):
                self.state.reset()
                self.state.world = open_world()
                self.state.owned = [True] * len(WEAPONS)
                self.state.ammo = [10, 10, 10, 10]
                self.state.switch_weapon(weapon_id)
                self.fire()
                ammo = self.state.ammo.copy()
                other = Weapon.NUKE if weapon_id != Weapon.NUKE else Weapon.PISTOL
                self.state.switch_weapon(other)
                update_combat(self.state, weapon.fire_interval_ms - 1, self.sounds.sfx)
                self.state.switch_weapon(weapon_id)
                self.fire()
                self.assertEqual(self.state.ammo, ammo)
                update_combat(self.state, 1, self.sounds.sfx)
                self.fire()
                ammo[weapon.ammo_pool] -= 1
                self.assertEqual(self.state.ammo, ammo)

    def test_empty_click_cooldown_survives_switching(self) -> None:
        self.state.ammo[0] = 0
        self.fire()
        self.state.switch_weapon(Weapon.NUKE)
        self.state.switch_weapon(Weapon.PISTOL)
        self.fire()
        self.sounds["empty"].play.assert_called_once()
        update_combat(self.state, EMPTY_CLICK_DELAY, self.sounds.sfx)
        self.fire()
        self.assertEqual(self.sounds["empty"].play.call_count, 2)

    def test_gatling_fire_rate_is_independent_of_frame_intervals(self) -> None:
        schedules = [[dt] * (6000 // dt) for dt in (10, 16, 20, 30, 40, 50, 250)]
        schedules.append([17, 43, 31, 9] * 60)
        for schedule in schedules:
            with self.subTest(frame_intervals=schedule[:4]):
                self.state.reset()
                self.state.world = open_world()
                self.state.owned[Weapon.GATLING] = True
                self.state.switch_weapon(Weapon.GATLING)
                self.state.ammo[0] = 999
                target = Enemy(self.state.px + 1, self.state.py)
                target.hp = 1000
                self.state.enemies = [target]
                self.fire()  # First shot at time zero, then six seconds of held fire.
                for dt in schedule:
                    update_combat(self.state, dt, self.sounds.sfx)
                self.assertEqual(self.state.ammo[0], 999 - 101)
                self.assertEqual(target.hp, 1000 - 101)

    def test_idle_gatling_does_not_accumulate_catch_up_shots(self) -> None:
        self.state.owned[Weapon.GATLING] = True
        self.state.switch_weapon(Weapon.GATLING)
        self.fire()
        self.state.mouse_held = False
        update_combat(self.state, 6000, self.sounds.sfx)
        ammo = self.state.ammo[0]
        self.fire()
        self.assertEqual(self.state.ammo[0], ammo - 1)
        self.assertEqual(self.state.shoot_timer, WEAPONS[Weapon.GATLING].fire_interval_ms)

    def test_gatling_catch_up_stops_when_ammo_runs_out(self) -> None:
        self.state.owned[Weapon.GATLING] = True
        self.state.switch_weapon(Weapon.GATLING)
        self.state.ammo[0] = 3
        self.fire()
        update_combat(self.state, 250, self.sounds.sfx)
        self.assertEqual(self.state.ammo[0], 0)
        self.assertEqual(self.sounds["gatling"].play.call_count, 3)
        self.sounds["empty"].play.assert_called_once()

    def test_gatling_pickup_unlocks_weapon_and_caps_shared_ammo(self) -> None:
        self.state.ammo[0] = MAX_AMMO[0] - 1
        pickup = WeaponPickup(self.state.px, self.state.py, Weapon.GATLING)
        self.state.weapon_pickups = [pickup]
        update_pickups(self.state, 16, self.sounds.sfx)
        self.assertTrue(self.state.owned[Weapon.GATLING])
        self.assertEqual(self.state.weapon, Weapon.GATLING)
        self.assertEqual(self.state.ammo[0], MAX_AMMO[0])
        self.assertFalse(pickup.active)

    def test_shotgun_counts_a_kill_once_despite_multiple_pellets(self) -> None:
        target = Enemy(3.5, 5.5)
        self.state.enemies = [target]
        self.state.weapon = Weapon.SHOTGUN
        self.state.owned[Weapon.SHOTGUN] = True
        self.state.ammo[1] = 3
        self.fire()
        self.assertFalse(target.alive)
        self.assertEqual(self.state.kills, 1)
        self.sounds["enemy_die"].play.assert_called_once()

    def test_nuke_kills_regular_enemies_but_spares_boss(self) -> None:
        enemy, boss = Enemy(4.5, 5.5), Boss(6.5, 5.5)
        self.state.enemies = [enemy, boss]
        self.state.weapon = Weapon.NUKE
        self.fire()
        self.assertFalse(enemy.alive)
        self.assertEqual(boss.hp, boss.max_hp)
        self.assertEqual(self.state.kills, 1)
        self.sounds["enemy_die"].play.assert_called_once()
        self.sounds["boss_die"].play.assert_not_called()
