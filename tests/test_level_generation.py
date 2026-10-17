"""Generated levels own their data and preserve supplies as difficulty increases."""

import random
from collections import Counter, deque
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from shooter.constants import (
    SPAWN_ENEMY_MIN_DIST,
    SPAWN_HEALTH_PACK_COUNT,
    SPAWN_REGULAR_COUNT,
    SPAWN_SCOUT_COUNT,
    SPAWN_SPIDER_COUNT,
    SPAWN_WEAPON_PICKUP_COUNT,
)
from shooter.entities import PICKUP_WEAPONS, Boss, Enemy, Scout, Spider
from shooter.map import DOOR_TILE, FLOOR_TILE, MAP_H, MAP_W, WALL_TILE
from shooter.simulation import update_doors
from shooter.state import GameState, start_level
from shooter.textures import generate_textures
from shooter.types import DoorAnim


@pytest.fixture
def preserve_random_state() -> Iterator[None]:
    rng_state = random.getstate()
    try:
        yield
    finally:
        random.setstate(rng_state)


# Level 1 opens fewer extra walls, 10 fits every requested enemy, and 60 overflows the
# free cells; any higher level only overflows further.
@pytest.mark.parametrize("level", (1, 10, 60))
@pytest.mark.parametrize("seed", range(50))
def test_seeded_levels_have_reachable_unique_spawns_and_reserved_supplies(
    level: int, seed: int
) -> None:
    state = GameState(seed=seed)
    start_level(state, level)
    world = state.world
    start = tuple(int(v) for v in world.player_spawn)
    seen = {start}
    pending = deque([start])
    while pending:
        x, y = pending.popleft()
        for cell in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            col, row = cell
            # Doors can be opened and barriers jumped.
            if (
                0 <= col < MAP_W
                and 0 <= row < MAP_H
                and world.maze[row][col] != WALL_TILE
                and cell not in seen
            ):
                seen.add(cell)
                pending.append(cell)
    entities = [*state.enemies, *state.health_packs, *state.weapon_pickups]
    positions = [(int(e.x), int(e.y)) for e in entities]
    assert len(positions) == len(set(positions))
    assert all((world.maze[y][x] == FLOOR_TILE for x, y in positions))
    assert all((pos in seen for pos in positions))
    assert world.exit_pos in seen
    assert len(state.health_packs) == SPAWN_HEALTH_PACK_COUNT
    assert len(state.weapon_pickups) == SPAWN_WEAPON_PICKUP_COUNT
    assert {p.weapon_type for p in state.weapon_pickups} == set(PICKUP_WEAPONS)

    requested_counts = {
        Enemy: SPAWN_REGULAR_COUNT + level - 1,
        Scout: SPAWN_SCOUT_COUNT + level - 1,
        Spider: SPAWN_SPIDER_COUNT + level - 1,
    }
    counts = Counter(type(enemy) for enemy in state.enemies)
    assert counts[Boss] == 1
    assert counts.keys() <= requested_counts.keys() | {Boss}
    assert state.total_enemies == len(state.enemies)

    reserved = {(int(p.x), int(p.y)) for p in [*state.health_packs, *state.weapon_pickups]}
    reserved.add((int(world.boss_spawn[0]), int(world.boss_spawn[1])))
    capacity = sum(
        tile == FLOOR_TILE
        and abs(col - start[0]) + abs(row - start[1]) > SPAWN_ENEMY_MIN_DIST
        and (col, row) not in reserved
        for row, tiles in enumerate(world.maze)
        for col, tile in enumerate(tiles)
    )
    requested_total = sum(requested_counts.values())
    assert len(state.enemies) == 1 + min(requested_total, capacity)
    for enemy_type, requested in requested_counts.items():
        if capacity >= requested_total:
            assert counts[enemy_type] == requested
        else:
            assert counts[enemy_type] <= requested


@pytest.mark.usefixtures("preserve_random_state")
def test_assets_and_gameplay_randomness_do_not_change_seeded_levels() -> None:
    first, second = GameState(seed=37), GameState(seed=37)
    for level in (1, 2, 3):
        start_level(first, level)
        generate_textures()  # Many draws from the process-global cosmetic RNG.
        for _ in range(100):
            second.rng.random()
            for enemy in second.enemies:
                enemy.rng.random()
        start_level(second, level)
        assert first.world == second.world
        assert [(type(e), e.x, e.y) for e in first.enemies] == [
            (type(e), e.x, e.y) for e in second.enemies
        ]
        assert [(p.x, p.y, p.weapon_type) for p in first.weapon_pickups] == [
            (p.x, p.y, p.weapon_type) for p in second.weapon_pickups
        ]
        assert [(p.x, p.y) for p in first.health_packs] == [(p.x, p.y) for p in second.health_packs]


def test_loading_and_opening_doors_in_one_game_cannot_mutate_another() -> None:
    first, second = GameState(seed=0), GameState(seed=0)
    start_level(first, 1)
    start_level(second, 1)
    original_maze = [row.copy() for row in first.world.maze]
    original_doors = first.world.door_positions.copy()
    original_exit = first.world.exit_pos
    col, row = second.world.door_positions[0]
    second.door_anim[(col, row)] = DoorAnim(phase="opening", progress=0.9, timer=0)
    update_doors(second, 50, MagicMock())
    assert second.world.tile_at(col, row) == FLOOR_TILE
    assert first.world.tile_at(col, row) == DOOR_TILE
    start_level(second, 2)
    assert first.world.maze == original_maze
    assert first.world.door_positions == original_doors
    assert first.world.exit_pos == original_exit
