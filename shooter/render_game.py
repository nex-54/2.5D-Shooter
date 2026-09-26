"""Gameplay frame composition and game-over, level, and pause overlays."""

from __future__ import annotations

import pygame
import pygame.freetype

from shooter.constants import BLACK, EYE_HEIGHT, HEIGHT, RED, WEAPONS, WHITE, WIDTH, YELLOW
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_sprites import Billboard, draw_world_sprites
from shooter.render_ui import draw_crosshair, draw_hud, draw_minimap
from shooter.render_world import draw_3d, draw_floor_ceiling
from shooter.state import GameState
from shooter.types import Textures
from shooter.weapons import draw_weapon


def draw_game_over(
    screen: pygame.Surface,
    state: GameState,
    font: pygame.freetype.Font,
    big_font: pygame.freetype.Font,
) -> None:
    """Render the game-over screen (death only — wins now advance levels)."""
    screen.fill(BLACK)
    msg, _ = big_font.render("GAME OVER", RED)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render(
        f"Reached Level {state.level}  -  Kills: {state.kills}/{state.total_enemies}  -  Press R to restart  -  ESC to quit",
        WHITE,
    )
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_level_banner(
    screen: pygame.Surface, state: GameState, big_font: pygame.freetype.Font
) -> None:
    """Draw a brief 'LEVEL N' banner that fades out over ~1.2s."""
    if state.level_banner_timer <= 0:
        return
    # Fade alpha based on remaining time (full for first 400 ms, then linear).
    total = 1200
    remaining = max(0, state.level_banner_timer)
    alpha = 255 if remaining > total - 400 else int(255 * remaining / (total - 400))
    overlay = pygame.Surface((WIDTH, 120), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, min(180, alpha)))
    screen.blit(overlay, (0, HEIGHT // 2 - 60))
    msg, _ = big_font.render(f"LEVEL {state.level}", YELLOW)
    msg.set_alpha(alpha)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - msg.get_height() // 2))


def draw_pause_overlay(
    screen: pygame.Surface, font: pygame.freetype.Font, big_font: pygame.freetype.Font
) -> None:
    """Dim the frozen frame and show how to resume or quit."""
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 150))
    screen.blit(dim, (0, 0))
    msg, _ = big_font.render("PAUSED", YELLOW)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render("Esc or click to resume  -  Q to quit", WHITE)
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_frame(
    state: GameState,
    screen: pygame.Surface,
    font: pygame.freetype.Font,
    textures: Textures,
    z_buffer: DepthBuffer,
    player_moving: bool,
) -> None:
    """Draw one complete gameplay frame (3D view, sprites, HUD)."""
    eye = EYE_HEIGHT + state.jump_height
    walls = cast_rays(state.world, state.px, state.py, state.pa, state.door_anim)
    draw_floor_ceiling(state.world, screen, state.px, state.py, state.pa, textures, eye)
    draw_3d(screen, walls, z_buffer, font, textures, eye, door_anim=state.door_anim)
    billboards = [Billboard("START", *state.world.player_spawn, (20, 20, 80))]
    if state.boss is not None and state.boss.alive:
        billboards.append(Billboard("BOSS", state.boss.x, state.boss.y, (80, 20, 80)))
    draw_world_sprites(
        screen,
        state.px,
        state.py,
        state.pa,
        z_buffer,
        font,
        enemies=state.enemies,
        health_packs=state.health_packs,
        weapon_pickups=state.weapon_pickups,
        rockets=state.rockets,
        billboards=billboards,
        eye_height=eye,
    )
    draw_minimap(
        state.world,
        screen,
        state.px,
        state.py,
        state.pa,
        state.enemies,
        state.health_packs,
        state.weapon_pickups,
        state.rockets,
    )
    draw_crosshair(screen)
    draw_weapon(
        screen,
        state.shooting,
        state.shoot_timer,
        player_moving,
        state.game_time,
        state.weapon,
        state.gatling_spin,
    )
    draw_hud(
        screen,
        font,
        state.hp,
        state.ammo[WEAPONS[state.weapon].ammo_pool],
        state.kills,
        state.total_enemies,
        WEAPONS[state.weapon].name,
        state.level,
    )

    door_pos = state.world.find_door_in_front(state.px, state.py, state.pa)
    if door_pos is not None and door_pos not in state.door_anim:
        prompt_surf, prompt_rect = font.render("Press [E] to open", YELLOW, size=20)
        screen.blit(prompt_surf, (WIDTH // 2 - prompt_rect.width // 2, HEIGHT // 2 + 60))
