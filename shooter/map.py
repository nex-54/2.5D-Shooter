"""
Maze layout, tile constants, and spatial query helpers.

Each GameState owns a LevelState. Generation returns a fresh map, and spatial
queries operate only on that instance.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tile values
# ---------------------------------------------------------------------------
FLOOR_TILE = 0
WALL_TILE = 1
EXIT_TILE = 2
BARRIER_TILE = 4
DOOR_TILE = 5

BARRIER_HEIGHT = 1 / 3  # in wall heights
BARRIER_CLEARANCE = 0.3  # jump height that carries the player over a barrier

# ---------------------------------------------------------------------------
# Map dimensions (constant across levels)
# ---------------------------------------------------------------------------
MAP_W = 20
MAP_H = 20

# The player starts here. The maze is carved from it, so it must be an odd cell.
START_TILE: tuple[int, int] = (1, 1)


def start_distance(col: int, row: int) -> int:
    """Manhattan distance in tiles from the player's start."""
    return abs(col - START_TILE[0]) + abs(row - START_TILE[1])


@dataclass
class LevelState:
    """One game's map and spawn locations; never shared between game sessions."""

    maze: list[list[int]] = field(
        default_factory=lambda: [[WALL_TILE] * MAP_W for _ in range(MAP_H)]
    )
    door_positions: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])
    exit_pos: tuple[int, int] = (MAP_W - 2, MAP_H - 1)
    player_spawn: tuple[float, float] = (START_TILE[0] + 0.5, START_TILE[1] + 0.5)
    boss_spawn: tuple[float, float] = (MAP_W - 4.5, MAP_H - 2.5)

    def tile_at(self, x: float, y: float) -> int:
        """Return the tile value at world position (x, y)."""
        mx, my = math.floor(x), math.floor(y)
        if 0 <= mx < MAP_W and 0 <= my < MAP_H:
            return self.maze[my][mx]
        return WALL_TILE

    def is_blocked(self, x: float, y: float, jump_h: float, exit_open: bool = False) -> bool:
        """Check if position is blocked considering jump height.

        The exit is a closed door until exit_open is set (the level boss is dead)."""
        t = self.tile_at(x, y)
        if t == WALL_TILE or t == DOOR_TILE:
            return True
        if t == EXIT_TILE and not exit_open:
            return True
        if t == BARRIER_TILE and jump_h < BARRIER_CLEARANCE:
            return True
        return False

    def is_obstacle(self, x: float, y: float) -> bool:
        """Check if a tile blocks movement (walls, barriers, and closed doors)."""
        t = self.tile_at(x, y)
        return t == WALL_TILE or t == BARRIER_TILE or t == DOOR_TILE

    def is_solid(self, x: float, y: float) -> bool:
        """Check if a tile blocks rays (walls, exit, barrier, and door tiles)."""
        t = self.tile_at(x, y)
        return t == WALL_TILE or t == EXIT_TILE or t == BARRIER_TILE or t == DOOR_TILE

    def blocks_sight(self, x: float, y: float) -> bool:
        """Check if a tile blocks sight and projectiles (walls and closed doors).
        Barriers sit below eye level, so shots, rockets, and enemies see over them."""
        t = self.tile_at(x, y)
        return t == WALL_TILE or t == DOOR_TILE

    def wall_hit_fraction(self, x1: float, y1: float, x2: float, y2: float) -> float | None:
        """Return the fraction along a segment where it first touches a wall/door.

        At grid corners, check both neighboring tiles so sight cannot pass through
        a diagonal wall seam. Barriers remain transparent at eye level.
        """
        cx, cy = math.floor(x1), math.floor(y1)
        end_x, end_y = math.floor(x2), math.floor(y2)
        if self.blocks_sight(cx, cy):
            return 0.0

        dx = x2 - x1
        dy = y2 - y1
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        while cx != end_x or cy != end_y:
            # Parametric distances to the next grid boundaries. Stop stepping each
            # axis once its destination cell is reached, including boundary endpoints.
            next_x = (cx + (1 if dx > 0 else 0) - x1) / dx if cx != end_x else math.inf
            next_y = (cy + (1 if dy > 0 else 0) - y1) / dy if cy != end_y else math.inf

            fraction = max(0.0, min(1.0, min(next_x, next_y)))
            if math.isclose(next_x, next_y, rel_tol=1e-12, abs_tol=1e-12):
                if self.blocks_sight(cx + step_x, cy) or self.blocks_sight(cx, cy + step_y):
                    return fraction
                cx += step_x
                cy += step_y
            elif next_x < next_y:
                cx += step_x
            else:
                cy += step_y
            if self.blocks_sight(cx, cy):
                return fraction
        return None

    def has_line_of_sight(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        """Whether the entire segment is clear, including corner contacts."""
        return self.wall_hit_fraction(x1, y1, x2, y2) is None

    def find_door_in_front(
        self, px: float, py: float, pa: float, max_range: float = 2.5
    ) -> tuple[int, int] | None:
        """Find the closest door tile the player is facing, within range."""
        cos_a = math.cos(pa)
        sin_a = math.sin(pa)
        for i in range(1, int(max_range * 8) + 1):
            d = i / 8.0
            cx = px + cos_a * d
            cy = py + sin_a * d
            t = self.tile_at(cx, cy)
            if t == DOOR_TILE:
                return (int(cx), int(cy))
            if t == WALL_TILE or t == EXIT_TILE or t == BARRIER_TILE:
                return None
        return None


# ---------------------------------------------------------------------------
# Procedural level generation
# ---------------------------------------------------------------------------
def _carve_maze(rng: random.Random, grid: list[list[int]]) -> None:
    """Recursive backtracker on odd cells. grid must start as all walls."""
    # Visit cells at odd indices: (1,1), (1,3), ..., (MAP_W-2, MAP_H-2)
    stack = [START_TILE]
    start_c, start_r = START_TILE
    grid[start_r][start_c] = FLOOR_TILE
    visited = {START_TILE}
    while stack:
        c, r = stack[-1]
        neighbours: list[tuple[int, int, int, int]] = []
        for dc, dr in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nc, nr = c + dc, r + dr
            if 1 <= nc < MAP_W - 1 and 1 <= nr < MAP_H - 1 and (nc, nr) not in visited:
                neighbours.append((nc, nr, dc, dr))
        if not neighbours:
            stack.pop()
            continue
        nc, nr, dc, dr = rng.choice(neighbours)
        # Knock down the wall between (c, r) and (nc, nr).
        grid[r + dr // 2][c + dc // 2] = FLOOR_TILE
        grid[nr][nc] = FLOOR_TILE
        visited.add((nc, nr))
        stack.append((nc, nr))


def _open_extra_walls(rng: random.Random, grid: list[list[int]], count: int) -> None:
    """Randomly remove interior walls to add loops/rooms."""
    candidates: list[tuple[int, int]] = []
    for r in range(1, MAP_H - 1):
        for c in range(1, MAP_W - 1):
            if grid[r][c] != WALL_TILE:
                continue
            # Needs at least two opposing open neighbours so removal creates a loop/passage.
            horiz = grid[r][c - 1] == FLOOR_TILE and grid[r][c + 1] == FLOOR_TILE
            vert = grid[r - 1][c] == FLOOR_TILE and grid[r + 1][c] == FLOOR_TILE
            if horiz or vert:
                candidates.append((c, r))
    rng.shuffle(candidates)
    for c, r in candidates[:count]:
        grid[r][c] = FLOOR_TILE


def _place_exit(rng: random.Random, grid: list[list[int]]) -> tuple[int, int]:
    """Carve an exit on the far edge from the player start. Returns (ex, ey).

    DFS only visits odd-indexed cells, so even rows/cols are walls. We pick an
    odd-indexed floor tile in the bottom-right quadrant and knock out a straight
    corridor from it to the nearest boundary, placing the EXIT_TILE there.
    """
    anchors: list[tuple[int, int]] = []
    for r in range(MAP_H // 2 | 1, MAP_H - 1, 2):
        for c in range(MAP_W // 2 | 1, MAP_W - 1, 2):
            if grid[r][c] == FLOOR_TILE:
                anchors.append((c, r))
    if not anchors:
        # Degenerate fallback: use (MAP_W-3, MAP_H-3) — an odd cell that DFS visits.
        ac, ar = MAP_W - 3, MAP_H - 3
        grid[ar][ac] = FLOOR_TILE
        anchors.append((ac, ar))
    ac, ar = rng.choice(anchors)

    # Choose whether to exit through the bottom or the right edge.
    if rng.random() < 0.5:
        for r in range(ar + 1, MAP_H - 1):
            grid[r][ac] = FLOOR_TILE
        ex, ey = ac, MAP_H - 1
    else:
        for c in range(ac + 1, MAP_W - 1):
            grid[ar][c] = FLOOR_TILE
        ex, ey = MAP_W - 1, ar
    grid[ey][ex] = EXIT_TILE
    return ex, ey


def _pick_boss_tile(rng: random.Random, grid: list[list[int]], ex: int, ey: int) -> tuple[int, int]:
    """Pick a floor tile within ~3 tiles of the exit for the boss spawn."""
    candidates: list[tuple[int, int]] = []
    for r in range(max(1, ey - 3), min(MAP_H - 1, ey + 4)):
        for c in range(max(1, ex - 3), min(MAP_W - 1, ex + 4)):
            if grid[r][c] == FLOOR_TILE and start_distance(c, r) > 5:
                candidates.append((c, r))
    if not candidates:
        # Fallback: any floor tile far from start.
        for r in range(MAP_H // 2, MAP_H - 1):
            for c in range(MAP_W // 2, MAP_W - 1):
                if grid[r][c] == FLOOR_TILE:
                    candidates.append((c, r))
    return rng.choice(candidates)


def _place_doors(rng: random.Random, grid: list[list[int]], count: int) -> list[tuple[int, int]]:
    """Place doors on corridor chokepoints. Returns list of (col, row)."""
    candidates: list[tuple[int, int]] = []
    for r in range(1, MAP_H - 1):
        for c in range(1, MAP_W - 1):
            if grid[r][c] != FLOOR_TILE:
                continue
            if (c, r) == START_TILE:
                continue
            left = grid[r][c - 1]
            right = grid[r][c + 1]
            up = grid[r - 1][c]
            down = grid[r + 1][c]
            # Corridor: walls on two opposite sides, floors on the other two.
            horizontal = up == down == WALL_TILE and left == right == FLOOR_TILE
            vertical = left == right == WALL_TILE and up == down == FLOOR_TILE
            if horizontal or vertical:
                candidates.append((c, r))
    rng.shuffle(candidates)
    placed: list[tuple[int, int]] = []
    for c, r in candidates:
        if len(placed) >= count:
            break
        # Avoid doors adjacent to each other.
        if any(abs(c - pc) + abs(r - pr) < 3 for pc, pr in placed):
            continue
        grid[r][c] = DOOR_TILE
        placed.append((c, r))
    return placed


def _place_barriers(
    rng: random.Random, grid: list[list[int]], count: int, ex: int, ey: int
) -> None:
    """Place low barriers on random floor tiles, away from start and exit."""
    candidates: list[tuple[int, int]] = []
    for r in range(2, MAP_H - 2):
        for c in range(2, MAP_W - 2):
            if grid[r][c] != FLOOR_TILE:
                continue
            if start_distance(c, r) < 4:
                continue
            if abs(c - ex) + abs(r - ey) < 3:
                continue
            candidates.append((c, r))
    rng.shuffle(candidates)
    for c, r in candidates[:count]:
        grid[r][c] = BARRIER_TILE


def generate_level(level: int, rng: random.Random) -> LevelState:
    """Build a fresh level using a caller-owned source of randomness."""
    grid = [[WALL_TILE] * MAP_W for _ in range(MAP_H)]
    _carve_maze(rng, grid)
    # Slightly more loops on later levels keeps things interesting.
    _open_extra_walls(rng, grid, 20 + min(level, 5))
    start_c, start_r = START_TILE
    grid[start_r][start_c] = FLOOR_TILE  # guarantee player start is floor

    ex, ey = _place_exit(rng, grid)
    doors = _place_doors(rng, grid, rng.randint(3, 5))
    _place_barriers(rng, grid, rng.randint(1, 3), ex, ey)
    # Pick the boss tile last so a door or barrier can't land on it and trap
    # the boss inside a solid tile (the exit only unlocks once the boss dies).
    bx, by = _pick_boss_tile(rng, grid, ex, ey)

    return LevelState(
        maze=grid, door_positions=doors, exit_pos=(ex, ey), boss_spawn=(bx + 0.5, by + 0.5)
    )
