"""Shared type aliases for the shooter package.

Central place for the dict and tuple shapes that flow between modules
(raycaster → renderer → game loop), so signatures read as `Sfx` / `Textures` /
`WallColumn` rather than unnamed primitives.
"""

from __future__ import annotations

from typing import Any, Literal, NamedTuple, TypedDict

import pygame


# ---------------------------------------------------------------------------
# Sound effects
# ---------------------------------------------------------------------------
# Mapping of SFX name -> loaded pygame Sound, built by sound.init_sounds().
# Canonical keys (see sound.init_sounds):
#   weapons:  'pistol', 'shotgun', 'gatling', 'rocket_fire', 'explosion', 'empty'
#   player:   'step0', 'step1', 'pickup'
#   world:    'door_open', 'door_close', 'music'
#   enemies:  'enemy_hurt', 'enemy_die', 'enemy_attack',
#             'boss_roar', 'boss_die', 'spider_hiss', 'spider_die'
Sfx = dict[str, pygame.mixer.Sound]


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------
# Mapping of texture name -> pygame.Surface | list[Surface] | np.ndarray,
# built by textures.generate_textures(). Heterogeneous so typed as Any.
#
# Canonical keys:
#   Surfaces:        'wall', 'exit', 'barrier', 'door', 'floor', 'ceil'
#   Column strips:   '{name}_cols'  (list[pygame.Surface], one 1x64 column per texel)
#                    available for 'wall', 'exit', 'barrier', 'door'
#   Numpy samples:   '{name}_np'    (np.ndarray float32, H x W x 3)
#                    available for 'floor', 'ceil', 'door'
Textures = dict[str, Any]


# ---------------------------------------------------------------------------
# Door animation state
# ---------------------------------------------------------------------------
DoorPhase = Literal['opening', 'open', 'closing']


class DoorAnim(TypedDict):
    """Animation state for a single door tile.

    phase:    current stage in the open -> open -> close cycle.
    progress: 0.0 = fully closed, 1.0 = fully open (door slid into the ceiling).
              Advances during 'opening', holds at 1.0 during 'open', retracts
              during 'closing'.
    timer:    ms remaining in 'open' phase before auto-close is attempted.
    """
    phase: DoorPhase
    progress: float
    timer: int


# Keyed by (col, row) of the door tile in map.MAZE.
DoorAnimMap = dict[tuple[int, int], DoorAnim]


# ---------------------------------------------------------------------------
# Raycaster output
# ---------------------------------------------------------------------------
class BgHit(NamedTuple):
    """A ray hit behind a barrier or an animating door.

    depth:  fish-eye-corrected distance to the background wall.
    offset: 0..1 horizontal offset along the texture strip.
    side:   0 = vertical grid edge, 1 = horizontal grid edge (used for shading).
    tile:   the background tile id that was hit.
    tile_coords: (col, row), used to apply the background door's animation.
    """
    depth: float
    offset: float
    side: int
    tile: int
    tile_coords: tuple[int, int]


class WallColumn(NamedTuple):
    """One column of the raycast output (one per screen column).

    depth:       fish-eye-corrected distance to the hit wall.
    offset:      0..1 horizontal offset along the texture strip.
    side:        0 = vertical grid edge, 1 = horizontal grid edge.
    tile:        the tile id that was hit (wall / exit / barrier / door).
    bg_hits:     hits behind a barrier or animating door, nearest first, ending
                 at a full wall. Retains every partial obstacle along the ray.
    tile_coords: (col, row) of the hit tile, used to look up per-tile
                 animation state (e.g. door slide progress).
    """
    depth: float
    offset: float
    side: int
    tile: int
    bg_hits: tuple[BgHit, ...]
    tile_coords: tuple[int, int]
