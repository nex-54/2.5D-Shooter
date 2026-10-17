"""Check entry points, then run the real main loop using SDL's headless drivers."""

import os
import runpy
import subprocess
import sys
from unittest.mock import patch

import pytest


def run_script(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("entry_point", ("script", "module"))
def test_entry_points_call_main(entry_point: str) -> None:
    with patch("shooter.app.main") as main:
        if entry_point == "script":
            runpy.run_path("shooter.py", run_name="__main__")
        else:
            runpy.run_module("shooter", run_name="__main__")
    main.assert_called_once_with()


def test_initialization_render_and_quit() -> None:
    run_script("""
import runpy
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
        runpy.run_module('shooter', run_name='__main__')
except SystemExit as exc:
    assert exc.code in (None, 0), exc.code
assert frames == 3, frames
assert not pygame.get_init()
assert not pygame.display.get_init()
assert pygame.mixer.get_init() is None
""")


def test_startup_and_loop_failures_release_pygame_resources() -> None:
    run_script("""
import pygame
from unittest.mock import patch
from shooter import app
from shooter.types import Textures

def fail(*args):
    assert pygame.get_init()
    assert pygame.display.get_init()
    assert pygame.mixer.get_init() is not None
    raise RuntimeError('injected failure')

for operation in ('init_sounds', 'run_game'):
    # Keep real SDL resources and playback without regenerating procedural assets.
    with (
        patch.object(app, 'init_sounds', side_effect=lambda: {
            'music': pygame.mixer.Sound(buffer=bytes(2)),
        }),
        patch.object(app, 'generate_textures', return_value=Textures()),
        patch.object(app, operation, side_effect=fail),
    ):
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
