"""Weapon definitions drive firing, shared ammo, pickups, and kill accounting."""

from unittest.mock import patch

import pygame
import pytest

from shooter.combat import update_combat
from shooter.constants import EMPTY_CLICK_DELAY, MAX_AMMO, WEAPONS, Weapon
from shooter.entities import Boss, Enemy, WeaponPickup
from shooter.input import handle_events
from shooter.map import LevelState
from shooter.simulation import update_pickups
from shooter.state import GameState
from tests.support import SoundMocks, open_world


@pytest.fixture
def state(world: LevelState) -> GameState:
    state = GameState(seed=0)
    state.world = world
    state.px, state.py = 2.5, 5.5
    return state


def fire(sounds: SoundMocks, state: GameState) -> None:
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    with patch("shooter.input.pygame.event.get", return_value=[event]):
        handle_events(state, sounds.sfx, set())
    if state.weapon == Weapon.GATLING:
        update_combat(state, 0, sounds.sfx)


@pytest.mark.parametrize(
    "weapon_id", tuple(Weapon), ids=tuple(weapon.name.lower() for weapon in Weapon)
)
def test_every_weapon_consumes_one_round_and_respects_cooldown(
    weapon_id: Weapon, sounds: SoundMocks, state: GameState
) -> None:
    weapon = WEAPONS[weapon_id]
    state.weapon = weapon_id
    state.owned[weapon_id] = True
    state.ammo = [3, 3, 3, 3]
    state.shoot_timer = 0
    fire(sounds, state)
    expected = [3, 3, 3, 3]
    expected[weapon.ammo_pool] -= 1
    assert state.ammo == expected
    assert state.shoot_timer == weapon.fire_interval_ms
    fire(sounds, state)
    assert state.ammo == expected


@pytest.mark.parametrize(
    "weapon_id", tuple(Weapon), ids=tuple(weapon.name.lower() for weapon in Weapon)
)
def test_unowned_and_empty_weapons_cannot_deal_damage(
    weapon_id: Weapon, sounds: SoundMocks, state: GameState
) -> None:
    target = Enemy(3.5, 5.5)
    state.enemies = [target]
    state.weapon = weapon_id
    state.owned[weapon_id] = False
    state.shoot_timer = 0
    state.ammo = [3, 3, 3, 3]
    fire(sounds, state)
    assert state.ammo == [3, 3, 3, 3]
    state.owned[weapon_id] = True
    state.ammo = [0, 0, 0, 0]
    fire(sounds, state)
    assert state.ammo == [0, 0, 0, 0]
    assert target.hp == target.max_hp
    assert state.kills == 0
    assert state.rockets == []


def test_pistol_and_gatling_share_ammo_when_switching(sounds: SoundMocks, state: GameState) -> None:
    state.ammo[0] = 10
    fire(sounds, state)
    state.owned[Weapon.GATLING] = True
    switch = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3, scancode=pygame.KSCAN_3)
    with patch("shooter.input.pygame.event.get", return_value=[switch]):
        handle_events(state, sounds.sfx, set())
    fire(sounds, state)
    assert state.ammo[0] == 8


def test_number_row_switches_weapons_on_any_keyboard_layout(
    sounds: SoundMocks, state: GameState
) -> None:
    # On AZERTY the unshifted "2" key reports "é" instead of K_2.
    state.owned[Weapon.SHOTGUN] = True
    switch = pygame.event.Event(pygame.KEYDOWN, key=ord("é"), scancode=pygame.KSCAN_2)
    with patch("shooter.input.pygame.event.get", return_value=[switch]):
        handle_events(state, sounds.sfx, set())
    assert state.weapon == Weapon.SHOTGUN


@pytest.mark.parametrize(
    "weapon_id", tuple(Weapon), ids=tuple(weapon.name.lower() for weapon in Weapon)
)
def test_switching_away_and_back_cannot_bypass_any_weapon_cooldown(
    weapon_id: Weapon, sounds: SoundMocks, state: GameState
) -> None:
    weapon = WEAPONS[weapon_id]
    state.reset()
    state.world = open_world()
    state.owned = [True] * len(WEAPONS)
    state.ammo = [10, 10, 10, 10]
    state.switch_weapon(weapon_id)
    fire(sounds, state)
    ammo = state.ammo.copy()
    other = Weapon.NUKE if weapon_id != Weapon.NUKE else Weapon.PISTOL
    state.switch_weapon(other)
    update_combat(state, weapon.fire_interval_ms - 1, sounds.sfx)
    state.switch_weapon(weapon_id)
    fire(sounds, state)
    assert state.ammo == ammo
    update_combat(state, 1, sounds.sfx)
    fire(sounds, state)
    ammo[weapon.ammo_pool] -= 1
    assert state.ammo == ammo


