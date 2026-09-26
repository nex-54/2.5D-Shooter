"""
Main game loop — initialization, input handling, game state updates, and draw orchestration.

The game loop is split into focused functions so individual behaviors (movement,
combat, doors, enemies, pickups, rendering) can be located and modified independently.
All mutable state lives in the GameState object, initialized/reset via reset_game().
"""

from __future__ import annotations

import math
import random
import sys
from collections.abc import Callable
from typing import Any

import pygame
import pygame.freetype

from shooter.types import DoorAnim, DoorAnimMap, Sfx, Textures
from shooter.constants import (
    WIDTH, HEIGHT, FPS, SAMPLE_RATE, EYE_HEIGHT,
    WHITE, BLACK, RED, YELLOW,
    PLAYER_MAX_HP,
    PLAYER_MOVE_SPEED, PLAYER_ROT_SPEED, PLAYER_SPRINT_MULT, PLAYER_MARGIN,
    MOUSE_SENSITIVITY,
    JUMP_VELOCITY, GRAVITY,
    INITIAL_AMMO, INITIAL_OWNED, MAX_AMMO, AMMO_INDEX, FIRE_RATES, WEAPON_NAMES, EMPTY_CLICK_DELAY,
    DAMAGE_COOLDOWN_MS, PICKUP_RADIUS,
    PISTOL_DAMAGE,
    SHOTGUN_PELLETS, SHOTGUN_SPREAD, SHOTGUN_RANGE,
    GATLING_SPREAD,
    ROCKET_SPEED, ROCKET_HIT_RADIUS, ROCKET_BLAST_RADIUS, ROCKET_MAX_HITS,
    ROCKET_SELF_DAMAGE, EXPLOSION_DURATION,
    FOOTSTEP_WALK_INTERVAL, FOOTSTEP_SPRINT_INTERVAL,
    DOOR_OPEN_DURATION, DOOR_RETRY_DELAY, DOOR_ANIM_DURATION,
    SPAWN_REGULAR_COUNT, SPAWN_SCOUT_COUNT, SPAWN_SPIDER_COUNT,
)
from shooter import map as gmap
from shooter.map import (
    MAZE, DOOR_TILE, BARRIER_TILE,
    tile_at, is_blocked, blocks_sight, find_door_in_front, has_line_of_sight,
)
from shooter.sound import init_sounds
from shooter.textures import generate_textures, generate_icon
from shooter.entities import (
    Boss, Enemy, HealthPack, Rocket, WeaponPickup,
    spawn_enemies, spawn_health_packs, spawn_weapon_pickups,
    hitscan, apply_hit,
)
from shooter.raycaster import cast_rays
from shooter.occlusion import DepthBuffer
from shooter.render_world import draw_floor_ceiling, draw_3d
from shooter.render_sprites import Billboard, draw_world_sprites
from shooter.render_ui import draw_minimap, draw_crosshair, draw_hud
from shooter.weapons import draw_weapon


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
class GameState:
    """All mutable game state, grouped by concern.

    Lifecycle:
        GameState()           -- construct (calls reset())
        start_level(s, n)     -- generate level n, spawn entities, refill HP
        reset_game(s)         -- full reset + start_level(1) after death

    Field groups:

        Player pose & physics
            px, py     -- world position (floats; integer part = tile col/row).
            pa         -- facing angle in radians, normalized to [0, 2*pi).
            jump_vel   -- vertical velocity (world units / ms), + = rising.
            jump_height-- current height above ground (world units).
            on_ground  -- True while jump_height == 0.

        Player combat
            hp              -- remaining hit points; <= 0 triggers game_over.
            damage_cooldown -- ms of i-frames remaining after taking a hit.
            kills           -- enemies killed this level (drives HUD "X / Y").

        Weapons (see constants.WEAPON_NAMES for indices)
            weapon       -- currently equipped weapon index (0..4).
            ammo         -- per-pool ammo counts; index via AMMO_INDEX[weapon].
            owned        -- which weapons the player has picked up.
            shooting     -- True while the firing animation is playing.
            shoot_timer  -- ms until the next shot is allowed (ROF gate).
            mouse_held   -- True while LMB is down (drives gatling auto-fire).
            gatling_spin -- barrel rotation angle (radians).
            gatling_speed-- barrel speed (rad/ms); coasts down after release.

        Footsteps
            step_timer, step_index -- alternates step0/step1 sounds on move.

        World
            game_time  -- seconds elapsed; used for idle-sway animations.
            game_over  -- True after death; main loop skips updates.
            paused     -- True while the pause screen is up; main loop skips updates.
            door_anim  -- per-door animation state; see shooter.types.DoorAnim.

        Level progression
            level              -- current level number (1-based).
            level_banner_timer -- ms remaining to show the "LEVEL N" banner.
            spawn_grace       -- ms of enemy-damage immunity after level load.

        Entities (populated/refreshed by start_level)
            enemies        -- all enemies including the boss.
            boss           -- level boss (also present in enemies list).
            total_enemies  -- len(enemies) at spawn, for HUD kill ratio.
            health_packs, weapon_pickups -- collectible items on the floor.
            rockets        -- in-flight rocket projectiles.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Set every field to its starting value. Does NOT generate a level."""
        # Player position & physics
        self.px = gmap.PLAYER_SPAWN[0]
        self.py = gmap.PLAYER_SPAWN[1]
        self.pa = 0.0
        self.jump_vel = 0.0
        self.jump_height = 0.0
        self.on_ground = True

        # Player combat
        self.hp = PLAYER_MAX_HP
        self.damage_cooldown = 0
        self.kills = 0

        # Weapons
        self.weapon = 0
        self.ammo = list(INITIAL_AMMO)
        self.owned = list(INITIAL_OWNED)
        self.shooting = False
        self.shoot_timer = 0
        self.mouse_held = False
        self.gatling_spin = 0.0
        self.gatling_speed = 0.0

        # Footsteps
        self.step_timer = 0
        self.step_index = 0

        # World
        self.game_time = 0.0
        self.game_over = False
        self.paused = False
        self.door_anim: DoorAnimMap = {}

        # Level progression
        self.level = 1
        self.level_banner_timer = 0
        self.spawn_grace = 0

        # Entities (populated by start_level)
        self.enemies: list[Enemy] = []
        self.boss: Boss | None = None
        self.total_enemies = 0
        self.health_packs: list[HealthPack] = []
        self.weapon_pickups: list[WeaponPickup] = []
        self.rockets: list[Rocket] = []

    @property
    def exit_open(self) -> bool:
        """The exit unlocks once the level boss is dead."""
        return self.boss is not None and not self.boss.alive


