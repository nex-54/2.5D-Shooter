"""Simulation state and lifecycle: level loading, restarts, and win/lose transitions."""

from __future__ import annotations

import random

from shooter import map as gmap
from shooter.constants import (
    INITIAL_AMMO,
    LEVEL_BANNER_DURATION,
    PLAYER_MAX_HP,
    SPAWN_GRACE_DURATION,
    SPAWN_REGULAR_COUNT,
    SPAWN_SCOUT_COUNT,
    SPAWN_SPIDER_COUNT,
    WEAPONS,
    Weapon,
)
from shooter.entities import (
    Boss,
    Enemy,
    HealthPack,
    Rocket,
    WeaponPickup,
    spawn_enemies,
    spawn_health_packs,
    spawn_weapon_pickups,
)
from shooter.map import LevelState
from shooter.types import DoorAnimMap


class GameState:
    """All mutable game state, grouped by concern.

    Lifecycle:
        GameState()           -- construct (calls reset())
        s.enter_level(w, n)   -- move into world w as level n, clearing per-level state
        start_level(s, n)     -- generate level n, enter it, and spawn entities
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
            god_mode        -- cheat toggle preventing all player damage; survives levels.
            damage_cooldown -- ms of i-frames remaining after taking a hit.
            kills           -- enemies killed this level (drives HUD "X / Y").
            cheat_buffer    -- recent letter key presses, cleared on pause/level entry.

        Weapons (see constants.Weapon and constants.WEAPONS)
            weapon       -- currently equipped Weapon.
            ammo         -- per-pool ammo counts; index via WEAPONS[weapon].ammo_pool.
            owned        -- which weapons the player has picked up.
            shooting     -- True while the firing animation is playing.
            weapon_cooldowns -- ms until each weapon can fire, including unequipped ones.
            shoot_timer  -- cooldown of the equipped weapon (ROF gate).
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

        self.weapon: Weapon = Weapon.PISTOL
        self.ammo: list[int] = list(INITIAL_AMMO)
        self.owned = [weapon.initially_owned for weapon in WEAPONS]
        self.god_mode = False

        self.step_index = 0
        self.game_time = 0.0
        self.game_over = False
        self.paused = False
        self.enter_level(LevelState(), 1)

    def enter_level(self, world: LevelState, level: int) -> None:
        """Stand the player in world as level number level, with per-level state cleared.

        Entity lists start empty; start_level spawns them.
        """
        self.world = world
        self.level = level

        self.spawn_player()

        self.hp = PLAYER_MAX_HP
        self.damage_cooldown = 0
        self.kills = 0
        self.cheat_buffer = ""

        self.shooting = False
        self.weapon_cooldowns: list[int] = [0] * len(WEAPONS)
        self.mouse_held = False
        self.gatling_spin = 0.0
        self.gatling_speed = 0.0

        self.step_timer = 0
        self.door_anim: DoorAnimMap = {}
        self.level_banner_timer = 0
        self.spawn_grace = 0

        self.enemies: list[Enemy] = []
        self.boss: Boss | None = None
        self.total_enemies = 0
        self.health_packs: list[HealthPack] = []
        self.weapon_pickups: list[WeaponPickup] = []
        self.rockets: list[Rocket] = []

    def spawn_player(self) -> None:
        """Stand the player at this level's spawn point, facing angle 0."""
        self.px, self.py = self.world.player_spawn
        self.pa = 0.0
        self.jump_vel = 0.0
        self.jump_height = 0.0
        self.on_ground = True

    @property
    def shoot_timer(self) -> int:
        """Remaining cooldown for the equipped weapon, shared with its animation."""
        return self.weapon_cooldowns[self.weapon]

    @shoot_timer.setter
    def shoot_timer(self, remaining: int) -> None:
        self.weapon_cooldowns[self.weapon] = remaining

    def switch_weapon(self, weapon: Weapon) -> None:
        """Equip a different weapon without resetting either weapon's cooldown."""
        if weapon == self.weapon:
            return
        self.weapon = weapon
        self.shooting = False

    @property
    def exit_open(self) -> bool:
        """The exit unlocks once the level boss is dead."""
        return self.boss is not None and not self.boss.alive


def start_level(state: GameState, level: int) -> None:
    """Generate a new procedural level and (re)spawn all entities.

    Preserves ammo and owned/equipped weapons; refills HP and resets level kills.
    Enemy counts scale modestly with level number.
    """
    state.enter_level(gmap.generate_level(level, state.level_rng), level)

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
    )
    state.boss = Boss(*state.world.boss_spawn, random.Random(state.level_rng.getrandbits(64)))
    state.enemies.append(state.boss)
    state.total_enemies = len(state.enemies)

    state.level_banner_timer = LEVEL_BANNER_DURATION
    state.spawn_grace = SPAWN_GRACE_DURATION


def reset_game(state: GameState) -> None:
    """Full game reset after death: reinitialize state and start level 1."""
    state.reset()
    start_level(state, 1)


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
        start_level(state, state.level + 1)
