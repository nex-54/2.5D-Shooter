"""Exercise update ordering, pause, level transitions, and restart together."""

import unittest
from unittest.mock import patch

import pygame

from shooter.constants import INITIAL_AMMO, WEAPONS
from shooter.entities import Boss, Enemy, HealthPack, Rocket
from shooter.input import handle_events
from shooter.map import DOOR_TILE
from shooter.simulation import update_game
from shooter.state import GameState, reset_game, start_level
from shooter.types import DoorAnim
from tests.support import Keys, SoundMocks, open_world


class GameLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(seed=0)
        self.state.world = open_world()
        self.sounds = SoundMocks()
        self.sfx = self.sounds.sfx

    def tick(self) -> bool:
        return update_game(self.state, 16, Keys(), set(), self.sfx)

    def test_lethal_enemy_attack_cannot_be_undone_by_a_pickup(self) -> None:
        self.state.hp = 5
        self.state.enemies = [Enemy(self.state.px + 0.7, self.state.py)]
        pack = HealthPack(self.state.px, self.state.py)
        self.state.health_packs = [pack]
        self.tick()
        self.assertTrue(self.state.game_over)
        self.assertLessEqual(self.state.hp, 0)
        self.assertTrue(pack.active)
        self.sounds["pickup"].play.assert_not_called()

    def test_lethal_rocket_damage_also_precedes_pickups(self) -> None:
        self.state.px, self.state.py = 4.79, 5.5
        self.state.hp = 5
        self.state.world.maze[5][5] = 1
        self.state.rockets = [Rocket(4.95, 5.5, 0.0)]
        pack = HealthPack(self.state.px, self.state.py)
        self.state.health_packs = [pack]
        self.tick()
        self.assertTrue(self.state.game_over)
        self.assertTrue(pack.active)

    def test_living_player_can_still_heal(self) -> None:
        self.state.hp = 5
        pack = HealthPack(self.state.px, self.state.py)
        self.state.health_packs = [pack]
        self.tick()
        self.assertEqual(self.state.hp, 30)
        self.assertFalse(pack.active)
        self.assertFalse(self.state.game_over)

    def test_pause_and_game_over_freeze_all_simulation(self) -> None:
        for status in ("paused", "game_over"):
            with self.subTest(status=status):
                state = GameState(seed=0)
                state.world = open_world()
                setattr(state, status, True)
                state.weapon = 2
                state.owned[2] = True
                state.mouse_held = True
                state.shoot_timer = 100
                state.spawn_grace = 1000
                state.enemies = [Enemy(2.2, 1.5)]
                state.door_anim[(5, 5)] = DoorAnim(phase="opening", progress=0.0, timer=0)
                state.world.maze[5][5] = DOOR_TILE
                state.rockets = [Rocket(3.5, 1.5, 0.0)]
                ammo = state.ammo.copy()
                moved = update_game(state, 50, Keys(pygame.K_SPACE), {pygame.KSCAN_W}, self.sfx)
                self.assertFalse(moved)
                self.assertEqual((state.px, state.py, state.jump_height), (1.5, 1.5, 0))
                self.assertEqual(state.game_time, 0)
                self.assertEqual(state.ammo, ammo)
                self.assertEqual(state.shoot_timer, 100)
                self.assertEqual(state.spawn_grace, 1000)
                self.assertEqual(state.enemies[0].x, 2.2)
                self.assertEqual(state.rockets[0].x, 3.5)
                self.assertEqual(state.door_anim[(5, 5)]["progress"], 0)

    def test_exit_transitions_preserve_inventory_and_clear_transient_state(self) -> None:
        start_level(self.state, 1)
        previous_world = self.state.world
        boss = self.state.boss
        assert boss is not None
        boss.take_damage(boss.hp)
        self.state.px, self.state.py = (v + 0.5 for v in self.state.world.exit_pos)
        self.state.owned[1] = True
        self.state.weapon = 1
        self.state.ammo = [17, 6, 2, 0]
        self.state.hp = 30
        self.state.kills = 7
        self.state.rockets = [Rocket(1.5, 1.5, 0)]
        self.state.door_anim[(5, 5)] = DoorAnim(phase="open", progress=1.0, timer=5000)
        self.tick()
        self.assertEqual(self.state.level, 2)
        self.assertIsNot(self.state.world, previous_world)
        self.assertEqual((self.state.px, self.state.py), self.state.world.player_spawn)
        self.assertEqual(self.state.ammo, [17, 6, 2, 0])
        self.assertEqual(self.state.weapon, 1)
        self.assertTrue(self.state.owned[1])
        self.assertEqual(self.state.hp, 100)
        self.assertEqual(self.state.kills, 0)
        self.assertEqual(self.state.rockets, [])
        self.assertEqual(self.state.door_anim, {})
        self.assertFalse(self.state.exit_open)

    def test_death_at_exit_does_not_load_another_level(self) -> None:
        boss = Boss(10.5, 10.5)
        boss.take_damage(boss.hp)
        self.state.boss = boss
        self.state.px, self.state.py = (v + 0.5 for v in self.state.world.exit_pos)
        self.state.hp = 0
        self.tick()
        self.assertTrue(self.state.game_over)
        self.assertEqual(self.state.level, 1)

    def test_restart_key_rebuilds_level_and_resets_inventory(self) -> None:
        reset_game(self.state)
        original_maze = [row.copy() for row in self.state.world.maze]
        self.state.game_over = True
        self.state.hp = -5
        self.state.ammo = [0, 0, 0, 0]
        self.state.owned = [True] * 5
        self.state.weapon = 3
        self.state.rockets = [Rocket(3.5, 1.5, 0)]
        restart = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, scancode=pygame.KSCAN_R)
        with patch("shooter.input.pygame.event.get", return_value=[restart]):
            self.assertTrue(handle_events(self.state, self.sfx, set()))
        self.assertFalse(self.state.game_over)
        self.assertEqual(self.state.hp, 100)
        self.assertEqual(self.state.ammo, list(INITIAL_AMMO))
        self.assertEqual(self.state.owned, [weapon.initially_owned for weapon in WEAPONS])
        self.assertEqual(self.state.weapon, 0)
        self.assertEqual(self.state.rockets, [])
        self.assertEqual(self.state.world.maze, original_maze)
