"""Viewmodel animation must remain deterministic and independent of combat state."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator

import pygame
import pytest

from shooter.constants import EMPTY_CLICK_DELAY, HEIGHT, WEAPONS, WIDTH, Weapon
from shooter.render_weapon import draw_weapon
from shooter.weapon_models import weapon_frame
from tests.support import weapon_name


@pytest.fixture
def fresh_weapon_cache() -> Iterator[None]:
    rng_state = random.getstate()
    weapon_frame.cache_clear()
    try:
        yield
    finally:
        weapon_frame.cache_clear()
        random.setstate(rng_state)


def render(
    weapon: Weapon,
    *,
    shooting: bool = False,
    timer: int = 0,
    moving: bool = False,
    time: float = 0.0,
    spin: float = 0.0,
    clip: pygame.Rect | None = None,
) -> pygame.Surface:
    screen = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    if clip is not None:
        screen.set_clip(clip)
    draw_weapon(screen, shooting, timer, moving, time, weapon, spin)
    return screen


def pixels(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGBA")


@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_empty_click_and_unequipped_cooldowns_do_not_animate(weapon: Weapon) -> None:
    idle = pixels(render(weapon))
    for timer in (EMPTY_CLICK_DELAY, WEAPONS[weapon].fire_interval_ms):
        assert pixels(render(weapon, timer=timer)) == idle


@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_firing_changes_each_weapon_and_returns_to_rest(weapon: Weapon) -> None:
    idle = pixels(render(weapon))
    fired = render(weapon, shooting=True, timer=WEAPONS[weapon].fire_interval_ms)
    assert pixels(fired) != idle
    for expired in (0, -16):
        assert pixels(render(weapon, shooting=True, timer=expired)) == idle


@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_walk_sway_works_without_firing(weapon: Weapon) -> None:
    assert pixels(render(weapon, time=0.2)) != pixels(render(weapon, time=0.2, moving=True))


def test_gatling_barrels_coast_without_firing() -> None:
    assert pixels(render(Weapon.GATLING, spin=0)) != pixels(
        render(Weapon.GATLING, spin=math.pi / 12)
    )


@pytest.mark.parametrize(
    "weapon, pose", ((Weapon.PISTOL, 8), (Weapon.SHOTGUN, 12)), ids=("pistol-slide", "shotgun-pump")
)
def test_slide_and_pump_move_while_the_weapon_body_stays_fixed(weapon: Weapon, pose: int) -> None:
    idle = weapon_frame(weapon, 0)
    cycled = weapon_frame(weapon, pose)
    assert pixels(idle) != pixels(cycled)
    # The grip / stock must not move along with the slide or forend.
    fixed_body = pygame.Rect(210, 270, 60, 40)
    assert pixels(idle.subsurface(fixed_body)) == pixels(cycled.subsurface(fixed_body))


@pytest.mark.usefixtures("fresh_weapon_cache")
@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_rendering_does_not_consume_randomness_or_mutate_cached_art(weapon: Weapon) -> None:
    rng_state = random.getstate()
    pose = 1 if weapon == Weapon.NUKE else 0
    model = weapon_frame(weapon, pose)
    assert random.getstate() == rng_state
    before = pixels(model)
    timer = WEAPONS[weapon].fire_interval_ms
    first = render(weapon, shooting=True, timer=timer)
    second = render(weapon, shooting=True, timer=timer)
    assert pixels(first) == pixels(second)
    assert pixels(model) == before
    assert model.get_alpha() == 255
    assert not model.get_locked()
    assert random.getstate() == rng_state

    weapon_frame.cache_clear()
    cold = render(weapon, shooting=True, timer=timer)
    assert pixels(cold) == pixels(first)
    assert random.getstate() == rng_state


@pytest.mark.parametrize("fraction", (0.0, 0.1, 0.4, 0.75, 1.0))
@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_models_and_flashes_preserve_the_aiming_area(fraction: float, weapon: Weapon) -> None:
    aiming_area = pygame.Rect(WIDTH // 2 - 50, HEIGHT // 2 - 50, 100, 100)
    interval = WEAPONS[weapon].fire_interval_ms
    screen = render(weapon, shooting=True, timer=round(interval * fraction), moving=True, time=0.2)
    assert pygame.mask.from_surface(screen).count() > 1000
    assert pygame.mask.from_surface(screen.subsurface(aiming_area)).count() == 0


@pytest.mark.parametrize("weapon", tuple(Weapon), ids=weapon_name)
def test_surface_clipping_applies_to_models_and_firing_effects(weapon: Weapon) -> None:
    clip = pygame.Rect(600, 530, 100, 120)
    timer = WEAPONS[weapon].fire_interval_ms
    reference = render(weapon, shooting=True, timer=timer)
    expected = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    expected.set_clip(clip)
    expected.blit(reference, (0, 0))
    actual = render(weapon, shooting=True, timer=timer, clip=clip)
    assert pixels(actual) == pixels(expected)
