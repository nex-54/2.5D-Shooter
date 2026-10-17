"""Shared world, input, sound, and rendering helpers for tests."""

from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from typing import NamedTuple, cast
from unittest.mock import MagicMock, patch

import pygame

from shooter.constants import EXPLOSION_DURATION, HEIGHT, WIDTH, Weapon
from shooter.entities import HealthPack, Rocket, WeaponPickup
from shooter.input import handle_events
from shooter.map import MAP_H, MAP_W, LevelState
from shooter.render_sprites import Billboard
from shooter.state import GameState
from shooter.types import Sfx

BACKGROUND = (17, 29, 41)


class SoundMocks(defaultdict[str, MagicMock]):
    """Keep separate, spec-checked sound mocks for each effect name."""

    def __init__(self) -> None:
        super().__init__(lambda: MagicMock(spec=pygame.mixer.Sound))

    @property
    def sfx(self) -> Sfx:
        # The mocks stand in for pygame's native Sound instances without audio setup.
        return cast(Sfx, self)


def open_world() -> LevelState:
    return LevelState(
        maze=[
            [int(x in (0, MAP_W - 1) or y in (0, MAP_H - 1)) for x in range(MAP_W)]
            for y in range(MAP_H)
        ]
    )


class Keys:
    def __init__(self, *down: int) -> None:
        self.down = set(down)

    def __getitem__(self, key: int) -> bool:
        return key in self.down


def send_events(state: GameState, sfx: Sfx, pressed: set[int], *events: pygame.event.Event) -> bool:
    """Deliver one event batch through handle_events; returns False when the game quits."""
    with patch("shooter.input.pygame.event.get", return_value=list(events)):
        return handle_events(state, sfx, pressed)


def weapon_name(weapon: Weapon) -> str:
    """Readable pytest id for a Weapon parameter."""
    return weapon.name.lower()


def make_screen() -> pygame.Surface:
    screen = pygame.Surface((WIDTH, HEIGHT))
    screen.fill(BACKGROUND)
    return screen


@contextmanager
def surface_allocations() -> Generator[MagicMock, None, None]:
    """Record new surfaces, failing any larger than the viewport before allocating it."""
    surface_type = pygame.Surface

    def bounded_surface(size: tuple[int, int], flags: int = 0) -> pygame.Surface:
        assert size[0] <= WIDTH
        assert size[1] <= HEIGHT
        return surface_type(size, flags)

    allocate = MagicMock(side_effect=bounded_surface)
    # Replacing pygame.Surface itself also records DepthBuffer's partial-sprite layers.
    with patch("pygame.Surface", allocate):
        yield allocate


def exploding_rocket(x: float, y: float) -> Rocket:
    """An explosion with a quarter of its duration left; its core is a quarter opaque."""
    rocket = Rocket(x, y, 0.0)
    rocket.exploded = True
    rocket.explosion_timer = EXPLOSION_DURATION // 4
    return rocket


class ForegroundSprites(NamedTuple):
    """One still sprite of each non-enemy kind at the same spot."""

    health: HealthPack
    weapon: WeaponPickup
    rocket: Rocket
    explosion: Rocket
    label: Billboard


def foreground_sprites(x: float, y: float = 5.5) -> ForegroundSprites:
    health = HealthPack(x, y)
    weapon = WeaponPickup(x, y, Weapon.SHOTGUN)
    health.anim_time = weapon.anim_time = 0.0
    label = Billboard("TEST", x, y, (20, 20, 80))
    return ForegroundSprites(health, weapon, Rocket(x, y, 0.0), exploding_rocket(x, y), label)
