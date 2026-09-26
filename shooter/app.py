"""Application startup and shutdown for both command-line entry points."""

from __future__ import annotations

import sys

import pygame
import pygame.freetype

from shooter.constants import HEIGHT, SAMPLE_RATE, WIDTH
from shooter.game import run_game
from shooter.input import capture_mouse
from shooter.sound import init_sounds
from shooter.state import GameState, reset_game
from shooter.textures import generate_icon, generate_textures


def main() -> None:
    """Initialize resources, run the game, and release Pygame on every exit path."""
    try:
        # pre_init must run before pygame.init() or the mixer latches onto defaults.
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
        pygame.init()
        pygame.mixer.init(SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.set_num_channels(16)
        pygame.display.set_icon(generate_icon())
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("2.5D Maze Shooter")
        font = pygame.freetype.SysFont("monospace", 20)
        big_font = pygame.freetype.SysFont("monospace", 48)
        sfx = init_sounds()
        textures = generate_textures()
        sfx["music"].set_volume(0.10)
        sfx["music"].play(loops=-1, fade_ms=800)

        state = GameState()
        reset_game(state)
        capture_mouse(True)
        run_game(state, screen, font, big_font, sfx, textures)
    finally:
        if pygame.display.get_init():
            capture_mouse(False)
        pygame.quit()
    sys.exit()
