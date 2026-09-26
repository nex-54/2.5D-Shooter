"""Main loop orchestration: process input, advance the simulation, and render frames."""

from __future__ import annotations

import pygame
import pygame.freetype

from shooter.constants import FPS
from shooter.input import capture_mouse, handle_events
from shooter.occlusion import DepthBuffer
from shooter.render_game import draw_frame, draw_game_over, draw_level_banner, draw_pause_overlay
from shooter.simulation import update_game
from shooter.state import GameState
from shooter.types import Sfx, Textures


def run_game(
    state: GameState,
    screen: pygame.Surface,
    font: pygame.freetype.Font,
    big_font: pygame.freetype.Font,
    sfx: Sfx,
    textures: Textures,
) -> None:
    """Run frames using initialized resources; the application owns their lifetime."""
    clock = pygame.time.Clock()
    z_buffer = DepthBuffer()
    pressed_scancodes: set[int] = set()

    running = True
    paused_frame: pygame.Surface | None = None
    while running:
        dt = min(clock.tick(FPS), 50)

        running = handle_events(state, sfx, pressed_scancodes)
        if not running:
            break

        if state.game_over:
            draw_game_over(screen, state, font, big_font)
            pygame.display.flip()
            continue

        if state.paused:
            # Hold the last frame under the overlay; free the mouse and mute.
            if paused_frame is None:
                paused_frame = screen.copy()
                draw_pause_overlay(paused_frame, font, big_font)
                capture_mouse(False)
                pygame.mixer.pause()
            screen.blit(paused_frame, (0, 0))
            pygame.display.flip()
            continue
        if paused_frame is not None:
            paused_frame = None
            capture_mouse(True)
            # Don't turn by however far the free cursor travelled.
            pygame.event.clear(pygame.MOUSEMOTION)
            pygame.mixer.unpause()

        keys = pygame.key.get_pressed()
        player_moving = update_game(state, dt, keys, pressed_scancodes, sfx)

        draw_frame(state, screen, font, textures, z_buffer, player_moving)
        draw_level_banner(screen, state, big_font)
        pygame.display.flip()
