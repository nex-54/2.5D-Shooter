"""
Maze layout, tile constants, and spatial query helpers.

The MAZE grid is mutable — doors are opened/closed by setting tiles to 0 / DOOR_TILE,
and the entire grid is rewritten in place by generate_level() between levels.
"""

from __future__ import annotations

import math
import random

# ---------------------------------------------------------------------------
# Special tile values
# ---------------------------------------------------------------------------
EXIT_TILE = 2
BARRIER_TILE = 4
DOOR_TILE = 5

BARRIER_HEIGHT = 1 / 3  # in wall heights; jumping 0.3 high clears a barrier

# ---------------------------------------------------------------------------
# Map dimensions (constant across levels)
# ---------------------------------------------------------------------------
MAP_W = 20
MAP_H = 20

# ---------------------------------------------------------------------------
# Mutable level state — populated by generate_level().
# Other modules reference these by identity (MAZE is a list, mutated in place),
# so import them via the module (e.g. `from shooter import map as gmap`)
# when reading scalars (EXIT_X, EXIT_Y) so rebindings are visible.
# ---------------------------------------------------------------------------
MAZE: list[list[int]] = [[1] * MAP_W for _ in range(MAP_H)]
DOOR_POSITIONS: list[tuple[int, int]] = []  # [(col, row), ...] — original door tiles for restoration
EXIT_X, EXIT_Y = MAP_W - 2, MAP_H - 1
PLAYER_SPAWN = (1.5, 1.5)
BOSS_SPAWN = (MAP_W - 4.5, MAP_H - 2.5)


# ---------------------------------------------------------------------------
# Tile queries
# ---------------------------------------------------------------------------
def tile_at(x: float, y: float) -> int:
    """Return the tile value at world position (x, y)."""
    mx, my = int(x), int(y)
    if 0 <= mx < MAP_W and 0 <= my < MAP_H:
        return MAZE[my][mx]
    return 1


def is_blocked(x: float, y: float, jump_h: float, exit_open: bool = False) -> bool:
    """Check if position is blocked considering jump height.

    The exit is a closed door until exit_open is set (the level boss is dead)."""
    t = tile_at(x, y)
    if t == 1 or t == DOOR_TILE:
        return True
    if t == EXIT_TILE and not exit_open:
        return True
    if t == BARRIER_TILE and jump_h < 0.3:
        return True
    return False


def is_obstacle(x: float, y: float) -> bool:
    """Check if a tile blocks movement (walls, barriers, and closed doors)."""
    t = tile_at(x, y)
    return t == 1 or t == BARRIER_TILE or t == DOOR_TILE


def is_solid(x: float, y: float) -> bool:
    """Check if a tile blocks rays (walls, exit, barrier, and door tiles)."""
    t = tile_at(x, y)
    return t == 1 or t == EXIT_TILE or t == BARRIER_TILE or t == DOOR_TILE


def blocks_sight(x: float, y: float) -> bool:
    """Check if a tile blocks sight and projectiles (walls and closed doors).
    Barriers sit below eye level, so shots, rockets, and enemies see over them."""
    t = tile_at(x, y)
    return t == 1 or t == DOOR_TILE


def has_line_of_sight(x1: float, y1: float, x2: float, y2: float) -> bool:
    """Traverse every crossed tile, treating walls and closed doors as opaque.

    At grid corners, check both neighboring tiles so sight cannot pass through
    a diagonal wall seam. Barriers remain transparent at eye level.
    """
    cx, cy = math.floor(x1), math.floor(y1)
    end_x, end_y = math.floor(x2), math.floor(y2)
    if blocks_sight(cx, cy) or blocks_sight(end_x, end_y):
        return False

    dx = x2 - x1
    dy = y2 - y1
    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy > 0 else -1
    while cx != end_x or cy != end_y:
        # Parametric distances to the next grid boundaries. Stop stepping each
        # axis once its destination cell is reached, including boundary endpoints.
        next_x = ((cx + (1 if dx > 0 else 0) - x1) / dx
                  if cx != end_x else math.inf)
        next_y = ((cy + (1 if dy > 0 else 0) - y1) / dy
                  if cy != end_y else math.inf)

        if math.isclose(next_x, next_y, rel_tol=1e-12, abs_tol=1e-12):
            if blocks_sight(cx + step_x, cy) or blocks_sight(cx, cy + step_y):
                return False
            cx += step_x
            cy += step_y
        elif next_x < next_y:
            cx += step_x
        else:
            cy += step_y
        if blocks_sight(cx, cy):
            return False
    return True


