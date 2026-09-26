"""
Game entities: enemies (Enemy, Boss, Scout, Spider), pickups (HealthPack, WeaponPickup),
spawning logic, and combat helpers (hitscan, damage application).
"""

from __future__ import annotations

import math
import random
from shooter.types import Sfx
from shooter.constants import (
    MAX_DEPTH,
    BOSS_START_X, BOSS_START_Y,
    SPAWN_REGULAR_COUNT, SPAWN_SCOUT_COUNT, SPAWN_SPIDER_COUNT,
    SPAWN_HEALTH_PACK_COUNT, SPAWN_WEAPON_PICKUP_COUNT,
    SPAWN_ENEMY_MIN_DIST, SPAWN_PICKUP_MIN_DIST,
)
from shooter import map as gmap
from shooter.map import MAZE, MAP_H, MAP_W, EXIT_TILE, tile_at, is_obstacle, has_line_of_sight


def _blocks_enemy(x: float, y: float) -> bool:
    """Movement blocker for enemies: also treats the exit tile as solid, since it
    renders as a closed door and an enemy inside it would be invisible."""
    return is_obstacle(x, y) or tile_at(x, y) == EXIT_TILE


# ---------------------------------------------------------------------------
# Combat helpers
# ---------------------------------------------------------------------------
def hitscan(enemies: list[Enemy], px: float, py: float, pa: float,
            spread: float = 0, max_range: float = MAX_DEPTH) -> Enemy | None:
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
        half_chord = math.sqrt(e.hit_radius ** 2 - across ** 2)
        if along + half_chord <= 0:
            continue  # behind the shooter
        dist = max(0.0, along - half_chord)
        if dist < best_dist and has_line_of_sight(px, py, px + cos_a * dist, py + sin_a * dist):
            best_enemy = e
            best_dist = dist
    return best_enemy


def apply_hit(enemy: Enemy, sfx: Sfx) -> bool:
    """Apply damage to an enemy and play the appropriate sound. Returns True if killed."""
    enemy.take_damage()
    if not enemy.alive:
        sfx['boss_die' if enemy.is_boss else ('spider_die' if enemy.is_spider else 'enemy_die')].play()
        return True
    sfx['enemy_hurt'].play()
    return False


# ---------------------------------------------------------------------------
# Enemy base class
# ---------------------------------------------------------------------------
class Enemy:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.hp = 3
        self.max_hp = 3
        self.alive = True
        self.speed = 0.0013
        self.damage_timer = 0
        self.attack_cooldown = 0
        self.alert = False
        self.wander_angle = random.uniform(0, 2 * math.pi)
        self.wander_timer = 0
        self.anim_time = random.uniform(0, 2 * math.pi)
        self.moving = False
        self.attacking = False
        self.is_boss = False
        self.is_scout = False
        self.is_spider = False
        # Behavior parameters (overridden by subclasses)
        self.detect_range = 8
        self.lose_range = 10
        self.attack_range = 2.0
        self.chase_range = 999
        self.chase_requires_los = False
        self.wander_speed_mult = 0.5
        self.anim_speed = 0.008
        self.wander_timer_range = (1000, 3000)
        self.wall_wander_timer_range = (500, 1500)
        self.always_alert = False
        self.damage = 10
        self.attack_cooldown_duration = 1000
        # Half the drawn body width (torso to arms) in world units, for hitscan.
        # Keep in step with the sprite scales in render_sprites.draw_enemies.
        self.hit_radius = 0.25

    def update(self, px: float, py: float, dt: int) -> None:
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
            if dist < self.detect_range and has_line_of_sight(self.x, self.y, px, py):
                self.alert = True
            elif dist > self.lose_range:
                self.alert = False

        if self.alert:
            if dist < self.attack_range and has_line_of_sight(self.x, self.y, px, py):
                self.attacking = True
                return
            should_chase = dist < self.chase_range
            if should_chase and (not self.chase_requires_los or has_line_of_sight(self.x, self.y, px, py)):
                self.moving = True
                dx /= dist
                dy /= dist
                speed = self.speed * dt
                nx = self.x + dx * speed
                ny = self.y + dy * speed
                if not _blocks_enemy(nx, self.y):
                    self.x = nx
                if not _blocks_enemy(self.x, ny):
                    self.y = ny
            else:
                self._wander(dt)
        else:
            self._wander(dt)

    def _wander(self, dt: int) -> None:
        """Random wandering behavior."""
        self.wander_timer -= dt
        if self.wander_timer <= 0:
            self.wander_angle = random.uniform(0, 2 * math.pi)
            self.wander_timer = random.randint(*self.wander_timer_range)
        speed = self.speed * self.wander_speed_mult * dt
        wx = math.cos(self.wander_angle) * speed
        wy = math.sin(self.wander_angle) * speed
        nx = self.x + wx
        ny = self.y + wy
        if _blocks_enemy(nx, self.y) or _blocks_enemy(self.x, ny):
            self.wander_angle = random.uniform(0, 2 * math.pi)
            self.wander_timer = random.randint(*self.wall_wander_timer_range)
        else:
            self.moving = True
            self.x = nx
            self.y = ny

    def take_damage(self) -> None:
        self.hp -= 1
        self.damage_timer = 150
        if self.hp <= 0:
            self.alive = False


