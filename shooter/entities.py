"""
Game entities: enemies (Enemy, Boss, Scout, Spider), pickups (HealthPack, WeaponPickup),
spawning logic, and combat helpers (hitscan, damage application).
"""

from __future__ import annotations

import math
import random

from shooter.constants import (
    MAX_DEPTH,
    RED,
    SPAWN_ENEMY_MIN_DIST,
    SPAWN_HEALTH_PACK_COUNT,
    SPAWN_PICKUP_MIN_DIST,
    SPAWN_REGULAR_COUNT,
    SPAWN_SCOUT_COUNT,
    SPAWN_SPIDER_COUNT,
    SPAWN_WEAPON_PICKUP_COUNT,
    Weapon,
)
from shooter.map import EXIT_TILE, FLOOR_TILE, MAP_H, MAP_W, LevelState, start_distance
from shooter.types import Sfx


def _blocks_enemy(world: LevelState, x: float, y: float) -> bool:
    """Movement blocker for enemies: also treats the exit tile as solid, since it
    renders as a closed door and an enemy inside it would be invisible."""
    return world.is_obstacle(x, y) or world.tile_at(x, y) == EXIT_TILE


# ---------------------------------------------------------------------------
# Combat helpers
# ---------------------------------------------------------------------------
def hitscan(
    world: LevelState,
    enemies: list[Enemy],
    px: float,
    py: float,
    pa: float,
    spread: float = 0,
    max_range: float = MAX_DEPTH,
) -> Enemy | None:
    """Find the first enemy the shot ray (crosshair direction + spread) enters.

    Enemies are circles of hit_radius, so the target zone shrinks with distance
    like the sprite does. The ray must reach the body unobstructed, which lets
    shots hit the part of an enemy that shows past a wall corner.
    """
    cos_a, sin_a = math.cos(pa + spread), math.sin(pa + spread)
    best_enemy = None
    best_dist = max_range
    for e in enemies:
        if not e.alive:
            continue
        edx = e.x - px
        edy = e.y - py
        along = edx * cos_a + edy * sin_a
        across = abs(edy * cos_a - edx * sin_a)
        if across >= e.hit_radius:
            continue
        half_chord = math.sqrt(e.hit_radius**2 - across**2)
        if along + half_chord <= 0:
            continue  # behind the shooter
        dist = max(0.0, along - half_chord)
        if dist < best_dist and world.has_line_of_sight(
            px, py, px + cos_a * dist, py + sin_a * dist
        ):
            best_enemy = e
            best_dist = dist
    return best_enemy


def apply_hit(enemy: Enemy, sfx: Sfx, damage: int = 1) -> bool:
    """Apply damage to an enemy and play the appropriate sound. Returns True if killed."""
    if not enemy.alive or damage <= 0:
        return False
    if enemy.take_damage(damage):
        sfx[enemy.death_sound].play()
        return True
    sfx["enemy_hurt"].play()
    return False


# ---------------------------------------------------------------------------
# Enemy base class
# ---------------------------------------------------------------------------
class Enemy:
    """A regular grunt. Subclasses retune the per-kind class attributes."""

    max_hp = 3
    speed = 0.0013
    damage = 10
    attack_range = 2.0
    attack_cooldown_duration = 1000
    detect_range = 8
    lose_range = 10
    chase_range = 999
    chase_requires_los = False
    always_alert = False
    wander_speed_mult = 0.5
    wander_timer_range = (1000, 3000)
    wall_wander_timer_range = (500, 1500)
    anim_speed = 0.008
    attack_sound = "enemy_attack"
    death_sound = "enemy_die"
    # Half the drawn body width (torso to arms) in world units, for hitscan.
    # Keep in step with sprite_scale, the drawn height relative to a wall.
    hit_radius = 0.25
    sprite_scale = 0.8
    # Humanoid sprite colors; spiders are drawn with their own palette.
    body_color = (180, 40, 40)
    arm_color = (160, 35, 35)
    minimap_color = RED
    minimap_radius = 3

    def __init__(self, x: float, y: float, rng: random.Random | None = None) -> None:
        self.rng = rng if rng is not None else random.Random()
        self.x = x
        self.y = y
        self.hp = self.max_hp
        self.alive = True
        self.damage_timer = 0
        self.attack_cooldown = 0
        self.alert = self.always_alert
        self.wander_angle = self.rng.uniform(0, 2 * math.pi)
        self.wander_timer = 0
        self.anim_time = self.rng.uniform(0, 2 * math.pi)
        self.moving = False
        self.attacking = False

    def update(self, world: LevelState, px: float, py: float, dt: int) -> None:
        if not self.alive:
            return
        if self.damage_timer > 0:
            self.damage_timer -= dt
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        self.anim_time += dt * self.anim_speed
        self.moving = False
        self.attacking = False

        dx = px - self.x
        dy = py - self.y
        dist = math.hypot(dx, dy)

        if not self.always_alert:
            if dist < self.detect_range and world.has_line_of_sight(self.x, self.y, px, py):
                self.alert = True
            elif dist > self.lose_range:
                self.alert = False

        if self.alert:
            if dist < self.attack_range and world.has_line_of_sight(self.x, self.y, px, py):
                self.attacking = True
                return
            should_chase = dist < self.chase_range
            if should_chase and (
                not self.chase_requires_los or world.has_line_of_sight(self.x, self.y, px, py)
            ):
                self.moving = True
                dx /= dist
                dy /= dist
                speed = self.speed * dt
                nx = self.x + dx * speed
                ny = self.y + dy * speed
                if not _blocks_enemy(world, nx, self.y):
                    self.x = nx
                if not _blocks_enemy(world, self.x, ny):
                    self.y = ny
            else:
                self._wander(world, dt)
        else:
            self._wander(world, dt)

    def _wander(self, world: LevelState, dt: int) -> None:
        """Random wandering behavior."""
        self.wander_timer -= dt
        if self.wander_timer <= 0:
            self.wander_angle = self.rng.uniform(0, 2 * math.pi)
            self.wander_timer = self.rng.randint(*self.wander_timer_range)
        speed = self.speed * self.wander_speed_mult * dt
        wx = math.cos(self.wander_angle) * speed
        wy = math.sin(self.wander_angle) * speed
        nx = self.x + wx
        ny = self.y + wy
        if _blocks_enemy(world, nx, self.y) or _blocks_enemy(world, self.x, ny):
            self.wander_angle = self.rng.uniform(0, 2 * math.pi)
            self.wander_timer = self.rng.randint(*self.wall_wander_timer_range)
        else:
            self.moving = True
            self.x = nx
            self.y = ny

    def take_damage(self, amount: int = 1) -> bool:
        """Return True only when this hit kills a living enemy."""
        if not self.alive or amount <= 0:
            return False
        self.hp = max(0, self.hp - amount)
        self.damage_timer = 150
        if self.hp <= 0:
            self.alive = False
            return True
        return False


