"""Exercise typed cheat codes, damage immunity, and cheat lifecycle rules."""

import pygame
import pytest

from shooter.combat import update_enemies, update_rockets
from shooter.constants import INITIAL_AMMO, MAX_AMMO, WEAPONS, Weapon
from shooter.entities import Boss, Enemy, Rocket, Scout, Spider
from shooter.simulation import update_game
from shooter.state import GameState, reset_game, start_level
from tests.support import Keys, SoundMocks, send_events


def type_code(pressed: set[int], sounds: SoundMocks, state: GameState, code: str) -> bool:
    events: list[pygame.event.Event] = []
    for letter in code:
        key = ord(letter.lower())
        scancode = pygame.KSCAN_A + key - pygame.K_a
        events.append(
            pygame.event.Event(pygame.KEYDOWN, key=key, scancode=scancode, unicode=letter)
        )
        events.append(pygame.event.Event(pygame.KEYUP, key=key, scancode=scancode))
    return send_events(state, sounds.sfx, pressed, *events)


def test_iddqd_toggles_only_after_the_complete_code_across_frames(
    pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    assert not state.god_mode
    for letter in "IdDq":
        assert type_code(pressed, sounds, state, letter)
        assert not state.god_mode
    sounds["pickup"].play.assert_not_called()
    # Modifier presses must not interrupt a code typed with mixed casing.
    shift = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LSHIFT, scancode=0)
    send_events(state, sounds.sfx, pressed, shift)
    assert type_code(pressed, sounds, state, "D")
    assert state.god_mode
    sounds["pickup"].play.assert_called_once()
    type_code(pressed, sounds, state, "iddqd")
    assert not state.god_mode
    assert sounds["pickup"].play.call_count == 2


def test_mistyped_codes_do_nothing_and_a_fresh_code_still_works(
    pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    type_code(pressed, sounds, state, "wasd" * 100 + "iddqxddidkfxa")
    assert not state.god_mode
    assert state.ammo == list(INITIAL_AMMO)
    assert len(state.cheat_buffer) <= 5
    sounds["pickup"].play.assert_not_called()
    type_code(pressed, sounds, state, "iiddqd")
    assert state.god_mode


def test_idkfa_unlocks_and_refills_every_weapon_without_switching_or_resetting_cooldowns(
    pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    state.ammo = [0] * len(MAX_AMMO)
    state.weapon_cooldowns = [100] * len(WEAPONS)
    type_code(pressed, sounds, state, "IDKFA")
    assert state.owned == [True] * len(WEAPONS)
    assert state.ammo == list(MAX_AMMO)
    assert state.weapon == Weapon.PISTOL
    assert state.weapon_cooldowns == [100] * len(WEAPONS)
    assert not state.god_mode
    sounds["pickup"].play.assert_called_once()
    state.ammo = [0] * len(MAX_AMMO)
    type_code(pressed, sounds, state, "idkfa")
    assert state.ammo == list(MAX_AMMO)
    assert sounds["pickup"].play.call_count == 2


@pytest.mark.parametrize("status", ("paused", "dead", "game_over"))
def test_cheats_are_disabled_while_paused_dead_or_game_over(
    status: str, pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    if status == "dead":
        state.hp = 0
    else:
        setattr(state, status, True)
    type_code(pressed, sounds, state, "iddqd")
    type_code(pressed, sounds, state, "idkfa")
    assert not state.god_mode
    assert state.owned == [weapon.initially_owned for weapon in WEAPONS]
    assert state.ammo == list(INITIAL_AMMO)
    sounds["pickup"].play.assert_not_called()


@pytest.mark.parametrize("escape", (True, False), ids=("escape", "focus-lost"))
def test_pausing_or_losing_focus_discards_a_partial_code(
    escape: bool, pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    pause = (
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=pygame.KSCAN_ESCAPE)
        if escape
        else pygame.event.Event(pygame.WINDOWFOCUSLOST)
    )
    type_code(pressed, sounds, state, "iddq")
    send_events(state, sounds.sfx, pressed, pause)
    send_events(state, sounds.sfx, pressed, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
    type_code(pressed, sounds, state, "d")
    assert not state.god_mode
    type_code(pressed, sounds, state, "iddqd")
    assert state.god_mode


@pytest.mark.parametrize(
    "enemy_type", (Enemy, Scout, Spider, Boss), ids=("enemy", "scout", "spider", "boss")
)
def test_god_mode_blocks_every_enemy_type_and_damage_resumes_when_disabled(
    enemy_type: type[Enemy], pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    state.hp = 1
    enemy = enemy_type(state.px + 0.5, state.py)
    state.enemies = [enemy]
    type_code(pressed, sounds, state, "iddqd")
    update_game(state, 16, Keys(), set(), sounds.sfx)
    assert state.hp == 1
    assert not state.game_over
    assert state.damage_cooldown == 0
    assert enemy.attacking
    type_code(pressed, sounds, state, "iddqd")
    update_enemies(state, 16, sounds.sfx)
    assert state.hp == 1 - enemy.damage


def test_god_mode_blocks_rocket_splash_without_protecting_enemies(
    pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    state.px, state.py = 4.5, 5.5
    state.hp = 1
    enemy = Enemy(5.5, 5.5)
    state.enemies = [enemy]
    rocket = Rocket(state.px, state.py, 0.0)
    state.rockets = [rocket]
    type_code(pressed, sounds, state, "iddqd")
    update_rockets(state, 100, sounds.sfx)
    assert rocket.exploded
    assert not enemy.alive
    assert state.kills == 1
    assert state.hp == 1
    assert state.damage_cooldown == 0
    sounds["explosion"].play.assert_called_once()


def test_level_changes_preserve_cheats_and_restart_clears_them(
    pressed: set[int], sounds: SoundMocks, state: GameState
) -> None:
    type_code(pressed, sounds, state, "iddqdidkfaiddq")
    start_level(state, 2)
    assert state.god_mode
    assert state.owned == [True] * len(WEAPONS)
    assert state.ammo == list(MAX_AMMO)
    type_code(pressed, sounds, state, "d")
    assert state.god_mode
    type_code(pressed, sounds, state, "iddq")
    reset_game(state)
    assert not state.god_mode
    assert state.owned == [weapon.initially_owned for weapon in WEAPONS]
    assert state.ammo == list(INITIAL_AMMO)
    type_code(pressed, sounds, state, "d")
    assert not state.god_mode
