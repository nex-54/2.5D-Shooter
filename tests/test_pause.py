"""Verify that Esc and losing focus pause the game instead of quitting it."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pygame

from shooter.constants import WEAPONS
from shooter.input import handle_events
from shooter.state import GameState


def key(key_code: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key_code, scancode=scancode)


class PauseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()
        self.pressed: set[int] = set()

    def send(self, *events: pygame.event.Event) -> bool:
        """Deliver events through handle_events; returns False when the game quits."""
        with patch("shooter.input.pygame.event.get", return_value=list(events)):
            return handle_events(self.state, MagicMock(), self.pressed)

    def test_escape_toggles_pause_instead_of_quitting(self) -> None:
        self.assertTrue(self.send(key(pygame.K_ESCAPE)))
        self.assertTrue(self.state.paused)
        self.assertTrue(self.send(key(pygame.K_ESCAPE)))
        self.assertFalse(self.state.paused)

    def test_paused_game_ignores_aim_weapon_keys_and_the_resuming_click(self) -> None:
        self.state.owned[1] = True
        self.state.ammo[WEAPONS[1].ammo_pool] = 10
        self.send(key(pygame.K_ESCAPE))
        ammo = list(self.state.ammo)
        self.send(pygame.event.Event(pygame.MOUSEMOTION, rel=(200, 0)), key(pygame.K_2))
        self.assertEqual(self.state.pa, 0.0)
        self.assertEqual(self.state.weapon, 0)

        self.send(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
        self.assertFalse(self.state.paused)
        self.assertFalse(self.state.mouse_held)
        self.assertEqual(self.state.ammo, ammo)

    def test_q_quits_only_while_paused(self) -> None:
        self.assertTrue(self.send(key(pygame.K_q)))
        self.send(key(pygame.K_ESCAPE))
        self.assertFalse(self.send(key(pygame.K_q)))

    def test_losing_focus_pauses_and_drops_held_input(self) -> None:
        self.pressed.add(pygame.KSCAN_W)
        self.state.mouse_held = True
        self.send(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertTrue(self.state.paused)
        self.assertFalse(self.state.mouse_held)
        self.assertEqual(self.pressed, set())

    def test_game_over_screen_still_quits_on_escape(self) -> None:
        self.state.game_over = True
        self.send(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertFalse(self.state.paused)
        self.assertFalse(self.send(key(pygame.K_ESCAPE)))


if __name__ == "__main__":
    unittest.main()
