"""Per-frame gameplay updates and their ordering: movement, doors, combat, and pickups."""

from __future__ import annotations

import math
from collections.abc import Callable

import pygame

from shooter.combat import update_combat, update_enemies, update_rockets
from shooter.constants import (
    DOOR_ANIM_DURATION,
    DOOR_OPEN_DURATION,
    DOOR_RETRY_DELAY,
    FOOTSTEP_SPRINT_INTERVAL,
    FOOTSTEP_WALK_INTERVAL,
    GRAVITY,
    JUMP_VELOCITY,
    MAX_AMMO,
    PICKUP_RADIUS,
    PLAYER_MARGIN,
    PLAYER_MAX_HP,
    PLAYER_MOVE_SPEED,
    PLAYER_ROT_SPEED,
    PLAYER_SPRINT_MULT,
    WEAPONS,
)
from shooter.map import BARRIER_TILE, DOOR_TILE
from shooter.state import GameState, check_win_lose
from shooter.types import KeyState, Sfx


def _footprint_hits(x: float, y: float, solid: Callable[[float, float], bool]) -> bool:
    """Check the player's square footprint (half-width PLAYER_MARGIN) at (x, y).

    The footprint is narrower than a tile, so its corners touch every tile it overlaps.
    """
    r = PLAYER_MARGIN
    return any(solid(cx, cy) for cx in (x - r, x + r) for cy in (y - r, y + r))


def _advance(pos: float, delta: float, blocked: Callable[[float], bool]) -> float:
    """Move along one axis, or stop flush against the tile edge in the way."""
    if not blocked(pos + delta):
        return pos + delta
    if delta > 0:
        edge = math.floor(pos + delta + PLAYER_MARGIN) - PLAYER_MARGIN - 1e-6
    else:
        edge = math.floor(pos + delta - PLAYER_MARGIN) + 1 + PLAYER_MARGIN + 1e-6
    if (edge - pos) * delta > 0 and not blocked(edge):
        return edge
    return pos


def update_player(
    state: GameState, dt: int, keys: KeyState, pressed_scancodes: set[int], sfx: Sfx
) -> bool:
    """Handle movement, jumping, and footstep sounds. Returns True if the player moved."""
    if keys[pygame.K_LEFT]:
        state.pa -= PLAYER_ROT_SPEED * dt
    if keys[pygame.K_RIGHT]:
        state.pa += PLAYER_ROT_SPEED * dt
    state.pa %= 2 * math.pi

    move = 0
    strafe = 0
    if pygame.KSCAN_W in pressed_scancodes or keys[pygame.K_UP]:
        move = 1
    if pygame.KSCAN_S in pressed_scancodes or keys[pygame.K_DOWN]:
        move = -1
    if pygame.KSCAN_A in pressed_scancodes:
        strafe = -1
    if pygame.KSCAN_D in pressed_scancodes:
        strafe = 1

    sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
    sp = PLAYER_MOVE_SPEED * (PLAYER_SPRINT_MULT if sprinting else 1.0) * dt
    dx = math.cos(state.pa) * move + math.cos(state.pa + math.pi / 2) * strafe
    dy = math.sin(state.pa) * move + math.sin(state.pa + math.pi / 2) * strafe
    move_len = math.hypot(dx, dy)
    if move_len > 0:
        dx = dx / move_len * sp
        dy = dy / move_len * sp

    old_px, old_py = state.px, state.py
    if dx != 0 or dy != 0:
        # Landing on a barrier's edge leaves the player standing on it, free to step off.
        on_barrier = state.jump_height < 0.3 and _footprint_hits(
            state.px, state.py, lambda x, y: state.world.tile_at(x, y) == BARRIER_TILE
        )
        jh = 1.0 if on_barrier else state.jump_height
        exit_open = state.exit_open

        def solid(x: float, y: float) -> bool:
            return state.world.is_blocked(x, y, jh, exit_open)

        state.px = _advance(state.px, dx, lambda x: _footprint_hits(x, state.py, solid))
        state.py = _advance(state.py, dy, lambda y: _footprint_hits(state.px, y, solid))

    if keys[pygame.K_SPACE] and state.on_ground:
        state.jump_vel = JUMP_VELOCITY
        state.on_ground = False
    state.jump_vel -= GRAVITY * dt
    state.jump_height += state.jump_vel * dt
    if state.jump_height <= 0:
        state.jump_height = 0
        state.jump_vel = 0
        state.on_ground = True

    player_moved = state.px != old_px or state.py != old_py
    if player_moved and state.on_ground:
        state.step_timer -= dt
        if state.step_timer <= 0:
            sfx[f"step{state.step_index}"].play()
            state.step_index = 1 - state.step_index
            state.step_timer = FOOTSTEP_SPRINT_INTERVAL if sprinting else FOOTSTEP_WALK_INTERVAL
    state.game_time += dt * 0.001

    return player_moved


