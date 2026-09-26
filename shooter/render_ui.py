"""
2D overlay rendering: minimap, crosshair, and HUD (HP, ammo, kills, weapon, level).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pygame
import pygame.freetype

from shooter.constants import (
    BLUE,
    DARK,
    GRAY,
    GREEN,
    HEIGHT,
    MINIMAP_MARGIN,
    MINIMAP_SCALE,
    PLAYER_MAX_HP,
    RED,
    WEAPONS,
    WHITE,
    WIDTH,
    YELLOW,
)
from shooter.entities import Boss, Enemy, HealthPack, Rocket, WeaponPickup
from shooter.map import BARRIER_TILE, DOOR_TILE, MAP_H, MAP_W, START_TILE, WALL_TILE, LevelState


# ---------------------------------------------------------------------------
# Minimap
# ---------------------------------------------------------------------------
def draw_minimap(
    world: LevelState,
    screen: pygame.Surface,
    px: float,
    py: float,
    pa: float,
    enemies: list[Enemy],
    health_packs: list[HealthPack],
    weapon_pickups: list[WeaponPickup],
    rockets: Iterable[Rocket] = (),
) -> None:
    """Draw the top-right corner minimap."""
    mw = MAP_W * MINIMAP_SCALE
    mh = MAP_H * MINIMAP_SCALE
    mx = WIDTH - mw - MINIMAP_MARGIN
    my = MINIMAP_MARGIN

    bg_surf = pygame.Surface((mw, mh), pygame.SRCALPHA)
    bg_surf.fill((0, 0, 0, 160))
    screen.blit(bg_surf, (mx, my))

    for r in range(MAP_H):
        for c in range(MAP_W):
            if world.maze[r][c] == WALL_TILE:
                pygame.draw.rect(
                    screen,
                    GRAY,
                    (mx + c * MINIMAP_SCALE, my + r * MINIMAP_SCALE, MINIMAP_SCALE, MINIMAP_SCALE),
                )
            elif world.maze[r][c] == BARRIER_TILE:
                pygame.draw.rect(
                    screen,
                    (180, 140, 60),
                    (mx + c * MINIMAP_SCALE, my + r * MINIMAP_SCALE, MINIMAP_SCALE, MINIMAP_SCALE),
                )
            elif world.maze[r][c] == DOOR_TILE:
                pygame.draw.rect(
                    screen,
                    (140, 80, 40),
                    (mx + c * MINIMAP_SCALE, my + r * MINIMAP_SCALE, MINIMAP_SCALE, MINIMAP_SCALE),
                )

    pygame.draw.rect(
        screen,
        YELLOW,
        (
            mx + world.exit_pos[0] * MINIMAP_SCALE,
            my + world.exit_pos[1] * MINIMAP_SCALE,
            MINIMAP_SCALE,
            MINIMAP_SCALE,
        ),
    )
    start_c, start_r = START_TILE
    pygame.draw.rect(
        screen,
        BLUE,
        (mx + start_c * MINIMAP_SCALE, my + start_r * MINIMAP_SCALE, MINIMAP_SCALE, MINIMAP_SCALE),
    )

    for hp_pack in health_packs:
        if hp_pack.active:
            hx = int(mx + hp_pack.x * MINIMAP_SCALE)
            hy = int(my + hp_pack.y * MINIMAP_SCALE)
            pygame.draw.rect(screen, WHITE, (hx - 1, hy - 3, 2, 6))
            pygame.draw.rect(screen, WHITE, (hx - 3, hy - 1, 6, 2))

    for pack in weapon_pickups:
        if pack.active:
            ax = int(mx + pack.x * MINIMAP_SCALE)
            ay = int(my + pack.y * MINIMAP_SCALE)
            col = WEAPONS[pack.weapon_type].color
            # Simple gun silhouette: horizontal barrel + a small grip below.
            pygame.draw.rect(screen, col, (ax - 2, ay - 1, 5, 2))
            pygame.draw.rect(screen, col, (ax, ay + 1, 2, 2))

    for e in enemies:
        if e.alive:
            ex = int(mx + e.x * MINIMAP_SCALE)
            ey = int(my + e.y * MINIMAP_SCALE)
            pygame.draw.circle(screen, e.minimap_color, (ex, ey), e.minimap_radius)
            if isinstance(e, Boss):
                pygame.draw.circle(screen, RED, (ex, ey), e.minimap_radius, 1)

    for rk in rockets:
        if not rk.alive or rk.exploded:
            continue
        rx = int(mx + rk.x * MINIMAP_SCALE)
        ry = int(my + rk.y * MINIMAP_SCALE)
        tail_x = int(rx - math.cos(rk.angle) * 6)
        tail_y = int(ry - math.sin(rk.angle) * 6)
        pygame.draw.line(screen, (255, 160, 40), (tail_x, tail_y), (rx, ry), 2)
        pygame.draw.circle(screen, (255, 230, 120), (rx, ry), 2)

    for rk in rockets:
        if rk.alive and rk.exploded:
            ex = int(mx + rk.x * MINIMAP_SCALE)
            ey = int(my + rk.y * MINIMAP_SCALE)
            pygame.draw.circle(screen, (255, 120, 40), (ex, ey), 5)
            pygame.draw.circle(screen, (255, 220, 120), (ex, ey), 2)

    ppx = int(mx + px * MINIMAP_SCALE)
    ppy = int(my + py * MINIMAP_SCALE)
    pygame.draw.circle(screen, GREEN, (ppx, ppy), 3)
    lx = int(ppx + math.cos(pa) * 8)
    ly = int(ppy + math.sin(pa) * 8)
    pygame.draw.line(screen, GREEN, (ppx, ppy), (lx, ly), 2)

    pygame.draw.rect(screen, WHITE, (mx, my, mw, mh), 1)


# ---------------------------------------------------------------------------
# HUD elements
# ---------------------------------------------------------------------------
def draw_crosshair(screen: pygame.Surface) -> None:
    """Draw the center crosshair."""
    cx, cy = WIDTH // 2, HEIGHT // 2
    size = 12
    pygame.draw.line(screen, WHITE, (cx - size, cy), (cx + size, cy), 2)
    pygame.draw.line(screen, WHITE, (cx, cy - size), (cx, cy + size), 2)


def draw_hud(
    screen: pygame.Surface,
    font: pygame.freetype.Font,
    hp: int,
    ammo: int,
    kills: int,
    total: int,
    weapon_name: str,
    level: int,
) -> None:
    """Draw the bottom HUD bar (HP, ammo, kills, weapon name, level)."""
    pygame.draw.rect(screen, DARK, (20, HEIGHT - 50, 204, 24))
    bar_w = int(200 * max(hp, 0) / PLAYER_MAX_HP)
    bar_color = GREEN if hp > 40 else RED
    pygame.draw.rect(screen, bar_color, (22, HEIGHT - 48, bar_w, 20))
    hp_text, _ = font.render(f"HP: {max(0, hp)}", WHITE)
    screen.blit(hp_text, (24, HEIGHT - 48))

    ammo_text, _ = font.render(f"Ammo: {ammo}", WHITE)
    screen.blit(ammo_text, (240, HEIGHT - 48))

    kills_text, _ = font.render(f"Kills: {kills}/{total}", WHITE)
    screen.blit(kills_text, (420, HEIGHT - 48))

    level_text, _ = font.render(f"Level: {level}", YELLOW)
    screen.blit(level_text, (620, HEIGHT - 48))

    wep_text, _ = font.render(f"[{weapon_name}]", YELLOW)
    screen.blit(wep_text, (WIDTH - wep_text.get_width() - 20, HEIGHT - 48))
