"""
3D world rendering: textured floor, ceiling, and wall columns.

Consumes raycast output (from raycaster.cast_rays) and the textures dict
(from textures.generate_textures) and paints the perspective view.
"""

from __future__ import annotations

from typing import Any

import pygame
from shooter.constants import (
    WIDTH, HEIGHT, HALF_FOV, NUM_RAYS, TEX_SIZE,
    WHITE, CEIL, FLOOR,
)
from shooter.map import EXIT_TILE, BARRIER_TILE, DOOR_TILE, DOOR_POSITIONS, MAP_W, MAP_H
from shooter.types import DoorAnimMap, Textures, WallColumn
import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Floor / Ceiling
# ---------------------------------------------------------------------------
def draw_floor_ceiling(screen: pygame.Surface, px: float, py: float, pa: float,
                       textures: Textures | None,
                       horizon_offset: int = 0) -> None:
    """Render textured floor and ceiling."""
    horizon = HEIGHT // 2 + horizon_offset

    if textures is not None:
        _draw_fc_numpy(screen, px, py, pa, horizon, textures)
    else:
        pygame.draw.rect(screen, CEIL, (0, 0, WIDTH, horizon))
        pygame.draw.rect(screen, FLOOR, (0, horizon, WIDTH, HEIGHT - horizon))


class _FloorCeilingRenderer:
    """Reuse small row buffers instead of creating full-screen float arrays."""

    # 32 rows keep the working buffers near 2 MiB at the default resolution.
    _BATCH_ROWS = 32

    def __init__(self, textures: Textures) -> None:
        self.textures = textures
        shape = (self._BATCH_ROWS, WIDTH)
        self.world_x: NDArray[np.float64] = np.empty(shape, dtype=np.float64)
        self.world_y: NDArray[np.float64] = np.empty(shape, dtype=np.float64)
        self.scaled: NDArray[np.float64] = np.empty(shape, dtype=np.float64)
        self.indices: NDArray[np.intp] = np.empty(shape, dtype=np.intp)
        self.scratch: NDArray[np.intp] = np.empty(shape, dtype=np.intp)
        self.cells: NDArray[np.intp] = np.empty(shape, dtype=np.intp)
        self.door_mask: NDArray[np.bool_] = np.empty(shape, dtype=np.bool_)
        self.samples: NDArray[np.float32] = np.empty((*shape, 3), dtype=np.float32)

        # A single lookup selects floor, ceiling, or the darkened door frame.
        # Textures are generated once at startup and remain unchanged thereafter.
        self.atlas: NDArray[np.float32] = np.concatenate((
            textures['floor_np'].reshape(-1, 3),
            textures['ceil_np'].reshape(-1, 3),
            (textures['door_np'] * 0.65).reshape(-1, 3),
        ))
        self.rows: NDArray[np.float64] = np.arange(HEIGHT, dtype=np.float64)
        self.dists: NDArray[np.float64] = np.empty(HEIGHT, dtype=np.float64)
        self.shades: NDArray[np.float64] = np.empty(HEIGHT, dtype=np.float64)
        self.horizon: int | None = None
        self.door_positions: tuple[tuple[int, int], ...] | None = None
        self.door_grid: NDArray[np.bool_] = np.zeros(MAP_W * MAP_H, dtype=np.bool_)

    def draw(self, screen: pygame.Surface, px: float, py: float, pa: float,
             horizon: int) -> None:
        if horizon != self.horizon:
            np.subtract(self.rows, horizon, out=self.dists)
            np.abs(self.dists, out=self.dists)
            # The horizon itself is skipped; avoid dividing by zero there.
            np.maximum(self.dists, 1, out=self.dists)
            np.divide(HEIGHT * 0.5, self.dists, out=self.dists)
            np.multiply(self.dists, 0.07, out=self.shades)
            np.subtract(1.0, self.shades, out=self.shades)
            np.clip(self.shades, 0.12, 1.0, out=self.shades)
            self.horizon = horizon

        # Level generation mutates DOOR_POSITIONS in place, so compare its values.
        doors = tuple(DOOR_POSITIONS)
        if doors != self.door_positions:
            self.door_grid.fill(False)
            for c, r in doors:
                self.door_grid[c * MAP_H + r] = True
            self.door_positions = doors

        angles = np.linspace(pa - HALF_FOV, pa + HALF_FOV, WIDTH, endpoint=False)
        cos_r = np.cos(angles)
        sin_r = np.sin(angles)
        # Row-major traversal matches the surface layout and improves locality.
        pix = pygame.surfarray.pixels3d(screen).transpose(1, 0, 2)
        try:
            for start, end, ceiling in ((0, min(HEIGHT, horizon), True),
                                        (max(1, horizon + 1), HEIGHT, False)):
                self._draw_rows(pix, start, end, ceiling, px, py, cos_r, sin_r)
        finally:
            del pix

    def _draw_rows(self, pix: NDArray[np.uint8], start: int, end: int,
                   ceiling: bool, px: float, py: float,
                   cos_r: NDArray[np.float64], sin_r: NDArray[np.float64]) -> None:
        for y in range(start, end, self._BATCH_ROWS):
            stop = min(y + self._BATCH_ROWS, end)
            count = stop - y
            wx, wy = self.world_x[:count], self.world_y[:count]
            scaled = self.scaled[:count]
            indices, scratch = self.indices[:count], self.scratch[:count]
            samples = self.samples[:count]
            np.multiply(self.dists[y:stop, None], cos_r[None, :], out=wx)
            np.add(wx, px, out=wx)
            np.multiply(self.dists[y:stop, None], sin_r[None, :], out=wy)
            np.add(wy, py, out=wy)
            np.multiply(wx, TEX_SIZE, out=scaled)
            np.copyto(indices, scaled, casting='unsafe')
            np.multiply(wy, TEX_SIZE, out=scaled)
            np.copyto(scratch, scaled, casting='unsafe')
            # Masking is equivalent to modulo, including negative coordinates,
            # for power-of-two textures. Retain modulo for other texture sizes.
            if TEX_SIZE & (TEX_SIZE - 1) == 0:
                np.bitwise_and(indices, TEX_SIZE - 1, out=indices)
                np.bitwise_and(scratch, TEX_SIZE - 1, out=scratch)
            else:
                np.remainder(indices, TEX_SIZE, out=indices)
                np.remainder(scratch, TEX_SIZE, out=scratch)
            np.multiply(indices, TEX_SIZE, out=indices)
            np.add(indices, scratch, out=indices)

            if ceiling:
                cells, mask = self.cells[:count], self.door_mask[:count]
                np.copyto(cells, wx, casting='unsafe')
                np.clip(cells, 0, MAP_W - 1, out=cells)
                np.multiply(cells, MAP_H, out=cells)
                np.copyto(scratch, wy, casting='unsafe')
                np.clip(scratch, 0, MAP_H - 1, out=scratch)
                np.add(cells, scratch, out=cells)
                np.take(self.door_grid, cells, out=mask, mode='clip')
                np.add(indices, TEX_SIZE ** 2, out=indices)
                np.add(indices, TEX_SIZE ** 2, out=indices, where=mask)

            # mode='clip' avoids np.take's default temporary output buffer;
            # indices have already been wrapped into the atlas's valid range.
            np.take(self.atlas, indices, axis=0, out=samples, mode='clip')
            np.multiply(samples, self.shades[y:stop, None, None],
                        out=pix[y:stop], casting='unsafe')