def start_level(state: GameState, level: int) -> None:
    """Generate a new procedural level and (re)spawn all entities.

    Preserves the player's HP, ammo, weapon, and kills so progression carries over.
    Enemy counts scale modestly with level number.
    """
    gmap.generate_level(level)

    # Reposition player to the fresh spawn and clear per-level transient state.
    state.px = gmap.PLAYER_SPAWN[0]
    state.py = gmap.PLAYER_SPAWN[1]
    state.pa = 0.0
    state.jump_vel = 0.0
    state.jump_height = 0.0
    state.on_ground = True
    state.door_anim = {}
    state.damage_cooldown = 0
    state.shoot_timer = 0
    state.shooting = False
    state.mouse_held = False

    # Difficulty scaling: +1 of each enemy type per level.
    bonus = level - 1
    boss_tile = (int(gmap.BOSS_SPAWN[0]), int(gmap.BOSS_SPAWN[1]))
    used_tiles: set[tuple[int, int]] = set()
    state.enemies = spawn_enemies(
        used_tiles,
        regular_count=SPAWN_REGULAR_COUNT + bonus,
        scout_count=SPAWN_SCOUT_COUNT + bonus,
        spider_count=SPAWN_SPIDER_COUNT + bonus,
        boss_tile=boss_tile,
    )
    state.boss = Boss(gmap.BOSS_SPAWN[0], gmap.BOSS_SPAWN[1])
    state.enemies.append(state.boss)
    used_tiles.add(boss_tile)
    state.total_enemies = len(state.enemies)
    state.health_packs = spawn_health_packs(used_tiles)
    state.weapon_pickups = spawn_weapon_pickups(used_tiles)
    state.rockets = []

    state.hp = PLAYER_MAX_HP  # refill health on each new level
    state.level = level
    state.level_banner_timer = 1200  # ms
    state.spawn_grace = 2000  # ms — no enemy damage while player gets oriented
    state.kills = 0  # per-level kill counter so HUD "X/Y" stays meaningful


