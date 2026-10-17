"""Exercise update ordering, pause, level transitions, and restart together."""

import pygame
import pytest

from shooter.constants import (
    INITIAL_AMMO,
    PLAYER_MAX_HP,
    SPAWN_GRACE_DURATION,
    WEAPONS,
    Weapon,
)
from shooter.entities import Boss, Enemy, HealthPack, Rocket
from shooter.map import DOOR_TILE
from shooter.simulation import update_game
from shooter.state import GameState, reset_game, start_level
from shooter.types import DoorAnim, Sfx
from tests.support import Keys, SoundMocks, send_events


def tick(sfx: Sfx, state: GameState) -> bool:
    return update_game(state, 16, Keys(), set(), sfx)


def test_lethal_enemy_attack_cannot_be_undone_by_a_pickup(
    sfx: Sfx, sounds: SoundMocks, state: GameState
) -> None:
    state.hp = 5
    state.enemies = [Enemy(state.px + 0.7, state.py)]
    pack = HealthPack(state.px, state.py)
    state.health_packs = [pack]
    tick(sfx, state)
    assert state.game_over
    assert state.hp <= 0
    assert pack.active
    sounds["pickup"].play.assert_not_called()


def test_lethal_rocket_damage_also_precedes_pickups(sfx: Sfx, state: GameState) -> None:
    state.px, state.py = 4.79, 5.5
    state.hp = 5
    state.world.maze[5][5] = 1
    state.rockets = [Rocket(4.95, 5.5, 0.0)]
    pack = HealthPack(state.px, state.py)
    state.health_packs = [pack]
    tick(sfx, state)
    assert state.game_over
    assert pack.active


def test_health_pickups_heal_an_injured_player(sounds: SoundMocks, state: GameState) -> None:
    state.hp = 5
    pack = HealthPack(state.px, state.py)
    state.health_packs = [pack]
    tick(sounds.sfx, state)
    assert state.hp == 5 + pack.heal_amount
    assert not pack.active
    assert not state.game_over
    sounds["pickup"].play.assert_called_once()


def test_full_health_preserves_a_pickup_until_the_player_is_hurt(
    sounds: SoundMocks, state: GameState
) -> None:
    pack = HealthPack(state.px, state.py)
    state.health_packs = [pack]
    tick(sounds.sfx, state)
    assert state.hp == PLAYER_MAX_HP
    assert pack.active
    sounds["pickup"].play.assert_not_called()

    # Healing stops at the maximum.
    state.hp -= 5
    tick(sounds.sfx, state)
    assert state.hp == PLAYER_MAX_HP
    assert not pack.active
    sounds["pickup"].play.assert_called_once()


def test_spawn_grace_prevents_attacks_until_the_timer_expires(
    sounds: SoundMocks, state: GameState
) -> None:
    start_level(state, 1)
    enemy = Enemy(state.px + 0.2, state.py)
    state.enemies = [enemy]
    assert state.spawn_grace == SPAWN_GRACE_DURATION

    update_game(state, SPAWN_GRACE_DURATION - 1, Keys(), set(), sounds.sfx)
    assert state.spawn_grace == 1
    assert state.hp == PLAYER_MAX_HP
    assert enemy.attacking
    assert enemy.attack_cooldown == 0
    sounds[enemy.attack_sound].play.assert_not_called()

    update_game(state, 1, Keys(), set(), sounds.sfx)
    assert state.spawn_grace == 0
    assert state.hp == PLAYER_MAX_HP - enemy.damage
    assert enemy.attack_cooldown == enemy.attack_cooldown_duration
    sounds[enemy.attack_sound].play.assert_called_once()


