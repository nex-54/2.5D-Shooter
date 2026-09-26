"""
Procedural texture generation — creates all wall, floor, ceiling, and door textures.
"""

from __future__ import annotations

import random

import numpy as np
import pygame

from shooter.constants import TEX_SIZE
from shooter.types import Textures


def _add_noise(surf: pygame.Surface, amount: int = 15) -> None:
    """Add per-pixel noise to a surface for a rough look."""
    for y in range(surf.get_height()):
        for x in range(surf.get_width()):
            r, g, b, _ = surf.get_at((x, y))
            n = random.randint(-amount, amount)
            surf.set_at(
                (x, y), (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
            )


def generate_textures() -> Textures:
    """Procedurally generate all game textures (see shooter.types.Textures)."""
    tex = Textures()

    # --- Wall: brick pattern ---
    wall = pygame.Surface((TEX_SIZE, TEX_SIZE))
    wall.fill((150, 85, 55))
    mortar = (90, 80, 65)
    for y in range(0, TEX_SIZE, 16):
        pygame.draw.rect(wall, mortar, (0, y, TEX_SIZE, 2))
    for row in range(4):
        y0 = row * 16 + 2
        offset = 0 if row % 2 == 0 else 16
        for x in range(offset, TEX_SIZE + 16, 32):
            pygame.draw.rect(wall, mortar, (x % TEX_SIZE, y0, 2, 14))
    for row in range(4):
        for col in range(2 + row % 2):
            bx = col * 32 + (16 if row % 2 else 0)
            by = row * 16 + 2
            v = random.randint(-12, 12)
            for yy in range(by, min(by + 14, TEX_SIZE)):
                for xx in range(bx, min(bx + 30, TEX_SIZE)):
                    r, g, b, _ = wall.get_at((xx, yy))
                    wall.set_at(
                        (xx, yy),
                        (
                            max(0, min(255, r + v)),
                            max(0, min(255, g + v // 2)),
                            max(0, min(255, b + v // 3)),
                        ),
                    )
    _add_noise(wall, 10)
    tex.surfaces["wall"] = wall

    # --- Exit: green metal door ---
    exit_s = pygame.Surface((TEX_SIZE, TEX_SIZE))
    exit_s.fill((35, 110, 45))
    for x in [0, 21, 42]:
        pygame.draw.rect(exit_s, (25, 80, 32), (x, 0, 2, TEX_SIZE))
    for y in range(0, TEX_SIZE, 8):
        pygame.draw.line(exit_s, (30, 95, 38), (0, y), (TEX_SIZE, y))
    for y in range(8, TEX_SIZE, 16):
        for x in range(10, TEX_SIZE, 20):
            pygame.draw.circle(exit_s, (55, 140, 65), (x, y), 2)
    _add_noise(exit_s, 8)
    tex.surfaces["exit"] = exit_s

    # --- Barrier: wooden planks ---
    barrier = pygame.Surface((TEX_SIZE, TEX_SIZE))
    barrier.fill((135, 115, 55))
    for y in range(0, TEX_SIZE, 8):
        pygame.draw.rect(barrier, (95, 80, 35), (0, y, TEX_SIZE, 1))
    for _ in range(40):
        gx = random.randint(0, TEX_SIZE - 1)
        gy = random.randint(0, TEX_SIZE - 1)
        gw = random.randint(6, 20)
        c = random.choice([(125, 105, 50), (145, 125, 60), (115, 95, 45)])
        pygame.draw.line(barrier, c, (gx, gy), (min(gx + gw, TEX_SIZE - 1), gy))
    _add_noise(barrier, 10)
    tex.surfaces["barrier"] = barrier

    # --- Floor: stone tiles ---
    floor = pygame.Surface((TEX_SIZE, TEX_SIZE))
    floor.fill((85, 75, 62))
    grout = (55, 48, 40)
    for p in [0, 32]:
        pygame.draw.rect(floor, grout, (0, p, TEX_SIZE, 2))
        pygame.draw.rect(floor, grout, (p, 0, 2, TEX_SIZE))
    for _ in range(8):
        sx = random.randint(4, TEX_SIZE - 5)
        sy = random.randint(4, TEX_SIZE - 5)
        sr = random.randint(2, 4)
        pygame.draw.circle(floor, (65, 58, 48), (sx, sy), sr)
    _add_noise(floor, 12)
    tex.surfaces["floor"] = floor

    # --- Ceiling: dark panels ---
    ceil = pygame.Surface((TEX_SIZE, TEX_SIZE))
    ceil.fill((58, 58, 78))
    border = (38, 38, 55)
    for p in [0, 32]:
        pygame.draw.rect(ceil, border, (0, p, TEX_SIZE, 1))
        pygame.draw.rect(ceil, border, (p, 0, 1, TEX_SIZE))
    pygame.draw.circle(ceil, (72, 72, 92), (16, 16), 5)
    pygame.draw.circle(ceil, (72, 72, 92), (48, 48), 5)
    _add_noise(ceil, 6)
    tex.surfaces["ceil"] = ceil

    # --- Door: wooden door with iron bands ---
    door = pygame.Surface((TEX_SIZE, TEX_SIZE))
    door.fill((100, 60, 30))
    for x in [0, 16, 32, 48]:
        pygame.draw.rect(door, (60, 35, 15), (x, 0, 2, TEX_SIZE))
    for y in [8, 28, 48]:
        pygame.draw.rect(door, (80, 80, 95), (0, y, TEX_SIZE, 4))
        for x in range(8, TEX_SIZE, 16):
            pygame.draw.circle(door, (105, 105, 115), (x, y + 2), 2)
    pygame.draw.circle(door, (95, 95, 105), (44, 34), 5, 2)
    pygame.draw.circle(door, (120, 120, 130), (44, 34), 2)
    for _ in range(30):
        gx = random.randint(2, TEX_SIZE - 3)
        gy = random.randint(0, TEX_SIZE - 1)
        glen = random.randint(4, 12)
        c = random.choice([(90, 50, 25), (110, 65, 35), (85, 45, 20)])
        pygame.draw.line(door, c, (gx, gy), (gx, min(gy + glen, TEX_SIZE - 1)))
    _add_noise(door, 8)
    tex.surfaces["door"] = door

    # --- Pre-extract 1px-wide column strips for each wall texture ---
    for name in ("wall", "exit", "barrier", "door"):
        cols: list[pygame.Surface] = []
        s = tex.surfaces[name]
        for x in range(TEX_SIZE):
            col = pygame.Surface((1, TEX_SIZE))
            col.blit(s, (0, 0), area=(x, 0, 1, TEX_SIZE))
            cols.append(col)
        tex.columns[name] = cols

    for name in ("floor", "ceil", "door"):
        tex.samples[name] = pygame.surfarray.array3d(tex.surfaces[name]).astype(np.float32)

    return tex


def generate_icon() -> pygame.Surface:
    """Generate the window icon: a crosshair + target framed by maze-wall corners."""
    size = 64
    icon = pygame.Surface((size, size), pygame.SRCALPHA)

    # Dark metallic backdrop with a subtle radial vignette
    cx, cy = size // 2, size // 2
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5
            t = min(1.0, d / (size * 0.7))
            base = 46 - int(22 * t)
            icon.set_at((x, y), (base, base, base + 4, 255))

    # Maze-wall corners (L-shapes in brick color — nods to the wall texture)
    brick = (150, 85, 55)
    brick_dk = (110, 60, 40)
    arm = 18
    thick = 5
    for corner in ((0, 0), (size, 0), (0, size), (size, size)):
        vx = 0 if corner[0] == 0 else size - thick
        vy = 0 if corner[1] == 0 else size - arm
        hx_ = 0 if corner[0] == 0 else size - arm
        hy_ = 0 if corner[1] == 0 else size - thick
        pygame.draw.rect(icon, brick, (vx, vy, thick, arm))
        pygame.draw.rect(icon, brick, (hx_, hy_, arm, thick))
        pygame.draw.rect(icon, brick_dk, (vx, vy, thick, 1))
        pygame.draw.rect(icon, brick_dk, (hx_, hy_, 1, thick))

    # Crosshair arms (white with dark outline for contrast)
    white = (235, 235, 235)
    shadow = (15, 15, 15)
    arm_len = 13
    arm_w = 4
    gap = 7
    for dx, dy, w, h in (
        (0, -gap - arm_len, arm_w, arm_len),  # top
        (0, gap, arm_w, arm_len),  # bottom
        (-gap - arm_len, 0, arm_len, arm_w),  # left
        (gap, 0, arm_len, arm_w),  # right
    ):
        rx = cx + dx - (w // 2 if w < arm_len else 0)
        ry = cy + dy - (h // 2 if h < arm_len else 0)
        pygame.draw.rect(icon, shadow, (rx - 1, ry - 1, w + 2, h + 2))
        pygame.draw.rect(icon, white, (rx, ry, w, h))

    # Target: red bullseye with highlight
    pygame.draw.circle(icon, shadow, (cx, cy), 8)
    pygame.draw.circle(icon, (200, 50, 50), (cx, cy), 7)
    pygame.draw.circle(icon, (245, 110, 110), (cx, cy), 7, 1)
    pygame.draw.circle(icon, (255, 220, 220), (cx - 2, cy - 2), 2)

    return icon