_fc_renderer: _FloorCeilingRenderer | None = None


def _draw_fc_numpy(screen: pygame.Surface, px: float, py: float, pa: float,
                   horizon: int, tex: Textures) -> None:
    """Render at full resolution with a cache bounded to one texture set."""
    global _fc_renderer
    if _fc_renderer is None or _fc_renderer.textures is not tex:
        _fc_renderer = _FloorCeilingRenderer(tex)
    _fc_renderer.draw(screen, px, py, pa, horizon)


# ---------------------------------------------------------------------------
# 3D Walls
# ---------------------------------------------------------------------------
def draw_3d(screen: pygame.Surface, walls: list[WallColumn], z_buffer: list[float],
            font: Any, textures: Textures | None,
            horizon_offset: int = 0,
            door_anim: DoorAnimMap | None = None) -> None:
    """Render textured wall columns from raycast results.

    door_anim: optional dict of (col, row) -> {'progress': 0.0..1.0} for sliding doors.
    progress=0 is fully closed, progress=1 is fully open (door slid up into ceiling)."""
    horizon = HEIGHT // 2 + horizon_offset
    tex = textures

    col_w = max(WIDTH // NUM_RAYS, 1)
    sign_tiles: dict[int, list[int | None]] = {EXIT_TILE: [None, None]}
    for i, (depth, offset, side, hit_tile, bg_hit, tile_coords) in enumerate(walls):
        z_buffer[i] = depth
        x = i * col_w

        # Doors slide up on open/close — hide the top `progress` fraction of the column.
        door_progress = 0.0
        if hit_tile == DOOR_TILE and door_anim is not None:
            anim = door_anim.get(tile_coords)
            if anim is not None:
                door_progress = anim['progress']

        if hit_tile == EXIT_TILE:
            cols = tex['exit_cols'] if tex else None
        elif hit_tile == BARRIER_TILE:
            cols = tex['barrier_cols'] if tex else None
        elif hit_tile == DOOR_TILE:
            cols = tex['door_cols'] if tex else None
        else:
            cols = tex['wall_cols'] if tex else None

        # Draw the wall behind a barrier or an animating door so the top of the
        # doorway reveals the corridor beyond rather than the "infinite" ceiling.
        draw_bg = bg_hit is not None and (
            hit_tile == BARRIER_TILE or (hit_tile == DOOR_TILE and door_progress > 0)
        )
        if draw_bg and bg_hit is not None:
            bg_depth, bg_offset, bg_side, bg_tile = bg_hit
            bg_wall_h = min(int(HEIGHT / bg_depth), HEIGHT * 2)
            bg_shade = max(30, 255 - int(bg_depth * 18))
            if bg_side == 1:
                bg_shade = int(bg_shade * 0.7)
            bg_y = horizon - bg_wall_h // 2

            if tex:
                bg_cols = tex['exit_cols'] if bg_tile == EXIT_TILE else (tex['door_cols'] if bg_tile == DOOR_TILE else tex['wall_cols'])
                bg_tx = int(bg_offset * TEX_SIZE) % TEX_SIZE
                vis_top = max(0, bg_y)
                vis_bot = min(HEIGHT, bg_y + bg_wall_h)
                vis_h = vis_bot - vis_top
                if vis_h > 0:
                    scaled = pygame.transform.scale(bg_cols[bg_tx], (col_w + 1, bg_wall_h))
                    scaled.fill((bg_shade, bg_shade, bg_shade),
                                special_flags=pygame.BLEND_RGB_MULT)
                    screen.blit(scaled, (x, vis_top),
                                area=(0, vis_top - bg_y, col_w + 1, vis_h))
            else:
                bg_color = (bg_shade, bg_shade // 2 + 40, bg_shade // 3 + 20)
                pygame.draw.rect(screen, bg_color, (x, bg_y, col_w + 1, bg_wall_h))

        wall_h = min(int(HEIGHT / depth), HEIGHT * 2)
        shade = max(30, 255 - int(depth * 18))
        if side == 1:
            shade = int(shade * 0.7)

        if hit_tile == BARRIER_TILE:
            wall_h = wall_h // 3
            y = horizon + wall_h // 3
        else:
            y = horizon - wall_h // 2

        # Sliding door: the door retracts into the ceiling. Its top stays pinned
        # to the top of the doorway while the bottom rises, so the visible slice
        # is the TOP (1 - progress) of the doorway showing the BOTTOM of the door
        # texture. At progress=1 the door is entirely hidden in the ceiling.
        if door_progress > 0:
            visible_h = max(0, int((1.0 - door_progress) * wall_h))
            src_y_offset = wall_h - visible_h
        else:
            visible_h = wall_h
            src_y_offset = 0
        anim_bot = y + visible_h

        if cols and wall_h > 0:
            tx = int(offset * TEX_SIZE) % TEX_SIZE
            vis_top = max(0, y)
            vis_bot = min(HEIGHT, anim_bot)
            vis_h = vis_bot - vis_top
            if vis_h > 0:
                scaled = pygame.transform.scale(cols[tx], (col_w + 1, wall_h))
                scaled.fill((shade, shade, shade),
                            special_flags=pygame.BLEND_RGB_MULT)
                screen.blit(scaled, (x, vis_top),
                            area=(0, src_y_offset + (vis_top - y), col_w + 1, vis_h))
        else:
            color = (shade, shade // 2 + 40, shade // 3 + 20)
            pygame.draw.rect(screen, color, (x, y, col_w + 1, max(0, anim_bot - y)))

        if hit_tile in sign_tiles:
            if sign_tiles[hit_tile][0] is None:
                sign_tiles[hit_tile][0] = x
            sign_tiles[hit_tile][1] = x + col_w

    # draw signs on special tiles
    sign_config = {
        EXIT_TILE:  ("EXIT",  (20, 80, 20)),
    }
    for tile_type, (label, bg_color) in sign_config.items():
        left, right = sign_tiles[tile_type]
        if left is None or right is None:
            continue
        sign_w = right - left
        font_size = max(8, min(int(sign_w * 0.5), 60))
        text_surf, text_rect = font.render(label, WHITE, size=font_size)
        tx = left + sign_w // 2 - text_rect.width // 2
        ty = horizon - text_rect.height // 2
        bg_rect = pygame.Rect(tx - 4, ty - 2, text_rect.width + 8, text_rect.height + 4)
        pygame.draw.rect(screen, bg_color, bg_rect)
        pygame.draw.rect(screen, WHITE, bg_rect, 1)
        screen.blit(text_surf, (tx, ty))