def reset_game(state: GameState) -> None:
    """Full game reset after death: reinitialize state and start level 1."""
    state.reset()
    start_level(state, 1)


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------
def handle_events(state: GameState, sfx: Sfx,
                  pressed_scancodes: set[int]) -> bool:
    """Process all pygame events. Returns False if the game should quit."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        elif event.type == pygame.KEYDOWN:
            pressed_scancodes.add(event.scancode)
            if event.key == pygame.K_ESCAPE:
                # Esc pauses; the game-over screen has nothing to pause.
                if state.game_over:
                    return False
                if state.paused:
                    state.paused = False
                else:
                    _pause(state, pressed_scancodes)
                continue
            if state.paused:
                if event.key == pygame.K_q:
                    return False
                continue
            if event.scancode == pygame.KSCAN_R and state.game_over:
                reset_game(state)
            # Reset the fire cooldown only on an actual switch — re-pressing the
            # equipped weapon's key must not zero shoot_timer (rate-of-fire bypass).
            weapon_keys = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                           pygame.K_4: 3, pygame.K_0: 4}
            if event.key in weapon_keys and not state.game_over:
                new_weapon = weapon_keys[event.key]
                if state.owned[new_weapon] and state.weapon != new_weapon:
                    state.weapon = new_weapon
                    state.shoot_timer = 0
                    state.shooting = False
            if event.scancode == pygame.KSCAN_E and not state.game_over:
                door_pos = find_door_in_front(state.px, state.py, state.pa)
                if door_pos and door_pos not in state.door_anim:
                    state.door_anim[door_pos] = DoorAnim(
                        phase='opening', progress=0.0, timer=0,
                    )
                    sfx['door_open'].play()
        elif event.type == pygame.KEYUP:
            pressed_scancodes.discard(event.scancode)
        elif event.type == pygame.WINDOWFOCUSLOST:
            if not state.game_over:
                _pause(state, pressed_scancodes)
        elif event.type == pygame.MOUSEMOTION:
            if not state.game_over and not state.paused:
                state.pa += event.rel[0] * MOUSE_SENSITIVITY
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and state.paused:
                state.paused = False  # the click that resumes doesn't fire
            elif event.button == 1 and not state.game_over:
                state.mouse_held = True
                _handle_click_fire(state, sfx)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                state.mouse_held = False
    return True


def _pause(state: GameState, pressed_scancodes: set[int]) -> None:
    """Freeze gameplay, dropping held input so nothing sticks on resume."""
    state.paused = True
    state.mouse_held = False
    pressed_scancodes.clear()


def _handle_click_fire(state: GameState, sfx: Sfx) -> None:
    """Fire single-shot weapons (pistol / shotgun) on mouse click."""
    if state.weapon == 0 and state.ammo[AMMO_INDEX[0]] > 0 and state.shoot_timer <= 0:
        state.shooting = True
        state.shoot_timer = FIRE_RATES[0]
        state.ammo[AMMO_INDEX[0]] -= 1
        sfx['pistol'].play()
        target = hitscan(state.enemies, state.px, state.py, state.pa)
        if target:
            killed = False
            for _ in range(PISTOL_DAMAGE):
                if not target.alive:
                    break
                if apply_hit(target, sfx):
                    killed = True
            if killed:
                state.kills += 1
    if state.weapon == 1 and state.ammo[AMMO_INDEX[1]] > 0 and state.shoot_timer <= 0:
        state.shooting = True
        state.shoot_timer = FIRE_RATES[1]
        state.ammo[AMMO_INDEX[1]] -= 1
        sfx['shotgun'].play()
        for _ in range(SHOTGUN_PELLETS):
            spread = random.uniform(-SHOTGUN_SPREAD, SHOTGUN_SPREAD)
            target = hitscan(state.enemies, state.px, state.py, state.pa,
                             spread=spread, max_range=SHOTGUN_RANGE)
            if target and apply_hit(target, sfx):
                state.kills += 1
    if state.weapon == 3 and state.ammo[AMMO_INDEX[3]] > 0 and state.shoot_timer <= 0:
        state.shooting = True
        state.shoot_timer = FIRE_RATES[3]
        state.ammo[AMMO_INDEX[3]] -= 1
        sfx['rocket_fire'].play()
        # Spawn rocket a little in front of the player so it can't detonate on us immediately.
        spawn_x = state.px + math.cos(state.pa) * 0.4
        spawn_y = state.py + math.sin(state.pa) * 0.4
        state.rockets.append(Rocket(spawn_x, spawn_y, state.pa))
    if state.weapon == 4 and state.ammo[AMMO_INDEX[4]] > 0 and state.shoot_timer <= 0:
        state.shooting = True
        state.shoot_timer = FIRE_RATES[4]
        state.ammo[AMMO_INDEX[4]] -= 1
        sfx['explosion'].play()
        for e in state.enemies:
            if not e.alive or e.is_boss:
                continue
            while e.alive:
                e.take_damage()
            sfx['spider_die' if e.is_spider else 'enemy_die'].play()
            state.kills += 1
    if state.ammo[AMMO_INDEX[state.weapon]] <= 0 and state.shoot_timer <= 0:
        sfx['empty'].play()
        state.shoot_timer = EMPTY_CLICK_DELAY


# ---------------------------------------------------------------------------
# Per-frame updates
# ---------------------------------------------------------------------------
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


def update_player(state: GameState, dt: int, keys: Any,
                  pressed_scancodes: set[int],
                  sfx: Sfx) -> bool:
    """Handle movement, jumping, and footstep sounds. Returns True if the player moved."""
    if keys[pygame.K_LEFT]:
        state.pa -= PLAYER_ROT_SPEED * dt
    if keys[pygame.K_RIGHT]:
        state.pa += PLAYER_ROT_SPEED * dt
    state.pa %= (2 * math.pi)

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
            state.px, state.py, lambda x, y: tile_at(x, y) == BARRIER_TILE)
        jh = 1.0 if on_barrier else state.jump_height
        exit_open = state.exit_open

        def solid(x: float, y: float) -> bool:
            return is_blocked(x, y, jh, exit_open)

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

    player_moved = (state.px != old_px or state.py != old_py)
    if player_moved and state.on_ground:
        state.step_timer -= dt
        if state.step_timer <= 0:
            sfx[f'step{state.step_index}'].play()
            state.step_index = 1 - state.step_index
            state.step_timer = FOOTSTEP_SPRINT_INTERVAL if sprinting else FOOTSTEP_WALK_INTERVAL
    state.game_time += dt * 0.001

    return player_moved


def update_combat(state: GameState, dt: int,
                  sfx: Sfx) -> None:
    """Handle shoot timer and gatling auto-fire."""
    if state.shoot_timer > 0:
        state.shoot_timer -= dt
    if state.shoot_timer <= 0:
        state.shooting = False

    if state.weapon == 2 and state.mouse_held and not state.game_over:
        state.gatling_speed = 0.08
        if state.shoot_timer <= 0 and state.ammo[AMMO_INDEX[2]] > 0:
            state.shooting = True
            state.shoot_timer = FIRE_RATES[2]
            state.ammo[AMMO_INDEX[2]] -= 1
            sfx['gatling'].play()
            target = hitscan(state.enemies, state.px, state.py, state.pa,
                             spread=random.uniform(-GATLING_SPREAD, GATLING_SPREAD))
            if target and apply_hit(target, sfx):
                state.kills += 1
        elif state.shoot_timer <= 0 and state.ammo[AMMO_INDEX[2]] <= 0:
            sfx['empty'].play()
            state.shoot_timer = EMPTY_CLICK_DELAY
    else:
        # Released barrels coast to a stop over 400 ms instead of unwinding.
        state.gatling_speed = max(0.0, state.gatling_speed - dt * 0.0002)
    state.gatling_spin = (state.gatling_spin + state.gatling_speed * dt) % (2 * math.pi)


def update_doors(state: GameState, dt: int,
                 sfx: Sfx) -> None:
    """Advance door animations through opening -> open -> closing phases."""
    anim_step = dt / DOOR_ANIM_DURATION
    to_remove = []
    for (dc, dr), anim in state.door_anim.items():
        phase = anim['phase']
        if phase == 'opening':
            anim['progress'] += anim_step
            if anim['progress'] >= 1.0:
                anim['progress'] = 1.0
                MAZE[dr][dc] = 0
                anim['phase'] = 'open'
                anim['timer'] = DOOR_OPEN_DURATION
        elif phase == 'open':
            anim['timer'] -= dt
            if anim['timer'] <= 0:
                # Any overlap with the player's footprint keeps the door open.
                occupied = _footprint_hits(state.px, state.py,
                                           lambda x, y: (int(x), int(y)) == (dc, dr))
                if not occupied:
                    for e in state.enemies:
                        if e.alive and int(e.x) == dc and int(e.y) == dr:
                            occupied = True
                            break
                if not occupied:
                    MAZE[dr][dc] = DOOR_TILE
                    anim['phase'] = 'closing'
                    sfx['door_close'].play()
                else:
                    anim['timer'] = DOOR_RETRY_DELAY
        elif phase == 'closing':
            anim['progress'] -= anim_step
            if anim['progress'] <= 0.0:
                to_remove.append((dc, dr))
    for key in to_remove:
        del state.door_anim[key]


def update_enemies(state: GameState, dt: int,
                   sfx: Sfx) -> None:
    """Run enemy AI and apply enemy attacks to the player."""
    if state.damage_cooldown > 0:
        state.damage_cooldown -= dt
    if state.spawn_grace > 0:
        state.spawn_grace -= dt
    for e in state.enemies:
        e.update(state.px, state.py, dt)
        if e.alive and state.hp > 0 and state.damage_cooldown <= 0 and state.spawn_grace <= 0:
            dist = math.hypot(e.x - state.px, e.y - state.py)
            if dist < e.attack_range and e.attack_cooldown <= 0 and has_line_of_sight(e.x, e.y, state.px, state.py):
                state.hp -= e.damage
                e.attack_cooldown = e.attack_cooldown_duration
                state.damage_cooldown = DAMAGE_COOLDOWN_MS
                sfx['boss_roar' if e.is_boss else ('spider_hiss' if e.is_spider else 'enemy_attack')].play()
                if state.hp <= 0:
                    break


def update_pickups(state: GameState, dt: int,
                   sfx: Sfx) -> None:
    """Update pickup animations and check for player collection."""
    for hp_pack in state.health_packs:
        if not hp_pack.active:
            continue
        hp_pack.update(dt)
        dist = math.hypot(hp_pack.x - state.px, hp_pack.y - state.py)
        if dist < PICKUP_RADIUS and state.hp < PLAYER_MAX_HP:
            hp_pack.active = False
            state.hp = min(PLAYER_MAX_HP, state.hp + hp_pack.heal_amount)
            sfx['pickup'].play()

    for pack in state.weapon_pickups:
        if not pack.active:
            continue
        pack.update(dt)
        dist = math.hypot(pack.x - state.px, pack.y - state.py)
        if dist >= PICKUP_RADIUS:
            continue
        wt = pack.weapon_type
        ai = AMMO_INDEX[wt]
        if not state.owned[wt]:
            # First time: unlock the weapon and hand over the starter ammo.
            state.owned[wt] = True
            state.ammo[ai] = min(state.ammo[ai] + pack.amounts[wt], MAX_AMMO[ai])
            # Auto-switch if the new weapon outranks what we're holding.
            if wt > state.weapon:
                state.weapon = wt
                state.shoot_timer = 0
                state.shooting = False
            pack.active = False
            sfx['pickup'].play()
        elif state.ammo[ai] < MAX_AMMO[ai]:
            state.ammo[ai] = min(state.ammo[ai] + pack.amounts[wt], MAX_AMMO[ai])
            pack.active = False
            sfx['pickup'].play()


def update_rockets(state: GameState, dt: int,
                   sfx: Sfx) -> None:
    """Advance in-flight rockets, detonate on contact, apply splash damage."""
    for rocket in state.rockets:
        if not rocket.alive:
            continue
        if rocket.exploded:
            rocket.explosion_timer -= dt
            if rocket.explosion_timer <= 0:
                rocket.alive = False
            continue

        rocket.trail_phase += dt * 0.02
        step = ROCKET_SPEED * dt
        nx = rocket.x + math.cos(rocket.angle) * step
        ny = rocket.y + math.sin(rocket.angle) * step

        detonate = False
        # Rockets fly at eye level, over barriers.
        if blocks_sight(nx, ny):
            # Stop just outside the wall so the explosion sprite doesn't disappear.
            rocket.x -= math.cos(rocket.angle) * 0.05
            rocket.y -= math.sin(rocket.angle) * 0.05
            detonate = True
        else:
            rocket.x = nx
            rocket.y = ny
            for e in state.enemies:
                if e.alive and math.hypot(e.x - rocket.x, e.y - rocket.y) < ROCKET_HIT_RADIUS:
                    detonate = True
                    break

        if detonate:
            rocket.exploded = True
            rocket.explosion_timer = EXPLOSION_DURATION
            sfx['explosion'].play()
            # Splash damage to enemies (closer = more take_damage() calls).
            for e in state.enemies:
                if not e.alive:
                    continue
                d = math.hypot(e.x - rocket.x, e.y - rocket.y)
                if d >= ROCKET_BLAST_RADIUS:
                    continue
                if not has_line_of_sight(rocket.x, rocket.y, e.x, e.y):
                    continue
                falloff = 1.0 - (d / ROCKET_BLAST_RADIUS)
                hits = max(1, int(ROCKET_MAX_HITS * falloff))
                killed = False
                for _ in range(hits):
                    if not e.alive:
                        break
                    e.take_damage()
                    if not e.alive:
                        killed = True
                if killed:
                    sfx['boss_die' if e.is_boss else
                        ('spider_die' if e.is_spider else 'enemy_die')].play()
                    state.kills += 1
                else:
                    sfx['enemy_hurt'].play()
            # Splash damage to the player — rockets hurt the one firing them too.
            pd = math.hypot(state.px - rocket.x, state.py - rocket.y)
            if (pd < ROCKET_BLAST_RADIUS and state.damage_cooldown <= 0
                    and has_line_of_sight(rocket.x, rocket.y, state.px, state.py)):
                falloff = 1.0 - (pd / ROCKET_BLAST_RADIUS)
                self_damage = int(ROCKET_SELF_DAMAGE * falloff)
                if self_damage > 0:
                    state.hp -= self_damage
                    state.damage_cooldown = DAMAGE_COOLDOWN_MS

    state.rockets = [r for r in state.rockets if r.alive]


def check_win_lose(state: GameState) -> None:
    """Check for death and level-exit conditions."""
    if state.hp <= 0:
        state.game_over = True
        return
    if int(state.px) == gmap.EXIT_X and int(state.py) == gmap.EXIT_Y and state.exit_open:
        # Advance to the next randomly-generated level. Ammo and weapons carry
        # over; HP refills (see start_level).
        start_level(state, state.level + 1)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def draw_game_over(screen: pygame.Surface, state: GameState,
                   font: Any, big_font: Any) -> None:
    """Render the game-over screen (death only — wins now advance levels)."""
    screen.fill(BLACK)
    msg, _ = big_font.render("GAME OVER", RED)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render(
        f"Reached Level {state.level}  -  Kills: {state.kills}/{state.total_enemies}  -  Press R to restart  -  ESC to quit",
        WHITE)
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_level_banner(screen: pygame.Surface, state: GameState, big_font: Any) -> None:
    """Draw a brief 'LEVEL N' banner that fades out over ~1.2s."""
    if state.level_banner_timer <= 0:
        return
    # Fade alpha based on remaining time (full for first 400 ms, then linear).
    total = 1200
    remaining = max(0, state.level_banner_timer)
    alpha = 255 if remaining > total - 400 else int(255 * remaining / (total - 400))
    overlay = pygame.Surface((WIDTH, 120), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, min(180, alpha)))
    screen.blit(overlay, (0, HEIGHT // 2 - 60))
    msg, _ = big_font.render(f"LEVEL {state.level}", YELLOW)
    msg.set_alpha(alpha)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - msg.get_height() // 2))


def draw_pause_overlay(screen: pygame.Surface, font: Any, big_font: Any) -> None:
    """Dim the frozen frame and show how to resume or quit."""
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 150))
    screen.blit(dim, (0, 0))
    msg, _ = big_font.render("PAUSED", YELLOW)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render("Esc or click to resume  -  Q to quit", WHITE)
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_frame(state: GameState, screen: pygame.Surface, font: Any,
               textures: Textures, z_buffer: DepthBuffer,
               player_moving: bool) -> None:
    """Draw one complete gameplay frame (3D view, sprites, HUD)."""
    eye = EYE_HEIGHT + state.jump_height
    walls = cast_rays(state.px, state.py, state.pa, state.door_anim)
    draw_floor_ceiling(screen, state.px, state.py, state.pa, textures, eye)
    draw_3d(screen, walls, z_buffer, font, textures, eye, door_anim=state.door_anim)
    billboards = [Billboard("START", *gmap.PLAYER_SPAWN, (20, 20, 80))]
    if state.boss is not None and state.boss.alive:
        billboards.append(Billboard("BOSS", state.boss.x, state.boss.y, (80, 20, 80)))
    draw_world_sprites(screen, state.px, state.py, state.pa, z_buffer, font,
                       enemies=state.enemies, health_packs=state.health_packs,
                       weapon_pickups=state.weapon_pickups, rockets=state.rockets,
                       billboards=billboards, eye_height=eye)
    draw_minimap(screen, state.px, state.py, state.pa, state.enemies,
                 state.health_packs, state.weapon_pickups, state.rockets)
    draw_crosshair(screen)
    draw_weapon(screen, state.shooting, state.shoot_timer, player_moving,
                state.game_time, state.weapon, state.gatling_spin)
    draw_hud(screen, font, state.hp, state.ammo[AMMO_INDEX[state.weapon]], state.kills,
             state.total_enemies, WEAPON_NAMES[state.weapon], state.level)

    door_pos = find_door_in_front(state.px, state.py, state.pa)
    if door_pos is not None and door_pos not in state.door_anim:
        prompt_surf, prompt_rect = font.render("Press [E] to open", YELLOW, size=20)
        screen.blit(prompt_surf, (WIDTH // 2 - prompt_rect.width // 2, HEIGHT // 2 + 60))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    # pre_init must run before pygame.init() or the mixer latches onto defaults.
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    pygame.mixer.init(SAMPLE_RATE, -16, 1, 512)
    pygame.mixer.set_num_channels(16)
    pygame.display.set_icon(generate_icon())
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("2.5D Maze Shooter")
    clock = pygame.time.Clock()
    font = pygame.freetype.SysFont("monospace", 20)
    big_font = pygame.freetype.SysFont("monospace", 48)
    sfx = init_sounds()
    textures = generate_textures()
    sfx['music'].set_volume(0.10)
    sfx['music'].play(loops=-1, fade_ms=800)

    state = GameState()
    reset_game(state)

    z_buffer = DepthBuffer()
    pressed_scancodes: set[int] = set()

    _capture_mouse(True)

    running = True
    paused_frame: pygame.Surface | None = None
    while running:
        dt = min(clock.tick(FPS), 50)

        running = handle_events(state, sfx, pressed_scancodes)

        if state.game_over:
            draw_game_over(screen, state, font, big_font)
            pygame.display.flip()
            continue

        if state.paused:
            # Hold the last frame under the overlay; free the mouse and mute.
            if paused_frame is None:
                paused_frame = screen.copy()
                draw_pause_overlay(paused_frame, font, big_font)
                _capture_mouse(False)
                pygame.mixer.pause()
            screen.blit(paused_frame, (0, 0))
            pygame.display.flip()
            continue
        if paused_frame is not None:
            paused_frame = None
            _capture_mouse(True)
            # Don't turn by however far the free cursor travelled.
            pygame.event.clear(pygame.MOUSEMOTION)
            pygame.mixer.unpause()

        keys = pygame.key.get_pressed()
        player_moving = update_player(state, dt, keys, pressed_scancodes, sfx)
        update_combat(state, dt, sfx)
        update_doors(state, dt, sfx)
        update_enemies(state, dt, sfx)
        update_pickups(state, dt, sfx)
        update_rockets(state, dt, sfx)
        check_win_lose(state)

        if state.level_banner_timer > 0:
            state.level_banner_timer -= dt

        draw_frame(state, screen, font, textures, z_buffer, player_moving)
        draw_level_banner(screen, state, big_font)
        pygame.display.flip()

    _capture_mouse(False)
    pygame.quit()
    sys.exit()


def _capture_mouse(captured: bool) -> None:
    """Hide and grab the cursor for mouselook, or hand it back."""
    pygame.mouse.set_visible(not captured)
    pygame.event.set_grab(captured)
