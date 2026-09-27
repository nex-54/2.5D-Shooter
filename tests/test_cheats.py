"""Exercise typed cheat codes, damage immunity, and cheat lifecycle rules."""

import unittest
from unittest.mock import patch

import pygame

from shooter.combat import fire_weapon, update_enemies, update_rockets
from shooter.constants import INITIAL_AMMO, MAX_AMMO, WEAPONS, Weapon
from shooter.entities import Boss, Enemy, Rocket, Scout, Spider
from shooter.input import handle_events
from shooter.simulation import update_game
from shooter.state import GameState, reset_game, start_level
from tests.support import Keys, SoundMocks, open_world


class CheatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(seed=0)
        self.state.world = open_world()
        self.sounds = SoundMocks()
        self.pressed: set[int] = set()

    def send(self, *events: pygame.event.Event) -> bool:
        with patch("shooter.input.pygame.event.get", return_value=list(events)):
            return handle_events(self.state, self.sounds.sfx, self.pressed)

    def type_code(self, code: str) -> bool:
        events: list[pygame.event.Event] = []
        for letter in code:
            key = ord(letter.lower())
            scancode = pygame.KSCAN_A + key - pygame.K_a
            events.append(
                pygame.event.Event(pygame.KEYDOWN, key=key, scancode=scancode, unicode=letter)
            )
            events.append(pygame.event.Event(pygame.KEYUP, key=key, scancode=scancode))
        return self.send(*events)

    def test_iddqd_toggles_only_after_the_complete_code_across_frames(self) -> None:
        self.assertFalse(self.state.god_mode)
        for letter in "IdDq":
            self.assertTrue(self.type_code(letter))
            self.assertFalse(self.state.god_mode)
        self.sounds["pickup"].play.assert_not_called()
        # Modifier presses must not interrupt a code typed with mixed casing.
        self.send(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LSHIFT, scancode=0))
        self.assertTrue(self.type_code("D"))
        self.assertTrue(self.state.god_mode)
        self.sounds["pickup"].play.assert_called_once()
        self.type_code("iddqd")
        self.assertFalse(self.state.god_mode)
        self.assertEqual(self.sounds["pickup"].play.call_count, 2)

    def test_mistyped_codes_do_nothing_and_a_fresh_code_still_works(self) -> None:
        self.type_code("wasd" * 100 + "iddqxddidkfxa")
        self.assertFalse(self.state.god_mode)
        self.assertEqual(self.state.ammo, list(INITIAL_AMMO))
        self.assertLessEqual(len(self.state.cheat_buffer), 5)
        self.sounds["pickup"].play.assert_not_called()
        self.type_code("iiddqd")
        self.assertTrue(self.state.god_mode)

    def test_idkfa_unlocks_and_refills_every_weapon_without_switching_or_resetting_cooldowns(
        self,
    ) -> None:
        self.state.ammo = [0] * len(MAX_AMMO)
        self.state.weapon_cooldowns = [100] * len(WEAPONS)
        self.type_code("IDKFA")
        self.assertEqual(self.state.owned, [True] * len(WEAPONS))
        self.assertEqual(self.state.ammo, list(MAX_AMMO))
        self.assertEqual(self.state.weapon, Weapon.PISTOL)
        self.assertEqual(self.state.weapon_cooldowns, [100] * len(WEAPONS))
        self.assertFalse(self.state.god_mode)
        self.sounds["pickup"].play.assert_called_once()
        self.state.ammo = [0] * len(MAX_AMMO)
        self.type_code("idkfa")
        self.assertEqual(self.state.ammo, list(MAX_AMMO))
        self.assertEqual(self.sounds["pickup"].play.call_count, 2)

    def test_cheats_are_disabled_while_paused_dead_or_game_over(self) -> None:
        for status in ("paused", "dead", "game_over"):
            with self.subTest(status=status):
                self.state.reset()
                if status == "dead":
                    self.state.hp = 0
                else:
                    setattr(self.state, status, True)
                self.type_code("iddqd")
                self.type_code("idkfa")
                self.assertFalse(self.state.god_mode)
                self.assertEqual(self.state.owned, [weapon.initially_owned for weapon in WEAPONS])
                self.assertEqual(self.state.ammo, list(INITIAL_AMMO))
        self.sounds["pickup"].play.assert_not_called()

    def test_pausing_or_losing_focus_discards_a_partial_code(self) -> None:
        for pause in (
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=pygame.KSCAN_ESCAPE),
            pygame.event.Event(pygame.WINDOWFOCUSLOST),
        ):
            with self.subTest(pause=pause):
                self.type_code("iddq")
                self.send(pause)
                self.send(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
                self.type_code("d")
                self.assertFalse(self.state.god_mode)
                self.type_code("iddqd")
                self.assertTrue(self.state.god_mode)
                self.state.reset()

    def test_god_mode_blocks_every_enemy_type_and_damage_resumes_when_disabled(self) -> None:
        for enemy_type in (Enemy, Scout, Spider, Boss):
            with self.subTest(enemy=enemy_type.__name__):
                self.state.reset()
                self.state.world = open_world()
                self.state.hp = 1
                enemy = enemy_type(self.state.px + 0.5, self.state.py)
                self.state.enemies = [enemy]
                self.type_code("iddqd")
                update_game(self.state, 16, Keys(), set(), self.sounds.sfx)
                self.assertEqual(self.state.hp, 1)
                self.assertFalse(self.state.game_over)
                self.assertEqual(self.state.damage_cooldown, 0)
                self.assertTrue(enemy.attacking)
                self.type_code("iddqd")
                update_enemies(self.state, 16, self.sounds.sfx)
                self.assertEqual(self.state.hp, 1 - enemy.damage)

    def test_god_mode_blocks_rocket_splash_without_protecting_enemies(self) -> None:
        self.state.px, self.state.py = 4.5, 5.5
        self.state.hp = 1
        enemy = Enemy(5.5, 5.5)
        self.state.enemies = [enemy]
        rocket = Rocket(self.state.px, self.state.py, 0.0)
        self.state.rockets = [rocket]
        self.type_code("iddqd")
        update_rockets(self.state, 100, self.sounds.sfx)
        self.assertTrue(rocket.exploded)
        self.assertFalse(enemy.alive)
        self.assertEqual(self.state.kills, 1)
        self.assertEqual(self.state.hp, 1)
        self.assertEqual(self.state.damage_cooldown, 0)
        self.sounds["explosion"].play.assert_called_once()

    def test_god_mode_blocks_muzzle_explosions_and_can_be_disabled(self) -> None:
        self.state.world.maze[5][5] = 1
        self.state.px, self.state.py = 4.79, 5.5
        self.type_code("idkfaiddqd")
        self.state.switch_weapon(Weapon.ROCKETS)
        hp = self.state.hp
        fire_weapon(self.state, self.sounds.sfx)
        self.assertTrue(self.state.rockets[0].exploded)
        self.assertEqual(self.state.hp, hp)
        self.type_code("iddqd")
        self.state.shoot_timer = 0
        fire_weapon(self.state, self.sounds.sfx)
        self.assertLess(self.state.hp, hp)

    def test_level_changes_preserve_cheats_and_restart_clears_them(self) -> None:
        self.type_code("iddqdidkfaiddq")
        start_level(self.state, 2)
        self.assertTrue(self.state.god_mode)
        self.assertEqual(self.state.owned, [True] * len(WEAPONS))
        self.assertEqual(self.state.ammo, list(MAX_AMMO))
        self.type_code("d")
        self.assertTrue(self.state.god_mode)
        self.type_code("iddq")
        reset_game(self.state)
        self.assertFalse(self.state.god_mode)
        self.assertEqual(self.state.owned, [weapon.initially_owned for weapon in WEAPONS])
        self.assertEqual(self.state.ammo, list(INITIAL_AMMO))
        self.type_code("d")
        self.assertFalse(self.state.god_mode)
