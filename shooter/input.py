"""Pygame event handling, pause controls, and mouse capture."""

from __future__ import annotations

import pygame

from shooter.combat import fire_weapon
from shooter.constants import MOUSE_SENSITIVITY
from shooter.state import GameState, reset_game
from shooter.types import DoorAnim, Sfx


def handle_events(state: GameState, sfx: Sfx, pressed_scancodes: set[int]) -> bool:
    """Process all pygame events. Returns False if the game should quit."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        elif event.type == pygame.KEYDOWN:
            pressed_scancodes.add(event.scancode)
            if event.key == pygame.K_ESCAPE:
                # Esc pauses; the game-over screen has nothing to pause.
                if state.game_over:
                    return False
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
            # Reset the fire cooldown only on an actual switch — re-pressing the
            # equipped weapon's key must not zero shoot_timer (rate-of-fire bypass).
            weapon_keys = {
                pygame.K_1: 0,
                pygame.K_2: 1,
                pygame.K_3: 2,
                pygame.K_4: 3,
                pygame.K_0: 4,
            }
            if event.key in weapon_keys and not state.game_over:
                new_weapon = weapon_keys[event.key]
                if state.owned[new_weapon] and state.weapon != new_weapon:
                    state.weapon = new_weapon
                    state.shoot_timer = 0
                    state.shooting = False
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
            if not state.game_over:
                _pause(state, pressed_scancodes)
        elif event.type == pygame.MOUSEMOTION:
            if not state.game_over and not state.paused:
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


def _pause(state: GameState, pressed_scancodes: set[int]) -> None:
    """Freeze gameplay, dropping held input so nothing sticks on resume."""
    state.paused = True
    state.mouse_held = False
    pressed_scancodes.clear()


def capture_mouse(captured: bool) -> None:
    """Hide and grab the cursor for mouselook, or hand it back."""
    pygame.mouse.set_visible(not captured)
    pygame.event.set_grab(captured)
