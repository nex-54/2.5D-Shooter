"""
3D world rendering: textured floor, ceiling, and wall columns.

Consumes raycast output (from raycaster.cast_rays) and the textures dict
(from textures.generate_textures) and paints the perspective view.
"""

from __future__ import annotations

import math
from typing import Any

import pygame
from shooter.constants import (
    WIDTH, HEIGHT, HALF_FOV, NUM_RAYS, TEX_SIZE, EYE_HEIGHT,
    WHITE, CEIL, FLOOR,
)
from shooter.map import (
    EXIT_TILE, BARRIER_TILE, BARRIER_HEIGHT, DOOR_TILE, DOOR_POSITIONS, MAP_W, MAP_H,
)
from shooter.occlusion import DepthBuffer
from shooter.types import BgHit, DoorAnimMap, Textures, WallColumn
import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Floor / Ceiling
# ---------------------------------------------------------------------------
def draw_floor_ceiling(screen: pygame.Surface, px: float, py: float, pa: float,
                       textures: Textures | None,
                       eye_height: float = EYE_HEIGHT) -> None:
    """Render textured floor and ceiling as seen from eye_height."""
    horizon = HEIGHT // 2

    if textures is not None:
        _draw_fc_numpy(screen, px, py, pa, eye_height, textures)
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
        # tan() of each column's angle from the view direction, matching the
        # column angles in raycaster.cast_rays.
        self.plane_offsets: NDArray[np.float64] = np.tan(
            np.linspace(-HALF_FOV, HALF_FOV, WIDTH, endpoint=False))
        self.rows: NDArray[np.float64] = np.arange(HEIGHT, dtype=np.float64)
        self.dists: NDArray[np.float64] = np.empty(HEIGHT, dtype=np.float64)
        self.shades: NDArray[np.float64] = np.empty(HEIGHT, dtype=np.float64)
        self.eye_height: float | None = None
        self.door_positions: tuple[tuple[int, int], ...] | None = None
        self.door_grid: NDArray[np.bool_] = np.zeros(MAP_W * MAP_H, dtype=np.bool_)

    def draw(self, screen: pygame.Surface, px: float, py: float, pa: float,
             eye_height: float) -> None:
        horizon = HEIGHT // 2
        if eye_height != self.eye_height:
            np.subtract(self.rows, horizon, out=self.dists)
            np.abs(self.dists, out=self.dists)
            # The horizon itself is skipped; avoid dividing by zero there.
            np.maximum(self.dists, 1, out=self.dists)
            # Rows above the horizon meet the ceiling and rows below meet the
            # floor, at the distance where that plane's gap to the eye projects.
            above, below = self.dists[:horizon], self.dists[horizon:]
            np.divide(HEIGHT * (1.0 - eye_height), above, out=above)
            np.divide(HEIGHT * eye_height, below, out=below)
            np.multiply(self.dists, 0.07, out=self.shades)
            np.subtract(1.0, self.shades, out=self.shades)
            np.clip(self.shades, 0.12, 1.0, out=self.shades)
            self.eye_height = eye_height

        # Level generation mutates DOOR_POSITIONS in place, so compare its values.
        doors = tuple(DOOR_POSITIONS)
        if doors != self.door_positions:
            self.door_grid.fill(False)
            for c, r in doors:
                self.door_grid[c * MAP_H + r] = True
            self.door_positions = doors

        # Row distances are perpendicular to the view direction, like wall
        # depths, so rays run to a flat camera plane instead of unit length.
        # Unit rays bend floor lines into arcs and misalign them with walls.
        cos_a, sin_a = math.cos(pa), math.sin(pa)
        ray_x = cos_a - sin_a * self.plane_offsets
        ray_y = sin_a + cos_a * self.plane_offsets
        # Row-major traversal matches the surface layout and improves locality.
        pix = pygame.surfarray.pixels3d(screen).transpose(1, 0, 2)
        try:
            for start, end, ceiling in ((0, horizon, True), (horizon + 1, HEIGHT, False)):
                self._draw_rows(pix, start, end, ceiling, px, py, ray_x, ray_y)
        finally:
            del pix

    def _draw_rows(self, pix: NDArray[np.uint8], start: int, end: int,
                   ceiling: bool, px: float, py: float,
                   ray_x: NDArray[np.float64], ray_y: NDArray[np.float64]) -> None:
        for y in range(start, end, self._BATCH_ROWS):
            stop = min(y + self._BATCH_ROWS, end)
            count = stop - y
            wx, wy = self.world_x[:count], self.world_y[:count]
            scaled = self.scaled[:count]
            indices, scratch = self.indices[:count], self.scratch[:count]
            samples = self.samples[:count]
            np.multiply(self.dists[y:stop, None], ray_x[None, :], out=wx)
            np.add(wx, px, out=wx)
            np.multiply(self.dists[y:stop, None], ray_y[None, :], out=wy)
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
                   eye_height: float, tex: Textures) -> None:
    """Render at full resolution with a cache bounded to one texture set."""
    global _fc_renderer
    if _fc_renderer is None or _fc_renderer.textures is not tex:
        _fc_renderer = _FloorCeilingRenderer(tex)
    _fc_renderer.draw(screen, px, py, pa, eye_height)


