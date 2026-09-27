"""Pygame event handling, pause controls, and mouse capture."""

from __future__ import annotations

import pygame

from shooter.combat import fire_weapon
from shooter.constants import MAX_AMMO, MOUSE_SENSITIVITY, WEAPONS, Weapon
from shooter.state import GameState, reset_game
from shooter.types import DoorAnim, Sfx

_WEAPON_KEYS = {
    pygame.K_1: Weapon.PISTOL,
    pygame.K_2: Weapon.SHOTGUN,
    pygame.K_3: Weapon.GATLING,
    pygame.K_4: Weapon.ROCKETS,
    pygame.K_0: Weapon.NUKE,
}
_CHEAT_BUFFER_SIZE = 5


def handle_events(state: GameState, sfx: Sfx, pressed_scancodes: set[int]) -> bool:
    """Process all pygame events. Returns False if the game should quit."""
    # event.get() drains a whole batch before the main loop can recapture the mouse.
    ignore_mouse_motion = state.paused
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        elif event.type == pygame.KEYDOWN:
            pressed_scancodes.add(event.scancode)
            if event.key == pygame.K_ESCAPE:
                if state.game_over:
                    return False
                ignore_mouse_motion = True
                if state.paused:
                    state.paused = False
                else:
                    _pause(state, pressed_scancodes)
                continue
            if state.paused:
                if event.key == pygame.K_q:
                    return False
                continue
            if event.scancode == pygame.KSCAN_R and state.game_over:
                reset_game(state)
                pressed_scancodes.clear()
                continue
            if not state.game_over and state.hp > 0:
                _handle_cheat_key(state, event.key, sfx)
            if event.key in _WEAPON_KEYS and not state.game_over:
                new_weapon = _WEAPON_KEYS[event.key]
                if state.owned[new_weapon]:
                    state.switch_weapon(new_weapon)
            if event.scancode == pygame.KSCAN_E and not state.game_over:
                door_pos = state.world.find_door_in_front(state.px, state.py, state.pa)
                if door_pos and door_pos not in state.door_anim:
                    state.door_anim[door_pos] = DoorAnim(
                        phase="opening",
                        progress=0.0,
                        timer=0,
                    )
                    sfx["door_open"].play()
        elif event.type == pygame.KEYUP:
            pressed_scancodes.discard(event.scancode)
        elif event.type == pygame.WINDOWFOCUSLOST:
            # Key/button releases may happen outside our window, even after death.
            pressed_scancodes.clear()
            state.mouse_held = False
            if not state.game_over:
                _pause(state, pressed_scancodes)
                ignore_mouse_motion = True
        elif event.type == pygame.MOUSEMOTION:
            if not state.game_over and not state.paused and not ignore_mouse_motion:
                state.pa += event.rel[0] * MOUSE_SENSITIVITY
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and state.paused:
                state.paused = False  # the click that resumes doesn't fire
            elif event.button == 1 and not state.game_over:
                state.mouse_held = True
                fire_weapon(state, sfx)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                state.mouse_held = False
    return True


def _handle_cheat_key(state: GameState, key: int, sfx: Sfx) -> None:
    """Watch recent letter presses without swallowing normal gameplay controls."""
    # Pygame letter keycodes stay lowercase with Shift or Caps Lock held.
    if not pygame.K_a <= key <= pygame.K_z:
        return
    state.cheat_buffer = (state.cheat_buffer + chr(key))[-_CHEAT_BUFFER_SIZE:]
    if state.cheat_buffer == "iddqd":
        state.god_mode = not state.god_mode
    elif state.cheat_buffer == "idkfa":
        state.owned = [True] * len(WEAPONS)
        state.ammo = list(MAX_AMMO)
    else:
        return
    state.cheat_buffer = ""
    sfx["pickup"].play()


def _pause(state: GameState, pressed_scancodes: set[int]) -> None:
    """Freeze gameplay, dropping held input so nothing sticks on resume."""
    state.paused = True
    state.mouse_held = False
    state.cheat_buffer = ""
    pressed_scancodes.clear()


def capture_mouse(captured: bool) -> None:
    """Hide and grab the cursor for mouselook, or hand it back."""
    pygame.mouse.set_visible(not captured)
    pygame.event.set_grab(captured)
