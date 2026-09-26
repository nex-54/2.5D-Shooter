"""Run real asset generation and the main loop using SDL's headless drivers."""

import os
import subprocess
import sys
import unittest


class StartupTests(unittest.TestCase):
    def run_script(self, script: str, *args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-c", script, *args],
            env={**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_initialization_render_and_quit(self) -> None:
        script = """
import runpy
import sys
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
        if sys.argv[1] == 'script':
            runpy.run_path('shooter.py', run_name='__main__')
        else:
            runpy.run_module('shooter', run_name='__main__')
except SystemExit as exc:
    assert exc.code in (None, 0), exc.code
assert frames == 3, frames
assert not pygame.get_init()
"""
        for entry_point in ("script", "module"):
            with self.subTest(entry_point=entry_point):
                self.run_script(script, entry_point)

    def test_startup_and_loop_failures_release_pygame_resources(self) -> None:
        self.run_script("""
import pygame
from unittest.mock import patch
from shooter import app

for operation in ('init_sounds', 'run_game'):
    with patch.object(app, operation, side_effect=RuntimeError('injected failure')):
        try:
            app.main()
        except RuntimeError as exc:
            assert str(exc) == 'injected failure', exc
        else:
            raise AssertionError('application swallowed the failure')
    assert not pygame.get_init(), operation
    assert not pygame.display.get_init(), operation
    assert pygame.mixer.get_init() is None, operation
""")