# ---------------------------------------------------------------------------
# Enemy variants
# ---------------------------------------------------------------------------
class Boss(Enemy):
    """A large boss enemy guarding the exit."""
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.hp = 20
        self.max_hp = 20
        self.speed = 0.0007
        self.is_boss = True
        self.always_alert = True
        self.alert = True
        self.attack_range = 2.5
        self.chase_range = 12
        self.chase_requires_los = True
        self.wander_speed_mult = 0.4
        self.anim_speed = 0.006
        self.wander_timer_range = (1500, 3500)
        self.damage = 15
        self.attack_cooldown_duration = 1200
        self.hit_radius = 0.38


class Scout(Enemy):
    """A fast, nimble enemy with low HP."""
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.hp = 2
        self.max_hp = 2
        self.speed = 0.0026
        self.is_scout = True
        self.detect_range = 10
        self.lose_range = 12
        self.attack_range = 1.8
        self.wander_speed_mult = 0.6
        self.anim_speed = 0.012
        self.wander_timer_range = (600, 2000)
        self.wall_wander_timer_range = (300, 1000)
        self.damage = 5
        self.attack_cooldown_duration = 600
        self.hit_radius = 0.18


class Spider(Enemy):
    """A creepy spider enemy -- fast, low, and hard to hit."""
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.hp = 4
        self.max_hp = 4
        self.speed = 0.002
        self.is_spider = True
        self.detect_range = 9
        self.lose_range = 11
        self.attack_range = 1.5
        self.wander_speed_mult = 0.6
        self.anim_speed = 0.014
        self.wander_timer_range = (400, 1200)
        self.wall_wander_timer_range = (200, 800)
        self.damage = 8
        self.attack_cooldown_duration = 700
        self.hit_radius = 0.18


# ---------------------------------------------------------------------------
# Pickups
# ---------------------------------------------------------------------------
class HealthPack:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.active = True
        self.heal_amount = 25
        self.anim_time = random.uniform(0, 2 * math.pi)

    def update(self, dt: int) -> None:
        self.anim_time += dt * 0.003


