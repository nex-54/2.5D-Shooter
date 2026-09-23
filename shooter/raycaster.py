"""
Raycasting engine — casts rays from the player's position to build the wall column list.
"""

from __future__ import annotations

import math
from typing import Callable
from shooter.constants import FOV, HALF_FOV, NUM_RAYS, MAX_DEPTH
from shooter.map import tile_at, is_solid, BARRIER_TILE, DOOR_TILE
from shooter.types import BgHit, DoorAnimMap, WallColumn

__all__ = ["BgHit", "WallColumn", "cast_rays"]


def _cast_single(px: float, py: float, sin_a: float, cos_a: float,
                 stop_func: Callable[[float, float], bool]
                 ) -> tuple[float, float, int, int, tuple[int, int]]:
    """Cast one ray, stopping at tiles where stop_func returns True."""
    # horizontal intersections
    y_hor: float
    dy: int
    if sin_a > 0:
        y_hor = int(py) + 1
        dy = 1
    elif sin_a < 0:
        y_hor = int(py) - 1e-6
        dy = -1
    else:
        y_hor = py
        dy = 0

    depth_h: float = MAX_DEPTH
    hit_hx: float = 0.0
    tile_h = 1
    tile_h_coords = (-1, -1)
    if dy != 0:
        for _ in range(MAX_DEPTH):
            depth_v_h = (y_hor - py) / sin_a if sin_a != 0 else MAX_DEPTH
            hx = px + depth_v_h * cos_a
            check_y = y_hor + (0 if dy > 0 else -0.001)
            if stop_func(hx, check_y):
                depth_h = depth_v_h
                hit_hx = hx
                tile_h = tile_at(hx, check_y)
                tile_h_coords = (int(hx), int(check_y))
                break
            y_hor += dy
        else:
            depth_h = MAX_DEPTH

    # vertical intersections
    x_ver: float
    dx: int
    if cos_a > 0:
        x_ver = int(px) + 1
        dx = 1
    elif cos_a < 0:
        x_ver = int(px) - 1e-6
        dx = -1
    else:
        x_ver = px
        dx = 0

    depth_v: float = MAX_DEPTH
    hit_vx: float = 0.0
    tile_v = 1
    tile_v_coords = (-1, -1)
    if dx != 0:
        for _ in range(MAX_DEPTH):
            depth_h_v = (x_ver - px) / cos_a if cos_a != 0 else MAX_DEPTH
            vy = py + depth_h_v * sin_a
            check_x = x_ver + (0 if dx > 0 else -0.001)
            if stop_func(check_x, vy):
                depth_v = depth_h_v
                hit_vx = vy
                tile_v = tile_at(check_x, vy)
                tile_v_coords = (int(check_x), int(vy))
                break
            x_ver += dx
        else:
            depth_v = MAX_DEPTH

    if depth_v < depth_h:
        return depth_v, hit_vx % 1, 0, tile_v, tile_v_coords
    else:
        return depth_h, hit_hx % 1, 1, tile_h, tile_h_coords


def _is_partial(tile: int, coords: tuple[int, int], door_anim: DoorAnimMap) -> bool:
    if tile == BARRIER_TILE:
        return True
    anim = door_anim.get(coords) if tile == DOOR_TILE else None
    return anim is not None and anim['progress'] > 0


def cast_rays(px: float, py: float, pa: float,
              door_anim: DoorAnimMap | None = None) -> list[WallColumn]:
    """Cast each column through partial obstacles until it reaches a full wall."""
    if door_anim is None:
        door_anim = {}
    walls: list[WallColumn] = []
    ray_angle = pa - HALF_FOV
    step = FOV / NUM_RAYS
    for _ in range(NUM_RAYS):
        sin_a = math.sin(ray_angle)
        cos_a = math.cos(ray_angle)

        depth, offset, side, hit_tile, tile_coords = _cast_single(px, py, sin_a, cos_a, is_solid)

        bg_hits: list[BgHit] = []
        if _is_partial(hit_tile, tile_coords, door_anim):
            passed = {tile_coords}

            def next_obstacle(x: float, y: float) -> bool:
                return (int(x), int(y)) not in passed and is_solid(x, y)

            # Keep other doors and barriers, rather than casting through all of
            # them: a closed door behind an opening door must still hide sprites.
            for _ in range(MAX_DEPTH):
                bg_depth, bg_offset, bg_side, bg_tile, bg_coords = _cast_single(
                    px, py, sin_a, cos_a, next_obstacle)
                corr = max(bg_depth * math.cos(ray_angle - pa), 0.0001)
                bg_hits.append(BgHit(corr, bg_offset, bg_side, bg_tile, bg_coords))
                if not _is_partial(bg_tile, bg_coords, door_anim):
                    break
                passed.add(bg_coords)

        # fish-eye correction
        depth *= math.cos(ray_angle - pa)
        depth = max(depth, 0.0001)
        walls.append(WallColumn(depth, offset, side, hit_tile, tuple(bg_hits), tile_coords))
        ray_angle += step
    return walls
