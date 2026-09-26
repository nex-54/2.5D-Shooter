"""Weapon firing, enemy attacks, projectile movement, and explosion damage."""

from __future__ import annotations

import math

from shooter.constants import (
    DAMAGE_COOLDOWN_MS,
    EMPTY_CLICK_DELAY,
    EXPLOSION_DURATION,
    GATLING_SPREAD,
    PISTOL_DAMAGE,
    ROCKET_BLAST_RADIUS,
    ROCKET_HIT_RADIUS,
    ROCKET_MAX_HITS,
    ROCKET_SELF_DAMAGE,
    ROCKET_SPEED,
    SHOTGUN_PELLETS,
    SHOTGUN_RANGE,
    SHOTGUN_SPREAD,
    WEAPONS,
    Weapon,
)
from shooter.entities import Boss, Enemy, Rocket, apply_hit, hitscan
from shooter.state import GameState
from shooter.types import Sfx


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


def _hit(state: GameState, enemy: Enemy, sfx: Sfx, damage: int = 1) -> None:
    """Damage an enemy, counting the kill if this hit finishes it."""
    if apply_hit(enemy, sfx, damage):
        state.kills += 1


def fire_weapon(state: GameState, sfx: Sfx) -> None:
    """Fire click-operated weapons, respecting ownership, ammo, and cooldown."""
    if state.weapon == Weapon.GATLING or not _begin_shot(state, sfx):
        return
    if state.weapon == Weapon.PISTOL:
        sfx["pistol"].play()
        target = hitscan(state.world, state.enemies, state.px, state.py, state.pa)
        if target is not None:
            _hit(state, target, sfx, PISTOL_DAMAGE)
    elif state.weapon == Weapon.SHOTGUN:
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
            if target is not None:
                _hit(state, target, sfx)
    elif state.weapon == Weapon.ROCKETS:
        sfx["rocket_fire"].play()
        rocket = Rocket(state.px, state.py, state.pa)
        state.rockets.append(rocket)
        # Sweep the muzzle offset too: a close wall must detonate on our side.
        _move_rocket(state, rocket, 0.4, sfx)
    elif state.weapon == Weapon.NUKE:
        sfx["explosion"].play()
        for e in state.enemies:
            if not e.alive or isinstance(e, Boss):
                continue
            _hit(state, e, sfx, e.hp)


def update_combat(state: GameState, dt: int, sfx: Sfx) -> None:
    """Handle shoot timer and gatling auto-fire."""
    if state.shoot_timer > 0:
        state.shoot_timer -= dt
    if state.shoot_timer <= 0:
        state.shooting = False

    if state.weapon == Weapon.GATLING and state.mouse_held and not state.game_over:
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
            if target is not None:
                _hit(state, target, sfx)
    else:
        # Released barrels coast to a stop over 400 ms instead of unwinding.
        state.gatling_speed = max(0.0, state.gatling_speed - dt * 0.0002)
    state.gatling_spin = (state.gatling_spin + state.gatling_speed * dt) % (2 * math.pi)


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
                sfx[e.attack_sound].play()
                if state.hp <= 0:
                    break


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
        _hit(state, enemy, sfx, damage)
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
