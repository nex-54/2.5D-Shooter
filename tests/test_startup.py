"""Run real asset generation and the main loop using SDL's headless drivers."""

import os
import subprocess
import sys
import unittest


class StartupTests(unittest.TestCase):
    def test_initialization_render_and_quit(self) -> None:
        script = """
import pygame
from unittest.mock import patch
from shooter import game

frames = 0
draw_frame = game.draw_frame

def draw(*args, **kwargs):
    global frames
    draw_frame(*args, **kwargs)
    frames += 1
    if frames == 3:
        pygame.event.post(pygame.event.Event(pygame.QUIT))

try:
    with patch.object(game, 'draw_frame', draw):
        game.main()
except SystemExit as exc:
    assert exc.code in (None, 0), exc.code
assert frames == 3, frames
assert not pygame.get_init()
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