def test_empty_click_cooldown_survives_switching(sounds: SoundMocks, state: GameState) -> None:
    state.ammo[0] = 0
    fire(sounds, state)
    state.switch_weapon(Weapon.NUKE)
    state.switch_weapon(Weapon.PISTOL)
    fire(sounds, state)
    sounds["empty"].play.assert_called_once()
    update_combat(state, EMPTY_CLICK_DELAY, sounds.sfx)
    fire(sounds, state)
    assert sounds["empty"].play.call_count == 2


@pytest.mark.parametrize(
    "schedule",
    (*((dt,) * (6000 // dt) for dt in (10, 16, 20, 30, 40, 50, 250)), (17, 43, 31, 9) * 60),
    ids=("10ms", "16ms", "20ms", "30ms", "40ms", "50ms", "250ms", "irregular"),
)
def test_gatling_fire_rate_is_independent_of_frame_intervals(
    schedule: tuple[int, ...], sounds: SoundMocks, state: GameState
) -> None:
    state.reset()
    state.world = open_world()
    state.owned[Weapon.GATLING] = True
    state.switch_weapon(Weapon.GATLING)
    state.ammo[0] = 999
    target = Enemy(state.px + 1, state.py)
    target.hp = 1000
    state.enemies = [target]
    fire(sounds, state)  # First shot at time zero, then six seconds of held fire.
    for dt in schedule:
        update_combat(state, dt, sounds.sfx)
    assert state.ammo[0] == 999 - 101
    assert target.hp == 1000 - 101


def test_idle_gatling_does_not_accumulate_catch_up_shots(
    sounds: SoundMocks, state: GameState
) -> None:
    state.owned[Weapon.GATLING] = True
    state.switch_weapon(Weapon.GATLING)
    fire(sounds, state)
    state.mouse_held = False
    update_combat(state, 6000, sounds.sfx)
    ammo = state.ammo[0]
    fire(sounds, state)
    assert state.ammo[0] == ammo - 1
    assert state.shoot_timer == WEAPONS[Weapon.GATLING].fire_interval_ms


def test_gatling_catch_up_stops_when_ammo_runs_out(sounds: SoundMocks, state: GameState) -> None:
    state.owned[Weapon.GATLING] = True
    state.switch_weapon(Weapon.GATLING)
    state.ammo[0] = 3
    fire(sounds, state)
    update_combat(state, 250, sounds.sfx)
    assert state.ammo[0] == 0
    assert sounds["gatling"].play.call_count == 3
    sounds["empty"].play.assert_called_once()


def test_gatling_pickup_unlocks_weapon_and_caps_shared_ammo(
    sounds: SoundMocks, state: GameState
) -> None:
    state.ammo[0] = MAX_AMMO[0] - 1
    pickup = WeaponPickup(state.px, state.py, Weapon.GATLING)
    state.weapon_pickups = [pickup]
    update_pickups(state, 16, sounds.sfx)
    assert state.owned[Weapon.GATLING]
    assert state.weapon == Weapon.GATLING
    assert state.ammo[0] == MAX_AMMO[0]
    assert not pickup.active


def test_shotgun_counts_a_kill_once_despite_multiple_pellets(
    sounds: SoundMocks, state: GameState
) -> None:
    target = Enemy(3.5, 5.5)
    state.enemies = [target]
    state.weapon = Weapon.SHOTGUN
    state.owned[Weapon.SHOTGUN] = True
    state.ammo[1] = 3
    fire(sounds, state)
    assert not target.alive
    assert state.kills == 1
    sounds["enemy_die"].play.assert_called_once()


def test_nuke_kills_regular_enemies_but_spares_boss(sounds: SoundMocks, state: GameState) -> None:
    enemy, boss = Enemy(4.5, 5.5), Boss(6.5, 5.5)
    state.enemies = [enemy, boss]
    state.weapon = Weapon.NUKE
    fire(sounds, state)
    assert not enemy.alive
    assert boss.hp == boss.max_hp
    assert state.kills == 1
    sounds["enemy_die"].play.assert_called_once()
    sounds["boss_die"].play.assert_not_called()
