"""Run real asset generation and the main loop using SDL's headless drivers."""

import os
import subprocess
import sys

import pytest


def run_script(script: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", script, *args],
        env={**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("entry_point", ("script", "module"))
def test_initialization_render_and_quit(entry_point: str) -> None:
    script = """
import runpy
import sys
import pygame
from unittest.mock import patch
from shooter import game
from shooter.constants import SAMPLE_RATE

frames = 0
draw_frame = game.draw_frame

def draw(*args, **kwargs):
    global frames
    assert pygame.mixer.get_init() == (SAMPLE_RATE, -16, 1), pygame.mixer.get_init()
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
    run_script(script, entry_point)


def test_startup_and_loop_failures_release_pygame_resources() -> None:
    run_script("""
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