def find_door_in_front(px: float, py: float, pa: float, max_range: float = 2.5) -> tuple[int, int] | None:
    """Find the closest door tile the player is facing, within range."""
    cos_a = math.cos(pa)
    sin_a = math.sin(pa)
    for i in range(1, int(max_range * 8) + 1):
        d = i / 8.0
        cx = px + cos_a * d
        cy = py + sin_a * d
        t = tile_at(cx, cy)
        if t == DOOR_TILE:
            return (int(cx), int(cy))
        if t == 1 or t == EXIT_TILE or t == BARRIER_TILE:
            return None
    return None


# ---------------------------------------------------------------------------
# Procedural level generation
# ---------------------------------------------------------------------------
def _carve_maze(grid: list[list[int]]) -> None:
    """Recursive backtracker on odd cells. grid must start as all walls."""
    # Visit cells at odd indices: (1,1), (1,3), ..., (MAP_W-2, MAP_H-2)
    stack = [(1, 1)]
    grid[1][1] = 0
    visited = {(1, 1)}
    while stack:
        c, r = stack[-1]
        neighbours = []
        for dc, dr in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nc, nr = c + dc, r + dr
            if 1 <= nc < MAP_W - 1 and 1 <= nr < MAP_H - 1 and (nc, nr) not in visited:
                neighbours.append((nc, nr, dc, dr))
        if not neighbours:
            stack.pop()
            continue
        nc, nr, dc, dr = random.choice(neighbours)
        # Knock down the wall between (c, r) and (nc, nr).
        grid[r + dr // 2][c + dc // 2] = 0
        grid[nr][nc] = 0
        visited.add((nc, nr))
        stack.append((nc, nr))


def _open_extra_walls(grid: list[list[int]], count: int) -> None:
    """Randomly remove interior walls to add loops/rooms."""
    candidates = []
    for r in range(1, MAP_H - 1):
        for c in range(1, MAP_W - 1):
            if grid[r][c] != 1:
                continue
            # Needs at least two opposing open neighbours so removal creates a loop/passage.
            horiz = grid[r][c - 1] == 0 and grid[r][c + 1] == 0
            vert = grid[r - 1][c] == 0 and grid[r + 1][c] == 0
            if horiz or vert:
                candidates.append((c, r))
    random.shuffle(candidates)
    for c, r in candidates[:count]:
        grid[r][c] = 0


def _place_exit(grid: list[list[int]]) -> tuple[int, int]:
    """Carve an exit on the far edge from the player start. Returns (ex, ey).

    DFS only visits odd-indexed cells, so even rows/cols are walls. We pick an
    odd-indexed floor tile in the bottom-right quadrant and knock out a straight
    corridor from it to the nearest boundary, placing the EXIT_TILE there.
    """
    anchors = []
    for r in range(MAP_H // 2 | 1, MAP_H - 1, 2):
        for c in range(MAP_W // 2 | 1, MAP_W - 1, 2):
            if grid[r][c] == 0:
                anchors.append((c, r))
    if not anchors:
        # Degenerate fallback: use (MAP_W-3, MAP_H-3) — an odd cell that DFS visits.
        ac, ar = MAP_W - 3, MAP_H - 3
        grid[ar][ac] = 0
        anchors.append((ac, ar))
    ac, ar = random.choice(anchors)

    # Choose whether to exit through the bottom or the right edge.
    if random.random() < 0.5:
        for r in range(ar + 1, MAP_H - 1):
            grid[r][ac] = 0
        ex, ey = ac, MAP_H - 1
    else:
        for c in range(ac + 1, MAP_W - 1):
            grid[ar][c] = 0
        ex, ey = MAP_W - 1, ar
    grid[ey][ex] = EXIT_TILE
    return ex, ey


def _pick_boss_tile(grid: list[list[int]], ex: int, ey: int) -> tuple[int, int]:
    """Pick a floor tile within ~3 tiles of the exit for the boss spawn."""
    candidates = []
    for r in range(max(1, ey - 3), min(MAP_H - 1, ey + 4)):
        for c in range(max(1, ex - 3), min(MAP_W - 1, ex + 4)):
            if grid[r][c] == 0 and (abs(c - 1) + abs(r - 1)) > 5:
                candidates.append((c, r))
    if not candidates:
        # Fallback: any floor tile far from start.
        for r in range(MAP_H // 2, MAP_H - 1):
            for c in range(MAP_W // 2, MAP_W - 1):
                if grid[r][c] == 0:
                    candidates.append((c, r))
    return random.choice(candidates)


def _place_doors(grid: list[list[int]], count: int) -> list[tuple[int, int]]:
    """Place doors on corridor chokepoints. Returns list of (col, row)."""
    candidates = []
    for r in range(1, MAP_H - 1):
        for c in range(1, MAP_W - 1):
            if grid[r][c] != 0:
                continue
            if (c, r) == (1, 1):
                continue
            left = grid[r][c - 1]
            right = grid[r][c + 1]
            up = grid[r - 1][c]
            down = grid[r + 1][c]
            # Horizontal corridor: walls above and below, floors left and right.
            if up == 1 and down == 1 and left == 0 and right == 0:
                candidates.append((c, r))
            elif left == 1 and right == 1 and up == 0 and down == 0:
                candidates.append((c, r))
    random.shuffle(candidates)
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


def _place_barriers(grid: list[list[int]], count: int, ex: int, ey: int) -> None:
    """Place low barriers on random floor tiles, away from start and exit."""
    candidates = []
    for r in range(2, MAP_H - 2):
        for c in range(2, MAP_W - 2):
            if grid[r][c] != 0:
                continue
            if abs(c - 1) + abs(r - 1) < 4:
                continue
            if abs(c - ex) + abs(r - ey) < 3:
                continue
            candidates.append((c, r))
    random.shuffle(candidates)
    for c, r in candidates[:count]:
        grid[r][c] = BARRIER_TILE


def generate_level(level: int) -> None:
    """Generate a new procedural level. Mutates module state in place.

    Updates: MAZE, DOOR_POSITIONS, EXIT_X, EXIT_Y, BOSS_SPAWN.
    Leaves PLAYER_SPAWN constant at (1.5, 1.5).
    """
    global EXIT_X, EXIT_Y, BOSS_SPAWN

    grid = [[1] * MAP_W for _ in range(MAP_H)]
    _carve_maze(grid)
    # Slightly more loops on later levels keeps things interesting.
    _open_extra_walls(grid, 20 + min(level, 5))
    grid[1][1] = 0  # guarantee player start is floor

    ex, ey = _place_exit(grid)
    doors = _place_doors(grid, random.randint(3, 5))
    _place_barriers(grid, random.randint(1, 3), ex, ey)
    # Pick the boss tile last so a door or barrier can't land on it and trap
    # the boss inside a solid tile (the exit only unlocks once the boss dies).
    bx, by = _pick_boss_tile(grid, ex, ey)

    MAZE.clear()
    MAZE.extend(grid)
    DOOR_POSITIONS.clear()
    DOOR_POSITIONS.extend(doors)
    EXIT_X, EXIT_Y = ex, ey
    BOSS_SPAWN = (bx + 0.5, by + 0.5)