@pytest.mark.parametrize("status", ("paused", "game_over"))
def test_pause_and_game_over_freeze_all_simulation(status: str, sfx: Sfx, state: GameState) -> None:
    setattr(state, status, True)
    state.shoot_timer = 200
    state.weapon = Weapon.GATLING
    state.owned[Weapon.GATLING] = True
    state.mouse_held = True
    state.shoot_timer = 100
    state.spawn_grace = 1000
    state.enemies = [Enemy(2.2, 1.5)]
    state.door_anim[(5, 5)] = DoorAnim(phase="opening", progress=0.0, timer=0)
    state.world.maze[5][5] = DOOR_TILE
    state.rockets = [Rocket(3.5, 1.5, 0.0)]
    ammo = state.ammo.copy()
    moved = update_game(state, 50, Keys(pygame.K_SPACE), {pygame.KSCAN_W}, sfx)
    assert not moved
    assert (state.px, state.py, state.jump_height) == (1.5, 1.5, 0)
    assert state.game_time == 0
    assert state.ammo == ammo
    assert state.shoot_timer == 100
    assert state.weapon_cooldowns[Weapon.PISTOL] == 200
    assert state.spawn_grace == 1000
    assert state.enemies[0].x == 2.2
    assert state.rockets[0].x == 3.5
    assert state.door_anim[5, 5]["progress"] == 0


def test_exit_transitions_preserve_inventory_and_clear_transient_state(
    sfx: Sfx, state: GameState
) -> None:
    start_level(state, 1)
    previous_world = state.world
    boss = state.boss
    assert boss is not None
    boss.take_damage(boss.hp)
    state.px, state.py = (v + 0.5 for v in state.world.exit_pos)
    state.owned[Weapon.SHOTGUN] = True
    state.weapon = Weapon.SHOTGUN
    state.ammo = [17, 6, 2, 0]
    state.weapon_cooldowns = [500] * len(WEAPONS)
    state.hp = 30
    state.kills = 7
    state.rockets = [Rocket(1.5, 1.5, 0)]
    state.door_anim[(5, 5)] = DoorAnim(phase="open", progress=1.0, timer=5000)
    tick(sfx, state)
    assert state.level == 2
    assert state.world is not previous_world
    assert (state.px, state.py) == state.world.player_spawn
    assert state.ammo == [17, 6, 2, 0]
    assert state.weapon == Weapon.SHOTGUN
    assert state.owned[Weapon.SHOTGUN]
    assert state.hp == 100
    assert state.kills == 0
    assert state.rockets == []
    assert state.door_anim == {}
    assert state.weapon_cooldowns == [0] * len(WEAPONS)
    assert not state.exit_open


def test_death_at_exit_does_not_load_another_level(sfx: Sfx, state: GameState) -> None:
    boss = Boss(10.5, 10.5)
    boss.take_damage(boss.hp)
    state.boss = boss
    state.px, state.py = (v + 0.5 for v in state.world.exit_pos)
    state.hp = 0
    tick(sfx, state)
    assert state.game_over
    assert state.level == 1


def test_restart_key_rebuilds_level_and_resets_inventory(sfx: Sfx, state: GameState) -> None:
    reset_game(state)
    original_maze = [row.copy() for row in state.world.maze]
    state.game_over = True
    state.hp = -5
    state.ammo = [0, 0, 0, 0]
    state.owned = [True] * 5
    state.weapon = Weapon.ROCKETS
    state.weapon_cooldowns = [500] * len(WEAPONS)
    state.rockets = [Rocket(3.5, 1.5, 0)]
    restart = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, scancode=pygame.KSCAN_R)
    assert send_events(state, sfx, set(), restart)
    assert not state.game_over
    assert state.hp == 100
    assert state.ammo == list(INITIAL_AMMO)
    assert state.owned == [weapon.initially_owned for weapon in WEAPONS]
    assert state.weapon == Weapon.PISTOL
    assert state.weapon_cooldowns == [0] * len(WEAPONS)
    assert state.rockets == []
    assert state.world.maze == original_maze


def test_restart_drops_movement_keys_from_the_previous_life(sfx: Sfx, state: GameState) -> None:
    state.game_over = True
    pressed = {pygame.KSCAN_W, pygame.KSCAN_A}
    restart = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, scancode=pygame.KSCAN_R)
    send_events(state, sfx, pressed, restart)
    assert not state.game_over
    assert pressed == set()
    assert not update_game(state, 16, Keys(), pressed, sfx)
    assert (state.px, state.py) == state.world.player_spawn