# ---------------------------------------------------------------------------
# 3D Walls
# ---------------------------------------------------------------------------
def _draw_wall_slice(screen: pygame.Surface, x: int, width: int,
                     hit: WallColumn | BgHit, z_buffer: DepthBuffer,
                     eye_height: float, tex: Textures | None,
                     door_anim: DoorAnimMap | None) -> None:
    depth, offset, side, hit_tile = hit.depth, hit.offset, hit.side, hit.tile
    door_progress = 0.0
    if hit_tile == DOOR_TILE and door_anim is not None:
        anim = door_anim.get(hit.tile_coords)
        if anim is not None:
            door_progress = anim['progress']

    if hit_tile == EXIT_TILE:
        name = 'exit'
    elif hit_tile == BARRIER_TILE:
        name = 'barrier'
    elif hit_tile == DOOR_TILE:
        name = 'door'
    else:
        name = 'wall'
    cols = tex[name + '_cols'] if tex else None

    shade = max(30, 255 - int(depth * 18))
    if side == 1:
        shade = int(shade * 0.7)

    # Project world heights (floor 0, ceiling 1) from the eye to screen rows.
    # Barriers stand on the floor. Doors retract into the ceiling, so the slab
    # rises by its progress and the ceiling cuts off whatever passes above it.
    scale = HEIGHT / depth
    horizon = HEIGHT // 2
    slab_h = BARRIER_HEIGHT if hit_tile == BARRIER_TILE else 1.0
    tex_top = horizon + (eye_height - door_progress - slab_h) * scale
    bottom = round(horizon + (eye_height - door_progress) * scale)
    if door_progress > 0:
        y = round(horizon + (eye_height - 1.0) * scale)
    else:
        y = round(tex_top)

    if hit_tile == BARRIER_TILE or door_progress > 0:
        z_buffer.block_column(x, width, depth, y, bottom)
    else:
        # Full walls also separate the ceiling/floor beyond them. Their columns
        # stay opaque even when a tall sprite extends past the projected wall.
        z_buffer.block_column(x, width, depth)

    vis_top = max(0, y)
    vis_bot = min(HEIGHT, bottom)
    if vis_bot <= vis_top:
        return
    if cols:
        tx = int(offset * TEX_SIZE) % TEX_SIZE
        strip: pygame.Surface = cols[tx]
        slab_px = slab_h * scale
        if slab_px <= 2 * HEIGHT:
            strip_top, strip_bot = round(tex_top), bottom
        else:
            # Scale only the texels that reach the screen; a wall just in front
            # of the camera projects several screens tall.
            texel_h = slab_px / TEX_SIZE
            first = max(0, int((vis_top - tex_top) / texel_h))
            last = min(TEX_SIZE, math.ceil((vis_bot - tex_top) / texel_h))
            strip = strip.subsurface((0, first, 1, last - first))
            strip_top = round(tex_top + first * texel_h)
            strip_bot = round(tex_top + last * texel_h)
        scaled = pygame.transform.scale(strip, (width, max(strip_bot, vis_bot) - strip_top))
        scaled.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
        screen.blit(scaled, (x, vis_top),
                    area=(0, vis_top - strip_top, width, vis_bot - vis_top))
    else:
        color = (shade, shade // 2 + 40, shade // 3 + 20)
        pygame.draw.rect(screen, color, (x, vis_top, width, vis_bot - vis_top))


def draw_3d(screen: pygame.Surface, walls: list[WallColumn], z_buffer: DepthBuffer,
            font: Any, textures: Textures | None,
            eye_height: float = EYE_HEIGHT,
            door_anim: DoorAnimMap | None = None) -> None:
    """Render walls and record the depth of their visible vertical spans."""
    col_w = max(WIDTH // NUM_RAYS, 1)
    z_buffer.clear()
    exit_cols: list[tuple[int, float]] = []  # (screen x, depth) of each exit column
    for i, wall in enumerate(walls):
        x = i * col_w
        # Paint every background obstacle, then the foreground. The same spans
        # drive sprite clipping, including stacked barriers and animated doors.
        for hit in reversed(wall.bg_hits):
            _draw_wall_slice(screen, x, col_w + 1, hit, z_buffer,
                             eye_height, textures, door_anim)
        _draw_wall_slice(screen, x, col_w + 1, wall, z_buffer,
                         eye_height, textures, door_anim)

        if wall.tile == EXIT_TILE:
            exit_cols.append((x, wall.depth))

    if not exit_cols:
        return
    left, right = exit_cols[0][0], exit_cols[-1][0] + col_w
    sign_depth = exit_cols[len(exit_cols) // 2][1]
    sign_w = right - left
    font_size = max(8, min(int(sign_w * 0.5), 60))
    text_surf, text_rect = font.render("EXIT", WHITE, size=font_size)
    tx = left + sign_w // 2 - text_rect.width // 2
    # The sign hangs at standing eye height on the exit door.
    sign_y = HEIGHT // 2 + int((eye_height - EYE_HEIGHT) * HEIGHT / sign_depth)
    ty = sign_y - text_rect.height // 2
    bg_rect = pygame.Rect(tx - 4, ty - 2, text_rect.width + 8, text_rect.height + 4)
    pygame.draw.rect(screen, (20, 80, 20), bg_rect)
    pygame.draw.rect(screen, WHITE, bg_rect, 1)
    screen.blit(text_surf, (tx, ty))