# ---------------------------------------------------------------------------
# Enemy variants
# ---------------------------------------------------------------------------
class Boss(Enemy):
    """A large boss enemy guarding the exit."""

    max_hp = 20
    speed = 0.0007
    damage = 15
    attack_range = 2.5
    attack_cooldown_duration = 1200
    chase_range = 12
    chase_requires_los = True
    always_alert = True
    wander_speed_mult = 0.4
    wander_timer_range = (1500, 3500)
    anim_speed = 0.006
    attack_sound = "boss_roar"
    death_sound = "boss_die"
    hit_radius = 0.38
    sprite_scale = 1.2
    body_color = (100, 30, 140)
    arm_color = (80, 25, 120)
    minimap_color = (180, 40, 180)
    minimap_radius = 5


class Scout(Enemy):
    """A fast, nimble enemy with low HP."""

    max_hp = 2
    speed = 0.0026
    damage = 5
    attack_range = 1.8
    attack_cooldown_duration = 600
    detect_range = 10
    lose_range = 12
    wander_speed_mult = 0.6
    wander_timer_range = (600, 2000)
    wall_wander_timer_range = (300, 1000)
    anim_speed = 0.012
    hit_radius = 0.18
    sprite_scale = 0.6
    body_color = (40, 140, 60)
    arm_color = (30, 120, 50)
    minimap_color = (50, 200, 70)
    minimap_radius = 2


class Spider(Enemy):
    """A creepy spider enemy -- fast, low, and hard to hit."""

    max_hp = 4
    speed = 0.002
    damage = 8
    attack_range = 1.5
    attack_cooldown_duration = 700
    detect_range = 9
    lose_range = 11
    wander_speed_mult = 0.6
    wander_timer_range = (400, 1200)
    wall_wander_timer_range = (200, 800)
    anim_speed = 0.014
    attack_sound = "spider_hiss"
    death_sound = "spider_die"
    hit_radius = 0.18
    sprite_scale = 0.55
    minimap_color = (140, 80, 30)


# ---------------------------------------------------------------------------
# Pickups
# ---------------------------------------------------------------------------
class HealthPack:
    def __init__(self, x: float, y: float, rng: random.Random | None = None) -> None:
        self.rng = rng if rng is not None else random.Random()
        self.x = x
        self.y = y
        self.active = True
        self.heal_amount = 25
        self.anim_time = self.rng.uniform(0, 2 * math.pi)

    def update(self, dt: int) -> None:
        self.anim_time += dt * 0.003


class WeaponPickup:
    """A gun lying on the floor. Grants the weapon on first pickup; refills ammo thereafter."""

    def __init__(
        self, x: float, y: float, weapon_type: Weapon, rng: random.Random | None = None
    ) -> None:
        self.rng = rng if rng is not None else random.Random()
        self.x = x
        self.y = y
        self.active = True
        self.weapon_type = weapon_type
        self.anim_time = self.rng.uniform(0, 2 * math.pi)

    def update(self, dt: int) -> None:
        self.anim_time += dt * 0.003


