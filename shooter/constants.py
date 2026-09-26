"""
Global constants, colors, and shared config for the game.
"""

import math
from dataclasses import dataclass
from enum import IntEnum

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1024, 768
FOV = math.pi / 3  # 60 degrees
HALF_FOV = FOV / 2
NUM_RAYS = WIDTH
MAX_DEPTH = 20
FPS = 60
# Heights are in wall heights: the floor is at 0 and the ceiling at 1.
EYE_HEIGHT = 0.5  # camera height while standing

# ---------------------------------------------------------------------------
# Minimap
# ---------------------------------------------------------------------------
MINIMAP_SCALE = 6  # each tile = 6 px on minimap
MINIMAP_MARGIN = 16

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (200, 50, 50)
GREEN = (50, 200, 50)
BLUE = (70, 130, 200)
GRAY = (100, 100, 100)
DARK = (40, 40, 40)
YELLOW = (240, 220, 60)
CEIL = (60, 60, 80)
FLOOR = (80, 70, 60)

# ---------------------------------------------------------------------------
# Textures / Audio
# ---------------------------------------------------------------------------
TEX_SIZE = 64
SAMPLE_RATE = 22050


def normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi]."""
    angle = angle % (2 * math.pi)
    if angle > math.pi:
        angle -= 2 * math.pi
    return angle


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
PLAYER_MAX_HP = 100
PLAYER_MOVE_SPEED = 0.003
PLAYER_ROT_SPEED = 0.002
PLAYER_SPRINT_MULT = 1.8
PLAYER_MARGIN = 0.2
MOUSE_SENSITIVITY = 0.003

# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
# Peaks near 0.4 wall heights after 300 ms: over barriers, under the ceiling.
JUMP_VELOCITY = 0.0027
GRAVITY = 0.000009


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------
class Weapon(IntEnum):
    """Weapon ids, which index WEAPONS and the player's owned flags."""

    PISTOL = 0
    SHOTGUN = 1
    GATLING = 2
    ROCKETS = 3
    NUKE = 4


@dataclass(frozen=True)
class WeaponDefinition:
    name: str
    ammo_pool: int
    fire_interval_ms: int
    pickup_ammo: int
    initially_owned: bool = False


# Indexed by Weapon. Pistol and gatling share ammo pool 0.
WEAPONS = (
    WeaponDefinition("Pistol", 0, 200, 15, True),
    WeaponDefinition("Shotgun", 1, 600, 8),
    WeaponDefinition("Gatling", 0, 60, 100),
    WeaponDefinition("Rockets", 2, 800, 5),
    WeaponDefinition("Nuke", 3, 1200, 0, True),
)
INITIAL_AMMO = (50, 0, 0, 1)
MAX_AMMO = (999, 50, 30, 1)
EMPTY_CLICK_DELAY = 200  # ms before another empty-click sound

# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------
DAMAGE_COOLDOWN_MS = 500
PICKUP_RADIUS = 0.6
PISTOL_DAMAGE = 2  # damage per pistol shot
SHOTGUN_PELLETS = 8
SHOTGUN_SPREAD = 0.1  # max pellet angle off the crosshair (radians)
SHOTGUN_RANGE = 6
GATLING_SPREAD = 0.08
ROCKET_SPEED = 0.008  # world units per ms
ROCKET_HIT_RADIUS = 0.6  # direct-hit proximity to enemies
ROCKET_BLAST_RADIUS = 3.0  # splash radius
ROCKET_MAX_HITS = 12  # damage at the epicenter
ROCKET_SELF_DAMAGE = 30  # max hp damage to player at the epicenter
EXPLOSION_DURATION = 320  # ms of explosion visual

# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
FOOTSTEP_WALK_INTERVAL = 350  # ms between footstep sounds
FOOTSTEP_SPRINT_INTERVAL = 200
DOOR_OPEN_DURATION = 5000  # ms before a door auto-closes
DOOR_RETRY_DELAY = 500  # ms to retry closing an occupied door
DOOR_ANIM_DURATION = 400  # ms for a door to slide open or closed
LEVEL_BANNER_DURATION = 1200  # ms the "LEVEL N" banner stays up

# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------
SPAWN_REGULAR_COUNT = 7
SPAWN_SCOUT_COUNT = 5
SPAWN_SPIDER_COUNT = 4
SPAWN_HEALTH_PACK_COUNT = 6
SPAWN_WEAPON_PICKUP_COUNT = 8
SPAWN_ENEMY_MIN_DIST = 5  # manhattan distance from player start
SPAWN_PICKUP_MIN_DIST = 3
