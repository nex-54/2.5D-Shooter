"""Verify that Esc and losing focus pause the game instead of quitting it."""

from __future__ import annotations

import pygame
import pytest

from shooter.constants import MOUSE_SENSITIVITY, WEAPONS, Weapon
from shooter.state import GameState
from shooter.types import Sfx
from tests.support import send_events


def key(key_code: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key_code, scancode=scancode)


def test_escape_toggles_pause_instead_of_quitting(
    pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    assert send_events(state, sfx, pressed, key(pygame.K_ESCAPE))
    assert state.paused
    assert send_events(state, sfx, pressed, key(pygame.K_ESCAPE))
    assert not state.paused


def test_paused_game_ignores_aim_weapon_keys_and_the_resuming_click(
    pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    state.owned[Weapon.SHOTGUN] = True
    state.ammo[WEAPONS[Weapon.SHOTGUN].ammo_pool] = 10
    send_events(state, sfx, pressed, key(pygame.K_ESCAPE))
    ammo = list(state.ammo)
    switch = key(pygame.K_2, pygame.KSCAN_2)
    send_events(state, sfx, pressed, pygame.event.Event(pygame.MOUSEMOTION, rel=(200, 0)), switch)
    assert state.pa == 0.0
    assert state.weapon == Weapon.PISTOL

    send_events(state, sfx, pressed, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
    assert not state.paused
    assert not state.mouse_held
    assert state.ammo == ammo
    send_events(state, sfx, pressed, switch)
    assert state.weapon == Weapon.SHOTGUN


def test_q_quits_only_while_paused(pressed: set[int], sfx: Sfx, state: GameState) -> None:
    assert send_events(state, sfx, pressed, key(pygame.K_q))
    send_events(state, sfx, pressed, key(pygame.K_ESCAPE))
    assert not send_events(state, sfx, pressed, key(pygame.K_q))


@pytest.mark.parametrize("escape", (True, False), ids=("escape", "click"))
def test_resume_discards_motion_from_the_entire_event_batch(
    escape: bool, pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    resume = (
        key(pygame.K_ESCAPE) if escape else pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    )
    state.paused = True
    state.pa = 0.0
    pressed.add(pygame.KSCAN_W)
    send_events(
        state,
        sfx,
        pressed,
        pygame.event.Event(pygame.MOUSEMOTION, rel=(100, 0)),
        resume,
        pygame.event.Event(pygame.MOUSEMOTION, rel=(200, 0)),
        pygame.event.Event(pygame.KEYUP, scancode=pygame.KSCAN_W),
    )
    assert not state.paused
    assert state.pa == 0.0
    assert pygame.KSCAN_W not in pressed
    send_events(state, sfx, pressed, pygame.event.Event(pygame.MOUSEMOTION, rel=(10, 0)))
    assert state.pa == pytest.approx(10 * MOUSE_SENSITIVITY, rel=0, abs=5e-8)


@pytest.mark.parametrize("escape", (True, False), ids=("escape", "focus-lost"))
def test_pause_and_resume_in_one_batch_also_discards_resume_motion(
    escape: bool, pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    pause = key(pygame.K_ESCAPE) if escape else pygame.event.Event(pygame.WINDOWFOCUSLOST)
    state.pa = 0.0
    send_events(
        state,
        sfx,
        pressed,
        pygame.event.Event(pygame.MOUSEMOTION, rel=(10, 0)),
        pause,
        pygame.event.Event(pygame.MOUSEMOTION, rel=(100, 0)),
        key(pygame.K_ESCAPE),
        pygame.event.Event(pygame.MOUSEMOTION, rel=(200, 0)),
    )
    assert not state.paused
    assert state.pa == pytest.approx(10 * MOUSE_SENSITIVITY, rel=0, abs=5e-8)


def test_losing_focus_pauses_and_drops_held_input(
    pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    pressed.add(pygame.KSCAN_W)
    state.mouse_held = True
    send_events(state, sfx, pressed, pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert state.paused
    assert not state.mouse_held
    assert pressed == set()


def test_game_over_screen_still_quits_on_escape(
    pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    state.game_over = True
    send_events(state, sfx, pressed, pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert not state.paused
    assert not send_events(state, sfx, pressed, key(pygame.K_ESCAPE))


def test_losing_focus_on_game_over_drops_held_input(
    pressed: set[int], sfx: Sfx, state: GameState
) -> None:
    state.game_over = True
    state.mouse_held = True
    pressed.add(pygame.KSCAN_W)
    send_events(state, sfx, pressed, pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert not state.paused
    assert not state.mouse_held
    assert pressed == set()