class Rocket:
    """Projectile fired by the rocket launcher. Travels forward; detonates on contact."""

    def __init__(self, x: float, y: float, angle: float) -> None:
        self.x = x
        self.y = y
        self.angle = angle
        self.alive = True
        self.exploded = False
        self.explosion_timer = 0
        self.trail_phase = 0.0


# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------
# Weapons that can lie on the floor; the nuke's single charge comes with the player.
PICKUP_WEAPONS = (Weapon.PISTOL, Weapon.SHOTGUN, Weapon.GATLING, Weapon.ROCKETS)


def spawn_enemies(
    world: LevelState,
    rng: random.Random,
    used: set[tuple[int, int]] | None = None,
    regular_count: int | None = None,
    scout_count: int | None = None,
    spider_count: int | None = None,
    boss_tile: tuple[int, int] | None = None,
) -> list[Enemy]:
    """Place enemies in open cells, away from player start.

    Counts default to the SPAWN_*_COUNT constants. boss_tile is an (int_x, int_y)
    pair excluded from spawn candidates; defaults to this level's boss spawn.
    """
    if used is None:
        used = set()
    if regular_count is None:
        regular_count = SPAWN_REGULAR_COUNT
    if scout_count is None:
        scout_count = SPAWN_SCOUT_COUNT
    if spider_count is None:
        spider_count = SPAWN_SPIDER_COUNT
    if boss_tile is None:
        boss_tx, boss_ty = int(world.boss_spawn[0]), int(world.boss_spawn[1])
    else:
        boss_tx, boss_ty = boss_tile
    # Reject any spot that has line of sight to the player's spawn, so the
    # player sees no enemies when a new level loads.
    psx, psy = world.player_spawn
    spots: list[tuple[float, float]] = []
    hidden_spots: list[tuple[float, float]] = []
    for r in range(MAP_H):
        for c in range(MAP_W):
            if world.maze[r][c] != FLOOR_TILE or (c, r) in used:
                continue
            if c == boss_tx and r == boss_ty:
                continue
            if start_distance(c, r) <= SPAWN_ENEMY_MIN_DIST:
                continue
            pos = (c + 0.5, r + 0.5)
            if world.has_line_of_sight(psx, psy, pos[0], pos[1]):
                spots.append(pos)
            else:
                hidden_spots.append(pos)
    rng.shuffle(hidden_spots)
    rng.shuffle(spots)
    # Prefer hidden (no-LOS) spots; fall back to visible ones only if we run out.
    ordered = hidden_spots + spots
    r_end = regular_count
    s_end = r_end + scout_count
    t_end = s_end + spider_count
    enemies = [Enemy(x, y, random.Random(rng.getrandbits(64))) for x, y in ordered[:r_end]]
    enemies += [Scout(x, y, random.Random(rng.getrandbits(64))) for x, y in ordered[r_end:s_end]]
    enemies += [Spider(x, y, random.Random(rng.getrandbits(64))) for x, y in ordered[s_end:t_end]]
    for x, y in ordered[:t_end]:
        used.add((int(x), int(y)))
    return enemies


def _supply_spots(world: LevelState, used: set[tuple[int, int]]) -> list[tuple[float, float]]:
    """Centers of free floor tiles far enough from the player's start for supplies."""
    return [
        (c + 0.5, r + 0.5)
        for r in range(MAP_H)
        for c in range(MAP_W)
        if world.maze[r][c] == FLOOR_TILE
        and (c, r) not in used
        and start_distance(c, r) > SPAWN_PICKUP_MIN_DIST
    ]


def spawn_health_packs(
    world: LevelState, rng: random.Random, used: set[tuple[int, int]] | None = None
) -> list[HealthPack]:
    """Place health packs in open cells, spread through the maze."""
    if used is None:
        used = set()
    spots = _supply_spots(world, used)
    rng.shuffle(spots)
    n = SPAWN_HEALTH_PACK_COUNT
    packs = [HealthPack(x, y, random.Random(rng.getrandbits(64))) for x, y in spots[:n]]
    for x, y in spots[:n]:
        used.add((int(x), int(y)))
    return packs


def spawn_weapon_pickups(
    world: LevelState, rng: random.Random, used: set[tuple[int, int]] | None = None
) -> list[WeaponPickup]:
    """Place weapon pickups in open cells, guaranteeing at least one of each type."""
    if used is None:
        used = set()
    spots = _supply_spots(world, used)
    rng.shuffle(spots)
    n = min(SPAWN_WEAPON_PICKUP_COUNT, len(spots))
    # Force one of each weapon type so the player can always find & unlock them.
    types = list(PICKUP_WEAPONS[:n])
    while len(types) < n:
        types.append(rng.choice(PICKUP_WEAPONS))
    rng.shuffle(types)
    packs = [
        WeaponPickup(x, y, t, random.Random(rng.getrandbits(64)))
        for (x, y), t in zip(spots[:n], types, strict=True)
    ]
    for x, y in spots[:n]:
        used.add((int(x), int(y)))
    return packs