class WeaponPickup:
    """A gun lying on the floor. Grants the weapon on first pickup; refills ammo thereafter."""
    # Ammo granted per weapon type (also serves as the unlock bonus)
    AMOUNTS = (15, 8, 100, 5)

    def __init__(self, x: float, y: float, weapon_type: int) -> None:
        self.x = x
        self.y = y
        self.active = True
        self.weapon_type = weapon_type  # 0=pistol, 1=shotgun, 2=gatling, 3=rockets
        self.anim_time = random.uniform(0, 2 * math.pi)

    @property
    def amounts(self) -> tuple[int, int, int, int]:
        return self.AMOUNTS

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
def spawn_enemies(used: set[tuple[int, int]] | None = None,
                  regular_count: int | None = None,
                  scout_count: int | None = None,
                  spider_count: int | None = None,
                  boss_tile: tuple[int, int] | None = None) -> list[Enemy]:
    """Place enemies in open cells, away from player start.

    Counts default to the SPAWN_*_COUNT constants. boss_tile is an (int_x, int_y)
    pair excluded from spawn candidates; falls back to BOSS_START_X/Y for callers
    still relying on the legacy hardcoded boss location.
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
        boss_tx, boss_ty = int(BOSS_START_X), int(BOSS_START_Y)
    else:
        boss_tx, boss_ty = boss_tile
    # Reject any spot that has line of sight to the player's spawn, so the
    # player sees no enemies when a new level loads.
    psx, psy = gmap.PLAYER_SPAWN
    spots = []
    hidden_spots = []
    for r in range(MAP_H):
        for c in range(MAP_W):
            if MAZE[r][c] != 0 or (c, r) in used:
                continue
            if c == boss_tx and r == boss_ty:
                continue
            if abs(c - 1) + abs(r - 1) <= SPAWN_ENEMY_MIN_DIST:
                continue
            pos = (c + 0.5, r + 0.5)
            if has_line_of_sight(psx, psy, pos[0], pos[1]):
                spots.append(pos)
            else:
                hidden_spots.append(pos)
    random.shuffle(hidden_spots)
    random.shuffle(spots)
    # Prefer hidden (no-LOS) spots; fall back to visible ones only if we run out.
    ordered = hidden_spots + spots
    r_end = regular_count
    s_end = r_end + scout_count
    t_end = s_end + spider_count
    enemies = [Enemy(x, y) for x, y in ordered[:r_end]]
    enemies += [Scout(x, y) for x, y in ordered[r_end:s_end]]
    enemies += [Spider(x, y) for x, y in ordered[s_end:t_end]]
    for x, y in ordered[:t_end]:
        used.add((int(x), int(y)))
    return enemies


def spawn_health_packs(used: set[tuple[int, int]] | None = None) -> list[HealthPack]:
    """Place health packs in open cells, spread through the maze."""
    if used is None:
        used = set()
    spots = []
    for r in range(MAP_H):
        for c in range(MAP_W):
            if MAZE[r][c] == 0 and (c, r) not in used and abs(c - 1) + abs(r - 1) > SPAWN_PICKUP_MIN_DIST:
                spots.append((c + 0.5, r + 0.5))
    random.shuffle(spots)
    n = SPAWN_HEALTH_PACK_COUNT
    packs = [HealthPack(x, y) for x, y in spots[:n]]
    for x, y in spots[:n]:
        used.add((int(x), int(y)))
    return packs


def spawn_weapon_pickups(used: set[tuple[int, int]] | None = None) -> list[WeaponPickup]:
    """Place weapon pickups in open cells, guaranteeing at least one of each type."""
    if used is None:
        used = set()
    spots = []
    for r in range(MAP_H):
        for c in range(MAP_W):
            if MAZE[r][c] == 0 and (c, r) not in used and abs(c - 1) + abs(r - 1) > SPAWN_PICKUP_MIN_DIST:
                spots.append((c + 0.5, r + 0.5))
    random.shuffle(spots)
    n = min(SPAWN_WEAPON_PICKUP_COUNT, len(spots))
    # Force one of each weapon type so the player can always find & unlock them.
    types = [0, 1, 2, 3][:n]
    while len(types) < n:
        types.append(random.randint(0, 3))
    random.shuffle(types)
    packs = [WeaponPickup(x, y, t) for (x, y), t in zip(spots[:n], types)]
    for x, y in spots[:n]:
        used.add((int(x), int(y)))
    return packs
