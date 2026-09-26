"""
Main game loop — initialization, input handling, game state updates, and draw orchestration.

The game loop is split into focused functions so individual behaviors (movement,
combat, doors, enemies, pickups, rendering) can be located and modified independently.
Mutable gameplay state is owned by GameState, initialized/reset via reset_game().
"""

from __future__ import annotations

import math
import random
import sys
from collections.abc import Callable

import pygame
import pygame.freetype

from shooter import map as gmap
from shooter.constants import (
    BLACK,
    DAMAGE_COOLDOWN_MS,
    DOOR_ANIM_DURATION,
    DOOR_OPEN_DURATION,
    DOOR_RETRY_DELAY,
    EMPTY_CLICK_DELAY,
    EXPLOSION_DURATION,
    EYE_HEIGHT,
    FOOTSTEP_SPRINT_INTERVAL,
    FOOTSTEP_WALK_INTERVAL,
    FPS,
    GATLING_SPREAD,
    GRAVITY,
    HEIGHT,
    INITIAL_AMMO,
    JUMP_VELOCITY,
    MAX_AMMO,
    MOUSE_SENSITIVITY,
    PICKUP_RADIUS,
    PISTOL_DAMAGE,
    PLAYER_MARGIN,
    PLAYER_MAX_HP,
    PLAYER_MOVE_SPEED,
    PLAYER_ROT_SPEED,
    PLAYER_SPRINT_MULT,
    RED,
    ROCKET_BLAST_RADIUS,
    ROCKET_HIT_RADIUS,
    ROCKET_MAX_HITS,
    ROCKET_SELF_DAMAGE,
    ROCKET_SPEED,
    SAMPLE_RATE,
    SHOTGUN_PELLETS,
    SHOTGUN_RANGE,
    SHOTGUN_SPREAD,
    SPAWN_REGULAR_COUNT,
    SPAWN_SCOUT_COUNT,
    SPAWN_SPIDER_COUNT,
    WEAPONS,
    WHITE,
    WIDTH,
    YELLOW,
)
from shooter.entities import (
    Boss,
    Enemy,
    HealthPack,
    Rocket,
    WeaponPickup,
    apply_hit,
    hitscan,
    spawn_enemies,
    spawn_health_packs,
    spawn_weapon_pickups,
)
from shooter.map import BARRIER_TILE, DOOR_TILE, LevelState
from shooter.occlusion import DepthBuffer
from shooter.raycaster import cast_rays
from shooter.render_sprites import Billboard, draw_world_sprites
from shooter.render_ui import draw_crosshair, draw_hud, draw_minimap
from shooter.render_world import draw_3d, draw_floor_ceiling
from shooter.sound import init_sounds
from shooter.textures import generate_icon, generate_textures
from shooter.types import DoorAnim, DoorAnimMap, KeyState, Sfx, Textures
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

        Weapons (see constants.WEAPONS for indices)
            weapon       -- currently equipped weapon index (0..4).
            ammo         -- per-pool ammo counts; index via WEAPONS[weapon].ammo_pool.
            owned        -- which weapons the player has picked up.
            shooting     -- True while the firing animation is playing.
            shoot_timer  -- ms until the next shot is allowed (ROF gate).
            mouse_held   -- True while LMB is down (drives gatling auto-fire).
            gatling_spin -- barrel rotation angle (radians).
            gatling_speed-- barrel speed (rad/ms); coasts down after release.

        Footsteps
            step_timer, step_index -- alternates step0/step1 sounds on move.

        World
            world      -- owned LevelState: maze, doors, exit, and spawn positions.
            level_rng  -- generation/spawning RNG, independent of gameplay and assets.
            rng        -- combat spread RNG, independent of subsequent levels.
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

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        """Set every field to its starting value. Does NOT generate a level."""
        self.level_rng = random.Random(self.seed)
        self.rng = random.Random(self.seed)
        self.world = LevelState()

        # Player position & physics
        self.px = self.world.player_spawn[0]
        self.py = self.world.player_spawn[1]
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
        self.ammo: list[int] = list(INITIAL_AMMO)
        self.owned = [weapon.initially_owned for weapon in WEAPONS]
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

    Preserves ammo and owned/equipped weapons; refills HP and resets level kills.
    Enemy counts scale modestly with level number.
    """
    state.world = gmap.generate_level(level, state.level_rng)

    # Reposition player to the fresh spawn and clear per-level transient state.
    state.px = state.world.player_spawn[0]
    state.py = state.world.player_spawn[1]
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
    boss_tile = (int(state.world.boss_spawn[0]), int(state.world.boss_spawn[1]))
    # Reserve the boss and all supplies before enemies consume the free cells.
    used_tiles: set[tuple[int, int]] = {boss_tile}
    state.health_packs = spawn_health_packs(state.world, state.level_rng, used_tiles)
    state.weapon_pickups = spawn_weapon_pickups(state.world, state.level_rng, used_tiles)
    state.enemies = spawn_enemies(
        state.world,
        state.level_rng,
        used_tiles,
        regular_count=SPAWN_REGULAR_COUNT + bonus,
        scout_count=SPAWN_SCOUT_COUNT + bonus,
        spider_count=SPAWN_SPIDER_COUNT + bonus,
        boss_tile=boss_tile,
    )
    state.boss = Boss(*state.world.boss_spawn, random.Random(state.level_rng.getrandbits(64)))
    state.enemies.append(state.boss)
    used_tiles.add(boss_tile)
    state.total_enemies = len(state.enemies)
    state.rockets = []
    state.gatling_spin = 0.0
    state.gatling_speed = 0.0
    state.step_timer = 0

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
def handle_events(state: GameState, sfx: Sfx, pressed_scancodes: set[int]) -> bool:
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
            weapon_keys = {
                pygame.K_1: 0,
                pygame.K_2: 1,
                pygame.K_3: 2,
                pygame.K_4: 3,
                pygame.K_0: 4,
            }
            if event.key in weapon_keys and not state.game_over:
                new_weapon = weapon_keys[event.key]
                if state.owned[new_weapon] and state.weapon != new_weapon:
                    state.weapon = new_weapon
                    state.shoot_timer = 0
                    state.shooting = False
            if event.scancode == pygame.KSCAN_E and not state.game_over:
                door_pos = state.world.find_door_in_front(state.px, state.py, state.pa)
                if door_pos and door_pos not in state.door_anim:
                    state.door_anim[door_pos] = DoorAnim(
                        phase="opening",
                        progress=0.0,
                        timer=0,
                    )
                    sfx["door_open"].play()
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


def _begin_shot(state: GameState, sfx: Sfx) -> bool:
    """Gate every weapon and consume its ammo/cooldown in one place."""
    if (
        state.game_over
        or state.paused
        or state.hp <= 0
        or not state.owned[state.weapon]
        or state.shoot_timer > 0
    ):
        return False
    weapon = WEAPONS[state.weapon]
    if state.ammo[weapon.ammo_pool] <= 0:
        sfx["empty"].play()
        state.shoot_timer = EMPTY_CLICK_DELAY
        return False
    state.ammo[weapon.ammo_pool] -= 1
    state.shoot_timer = weapon.fire_interval_ms
    state.shooting = True
    return True


def _handle_click_fire(state: GameState, sfx: Sfx) -> None:
    """Fire click-operated weapons, respecting ownership, ammo, and cooldown."""
    if state.weapon == 2 or not _begin_shot(state, sfx):
        return
    if state.weapon == 0:
        sfx["pistol"].play()
        target = hitscan(state.world, state.enemies, state.px, state.py, state.pa)
        if target and apply_hit(target, sfx, PISTOL_DAMAGE):
            state.kills += 1
    elif state.weapon == 1:
        sfx["shotgun"].play()
        for _ in range(SHOTGUN_PELLETS):
            spread = state.rng.uniform(-SHOTGUN_SPREAD, SHOTGUN_SPREAD)
            target = hitscan(
                state.world,
                state.enemies,
                state.px,
                state.py,
                state.pa,
                spread=spread,
                max_range=SHOTGUN_RANGE,
            )
            if target and apply_hit(target, sfx):
                state.kills += 1
    elif state.weapon == 3:
        sfx["rocket_fire"].play()
        rocket = Rocket(state.px, state.py, state.pa)
        state.rockets.append(rocket)
        # Sweep the muzzle offset too: a close wall must detonate on our side.
        _move_rocket(state, rocket, 0.4, sfx)
    elif state.weapon == 4:
        sfx["explosion"].play()
        for e in state.enemies:
            if not e.alive or e.is_boss:
                continue
            if apply_hit(e, sfx, e.hp):
                state.kills += 1


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


def update_combat(state: GameState, dt: int, sfx: Sfx) -> None:
    """Handle shoot timer and gatling auto-fire."""
    if state.shoot_timer > 0:
        state.shoot_timer -= dt
    if state.shoot_timer <= 0:
        state.shooting = False

    if state.weapon == 2 and state.mouse_held and not state.game_over:
        state.gatling_speed = 0.08
        if _begin_shot(state, sfx):
            sfx["gatling"].play()
            target = hitscan(
                state.world,
                state.enemies,
                state.px,
                state.py,
                state.pa,
                spread=state.rng.uniform(-GATLING_SPREAD, GATLING_SPREAD),
            )
            if target and apply_hit(target, sfx):
                state.kills += 1
    else:
        # Released barrels coast to a stop over 400 ms instead of unwinding.
        state.gatling_speed = max(0.0, state.gatling_speed - dt * 0.0002)
    state.gatling_spin = (state.gatling_spin + state.gatling_speed * dt) % (2 * math.pi)


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


def update_enemies(state: GameState, dt: int, sfx: Sfx) -> None:
    """Run enemy AI and apply enemy attacks to the player."""
    if state.damage_cooldown > 0:
        state.damage_cooldown -= dt
    if state.spawn_grace > 0:
        state.spawn_grace -= dt
    for e in state.enemies:
        e.update(state.world, state.px, state.py, dt)
        if e.alive and state.hp > 0 and state.damage_cooldown <= 0 and state.spawn_grace <= 0:
            dist = math.hypot(e.x - state.px, e.y - state.py)
            if (
                dist < e.attack_range
                and e.attack_cooldown <= 0
                and state.world.has_line_of_sight(e.x, e.y, state.px, state.py)
            ):
                state.hp -= e.damage
                e.attack_cooldown = e.attack_cooldown_duration
                state.damage_cooldown = DAMAGE_COOLDOWN_MS
                sfx[
                    "boss_roar" if e.is_boss else ("spider_hiss" if e.is_spider else "enemy_attack")
                ].play()
                if state.hp <= 0:
                    break


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


def _detonate_rocket(state: GameState, rocket: Rocket, sfx: Sfx) -> None:
    """Apply each explosion once, using the same damage rules as hitscan."""
    if rocket.exploded:
        return
    rocket.exploded = True
    rocket.explosion_timer = EXPLOSION_DURATION
    sfx["explosion"].play()
    for enemy in state.enemies:
        if not enemy.alive:
            continue
        distance = math.hypot(enemy.x - rocket.x, enemy.y - rocket.y)
        if distance >= ROCKET_BLAST_RADIUS or not state.world.has_line_of_sight(
            rocket.x, rocket.y, enemy.x, enemy.y
        ):
            continue
        damage = max(1, int(ROCKET_MAX_HITS * (1.0 - distance / ROCKET_BLAST_RADIUS)))
        if apply_hit(enemy, sfx, damage):
            state.kills += 1
    distance = math.hypot(state.px - rocket.x, state.py - rocket.y)
    if (
        distance < ROCKET_BLAST_RADIUS
        and state.damage_cooldown <= 0
        and state.world.has_line_of_sight(rocket.x, rocket.y, state.px, state.py)
    ):
        damage = int(ROCKET_SELF_DAMAGE * (1.0 - distance / ROCKET_BLAST_RADIUS))
        if damage > 0:
            state.hp -= damage
            state.damage_cooldown = DAMAGE_COOLDOWN_MS


def _move_rocket(state: GameState, rocket: Rocket, distance: float, sfx: Sfx) -> None:
    """Sweep a projectile segment and stop at its earliest wall or enemy contact."""
    if rocket.exploded or distance <= 0:
        return
    cos_a, sin_a = math.cos(rocket.angle), math.sin(rocket.angle)
    nx, ny = rocket.x + cos_a * distance, rocket.y + sin_a * distance
    fraction = state.world.wall_hit_fraction(rocket.x, rocket.y, nx, ny)
    hit_distance = distance if fraction is None else fraction * distance
    hit_wall = fraction is not None
    detonate = hit_wall
    for enemy in state.enemies:
        if not enemy.alive:
            continue
        dx, dy = enemy.x - rocket.x, enemy.y - rocket.y
        along = dx * cos_a + dy * sin_a
        across = abs(dy * cos_a - dx * sin_a)
        if across >= ROCKET_HIT_RADIUS:
            continue
        half_chord = math.sqrt(ROCKET_HIT_RADIUS**2 - across**2)
        if along + half_chord < 0:
            continue
        contact = max(0.0, along - half_chord)
        if contact < hit_distance or (contact == hit_distance and not hit_wall):
            hit_distance = contact
            hit_wall = False
            detonate = True
    # Keep wall impacts just inside the last clear space for visibility and splash LOS.
    travel = max(0.0, hit_distance - 1e-6) if hit_wall else hit_distance
    rocket.x += cos_a * travel
    rocket.y += sin_a * travel
    if detonate:
        _detonate_rocket(state, rocket, sfx)


def update_rockets(state: GameState, dt: int, sfx: Sfx) -> None:
    """Advance projectiles and age explosion visuals."""
    for rocket in state.rockets:
        if not rocket.alive:
            continue
        if rocket.exploded:
            rocket.explosion_timer -= dt
            if rocket.explosion_timer <= 0:
                rocket.alive = False
            continue
        rocket.trail_phase += dt * 0.02
        _move_rocket(state, rocket, ROCKET_SPEED * dt, sfx)
    state.rockets = [rocket for rocket in state.rockets if rocket.alive]


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


def check_win_lose(state: GameState) -> None:
    """Check for death and level-exit conditions."""
    if state.hp <= 0:
        state.game_over = True
        return
    if (
        int(state.px) == state.world.exit_pos[0]
        and int(state.py) == state.world.exit_pos[1]
        and state.exit_open
    ):
        # Advance to the next randomly-generated level. Ammo and weapons carry
        # over; HP refills (see start_level).
        start_level(state, state.level + 1)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
def draw_game_over(
    screen: pygame.Surface,
    state: GameState,
    font: pygame.freetype.Font,
    big_font: pygame.freetype.Font,
) -> None:
    """Render the game-over screen (death only — wins now advance levels)."""
    screen.fill(BLACK)
    msg, _ = big_font.render("GAME OVER", RED)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render(
        f"Reached Level {state.level}  -  Kills: {state.kills}/{state.total_enemies}  -  Press R to restart  -  ESC to quit",
        WHITE,
    )
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_level_banner(
    screen: pygame.Surface, state: GameState, big_font: pygame.freetype.Font
) -> None:
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


def draw_pause_overlay(
    screen: pygame.Surface, font: pygame.freetype.Font, big_font: pygame.freetype.Font
) -> None:
    """Dim the frozen frame and show how to resume or quit."""
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 150))
    screen.blit(dim, (0, 0))
    msg, _ = big_font.render("PAUSED", YELLOW)
    screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 40))
    sub, _ = font.render("Esc or click to resume  -  Q to quit", WHITE)
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 30))


def draw_frame(
    state: GameState,
    screen: pygame.Surface,
    font: pygame.freetype.Font,
    textures: Textures,
    z_buffer: DepthBuffer,
    player_moving: bool,
) -> None:
    """Draw one complete gameplay frame (3D view, sprites, HUD)."""
    eye = EYE_HEIGHT + state.jump_height
    walls = cast_rays(state.world, state.px, state.py, state.pa, state.door_anim)
    draw_floor_ceiling(state.world, screen, state.px, state.py, state.pa, textures, eye)
    draw_3d(screen, walls, z_buffer, font, textures, eye, door_anim=state.door_anim)
    billboards = [Billboard("START", *state.world.player_spawn, (20, 20, 80))]
    if state.boss is not None and state.boss.alive:
        billboards.append(Billboard("BOSS", state.boss.x, state.boss.y, (80, 20, 80)))
    draw_world_sprites(
        screen,
        state.px,
        state.py,
        state.pa,
        z_buffer,
        font,
        enemies=state.enemies,
        health_packs=state.health_packs,
        weapon_pickups=state.weapon_pickups,
        rockets=state.rockets,
        billboards=billboards,
        eye_height=eye,
    )
    draw_minimap(
        state.world,
        screen,
        state.px,
        state.py,
        state.pa,
        state.enemies,
        state.health_packs,
        state.weapon_pickups,
        state.rockets,
    )
    draw_crosshair(screen)
    draw_weapon(
        screen,
        state.shooting,
        state.shoot_timer,
        player_moving,
        state.game_time,
        state.weapon,
        state.gatling_spin,
    )
    draw_hud(
        screen,
        font,
        state.hp,
        state.ammo[WEAPONS[state.weapon].ammo_pool],
        state.kills,
        state.total_enemies,
        WEAPONS[state.weapon].name,
        state.level,
    )

    door_pos = state.world.find_door_in_front(state.px, state.py, state.pa)
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
    sfx["music"].set_volume(0.10)
    sfx["music"].play(loops=-1, fade_ms=800)

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
        if not running:
            break

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
        player_moving = update_game(state, dt, keys, pressed_scancodes, sfx)

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