def update_doors(state: GameState, dt: int, sfx: Sfx) -> None:
    """Advance door animations through opening -> open -> closing phases."""
    anim_step = dt / DOOR_ANIM_DURATION
    to_remove: list[tuple[int, int]] = []
    for (dc, dr), anim in state.door_anim.items():
        phase = anim["phase"]
        if phase == "opening":
            anim["progress"] += anim_step
            if anim["progress"] >= 1.0:
                anim["progress"] = 1.0
                state.world.maze[dr][dc] = 0
                anim["phase"] = "open"
                anim["timer"] = DOOR_OPEN_DURATION
        elif phase == "open":
            anim["timer"] -= dt
            if anim["timer"] <= 0:
                # Any overlap with the player's footprint keeps the door open.
                occupied = _footprint_hits(
                    state.px, state.py, lambda x, y, dc=dc, dr=dr: (int(x), int(y)) == (dc, dr)
                )
                if not occupied:
                    for e in state.enemies:
                        if e.alive and int(e.x) == dc and int(e.y) == dr:
                            occupied = True
                            break
                if not occupied:
                    state.world.maze[dr][dc] = DOOR_TILE
                    anim["phase"] = "closing"
                    sfx["door_close"].play()
                else:
                    anim["timer"] = DOOR_RETRY_DELAY
        elif phase == "closing":
            anim["progress"] -= anim_step
            if anim["progress"] <= 0.0:
                to_remove.append((dc, dr))
    for key in to_remove:
        del state.door_anim[key]


def update_pickups(state: GameState, dt: int, sfx: Sfx) -> None:
    """Update pickup animations and check for player collection."""
    if state.hp <= 0:
        return
    for hp_pack in state.health_packs:
        if not hp_pack.active:
            continue
        hp_pack.update(dt)
        dist = math.hypot(hp_pack.x - state.px, hp_pack.y - state.py)
        if dist < PICKUP_RADIUS and state.hp < PLAYER_MAX_HP:
            hp_pack.active = False
            state.hp = min(PLAYER_MAX_HP, state.hp + hp_pack.heal_amount)
            sfx["pickup"].play()

    for pack in state.weapon_pickups:
        if not pack.active:
            continue
        pack.update(dt)
        dist = math.hypot(pack.x - state.px, pack.y - state.py)
        if dist >= PICKUP_RADIUS:
            continue
        wt = pack.weapon_type
        ai = WEAPONS[wt].ammo_pool
        if not state.owned[wt]:
            # First time: unlock the weapon and hand over the starter ammo.
            state.owned[wt] = True
            state.ammo[ai] = min(state.ammo[ai] + WEAPONS[wt].pickup_ammo, MAX_AMMO[ai])
            # Auto-switch if the new weapon outranks what we're holding.
            if wt > state.weapon:
                state.weapon = wt
                state.shoot_timer = 0
                state.shooting = False
            pack.active = False
            sfx["pickup"].play()
        elif state.ammo[ai] < MAX_AMMO[ai]:
            state.ammo[ai] = min(state.ammo[ai] + WEAPONS[wt].pickup_ammo, MAX_AMMO[ai])
            pack.active = False
            sfx["pickup"].play()


def update_game(
    state: GameState, dt: int, keys: KeyState, pressed_scancodes: set[int], sfx: Sfx
) -> bool:
    """Advance one simulation frame; lethal damage takes precedence over pickups."""
    if state.paused or state.game_over:
        return False
    if state.hp <= 0:
        check_win_lose(state)
        return False
    moved = update_player(state, dt, keys, pressed_scancodes, sfx)
    update_combat(state, dt, sfx)
    update_doors(state, dt, sfx)
    update_enemies(state, dt, sfx)
    if state.hp > 0:
        update_rockets(state, dt, sfx)
    if state.hp > 0:
        update_pickups(state, dt, sfx)
    check_win_lose(state)
    if state.level_banner_timer > 0:
        state.level_banner_timer -= dt
    return moved
