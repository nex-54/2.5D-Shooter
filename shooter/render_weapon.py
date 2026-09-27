"""First-person weapon composition, recoil, mechanical cycling, and muzzle light."""

from __future__ import annotations

import math
from functools import lru_cache

import pygame

from shooter.constants import HEIGHT, WEAPONS, WIDTH, Weapon
from shooter.weapon_models import MODEL_SIZE, MUZZLES, weapon_frame


def _shot_progress(weapon: Weapon, shooting: bool, shoot_timer: int) -> float:
    """Only a live shot drives animation; an empty-click cooldown does not."""
    if not shooting or shoot_timer <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - shoot_timer / WEAPONS[weapon].fire_interval_ms))


def _cycle(progress: float, start: float, peak: float, end: float) -> float:
    """A smooth out-and-back movement, with stationary endpoints."""
    if not start < progress < end:
        return 0.0
    phase = (progress - start) / (peak - start)
    if progress > peak:
        phase = (end - progress) / (end - peak)
    return phase * phase * (3.0 - 2.0 * phase)


@lru_cache(maxsize=4)
def _flash(weapon: Weapon) -> pygame.Surface:
    """Small cached, translucent flame pointing along the weapon's sight line."""
    size = 180
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    scale = {Weapon.PISTOL: 0.65, Weapon.SHOTGUN: 1.0, Weapon.GATLING: 0.8}.get(weapon, 1.2)
    for radius in range(int(65 * scale), 0, -2):
        alpha = int(42 * (1 - radius / (66 * scale)) ** 2)
        pygame.draw.circle(surf, (255, 159, 48, alpha), (cx, cy), radius)
    outline = [
        (-4, 12),
        (-21, -5),
        (-12, -13),
        (-40, -54),
        (-12, -32),
        (-7, -65),
        (5, -29),
        (19, -34),
        (11, -12),
        (24, 0),
        (7, 6),
    ]
    for shrink, color in (
        (1.0, (255, 150, 35, 180)),
        (0.68, (255, 217, 100, 235)),
        (0.36, (255, 251, 221, 255)),
    ):
        points = [(cx + int(x * scale * shrink), cy + int(y * scale * shrink)) for x, y in outline]
        pygame.draw.polygon(surf, color, points)
    return surf


def _draw_casing(screen: pygame.Surface, x: int, y: int, progress: float, shell: bool) -> None:
    """One deterministic casing arc per shot; never consume gameplay randomness."""
    start = 0.32 if shell else 0.08
    flight = (progress - start) / (0.50 if shell else 0.72)
    if not 0.0 < flight < 1.0:
        return
    cx = x + int(115 * flight)
    cy = y - int(85 * flight - 130 * flight * flight)
    angle = flight * 9
    dx, dy = int(math.cos(angle) * 7), int(math.sin(angle) * 7)
    pygame.draw.line(screen, (57, 37, 20), (cx - dx, cy - dy + 1), (cx + dx, cy + dy + 1), 6)
    pygame.draw.line(
        screen,
        (150, 57, 37) if shell else (190, 145, 65),
        (cx - dx, cy - dy),
        (cx + dx, cy + dy),
        4,
    )
    pygame.draw.circle(screen, (237, 199, 111), (cx + dx, cy + dy), 2)


def draw_weapon(
    screen: pygame.Surface,
    shooting: bool,
    shoot_timer: int,
    player_moving: bool,
    game_time: float,
    weapon: Weapon,
    gatling_spin: float,
) -> None:
    """Compose a cached procedural viewmodel without changing simulation state."""
    progress = _shot_progress(weapon, shooting, shoot_timer)
    kick = (1.0 - min(1.0, progress / 0.48)) ** 2
    strength = (18, 34, 5, 28, 0)[weapon]
    if player_moving:
        bob_x = math.sin(game_time * 7) * 4
        bob_y = abs(math.sin(game_time * 7)) * 4
    else:
        bob_x = math.sin(game_time * 1.5) * 1.5
        bob_y = math.sin(game_time * 2) * 1.5
    ox = WIDTH // 2 - 8 + int(bob_x + kick * strength * 0.4)
    oy = HEIGHT - MODEL_SIZE[1] + int(bob_y + kick * strength)

    pose = 0
    if weapon == Weapon.PISTOL:
        pose = round(_cycle(progress, 0.0, 0.12, 0.45) * 8)
    elif weapon == Weapon.SHOTGUN:
        pose = round(_cycle(progress, 0.2, 0.55, 0.9) * 12)
    elif weapon == Weapon.GATLING:
        # Six identical barrels repeat after one sixth of a revolution.
        pose = int((gatling_spin % (math.tau / 6)) / (math.tau / 6) * 16) % 16
    elif weapon == Weapon.NUKE:
        pose = int(progress < 0.65)

    flashing = progress < (0.20, 0.13, 0.5, 0.12, 0.0)[weapon]
    if flashing:
        mx, my = MUZZLES[weapon]
        flash = _flash(weapon)
        screen.blit(flash, (ox + mx - flash.get_width() // 2, oy + my - flash.get_height() // 2))

    model = weapon_frame(weapon, pose)
    screen.blit(model, (ox, oy))
    if flashing:
        # A faint warm reflection follows the actual silhouette, including the hands.
        reflected = model.copy()
        reflected.fill((70, 42, 12, 0), special_flags=pygame.BLEND_RGBA_ADD)
        reflected.set_alpha(100)
        screen.blit(reflected, (ox, oy))

    if weapon in (Weapon.PISTOL, Weapon.SHOTGUN, Weapon.GATLING):
        _draw_casing(screen, ox + 202, oy + 188, progress, weapon == Weapon.SHOTGUN)
