"""Verify hitscan, attack protection, damage accounting, and gatling spin."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from shooter.combat import update_combat, update_enemies
from shooter.constants import DAMAGE_COOLDOWN_MS, PLAYER_MAX_HP, Weapon
from shooter.entities import Boss, Enemy, Scout, Spider, apply_hit, hitscan
from shooter.map import LevelState
from shooter.state import GameState
from tests.support import SoundMocks


@pytest.mark.parametrize(
    "radius_fraction, hits", ((0.95, True), (1.05, False)), ids=("inside", "outside")
)
@pytest.mark.parametrize("distance", (0.8, 3.0, 8.0, 15.0))
def test_hit_zone_matches_the_body_width_at_any_distance(
    radius_fraction: float, hits: bool, distance: float, world: LevelState
) -> None:
    enemy = Enemy(2.5 + distance, 5.5)
    across = enemy.hit_radius * radius_fraction
    aim = math.asin(across / distance)
    assert (hitscan(world, [enemy], 2.5, 5.5, aim) is enemy) is hits


def test_far_misses_miss_and_point_blank_body_shots_hit(world: LevelState) -> None:
    # A fixed 0.15 rad cone hit the first and missed the second.
    far = Enemy(2.5 + 8 * math.cos(0.14), 5.5 + 8 * math.sin(0.14))
    assert hitscan(world, [far], 2.5, 5.5, 0.0) is None
    near = Enemy(2.5 + 0.8 * math.cos(0.17), 5.5 + 0.8 * math.sin(0.17))
    assert hitscan(world, [near], 2.5, 5.5, 0.0) is near


def test_nearer_enemy_beside_the_line_does_not_take_the_shot(world: LevelState) -> None:
    beside = Enemy(5.5, 5.9)
    target = Enemy(8.5, 5.5)
    assert hitscan(world, [beside, target], 2.5, 5.5, 0.0) is target
    assert hitscan(world, [beside, target], 2.5, 5.5, math.atan2(0.4, 3.0)) is beside


def test_bigger_bodies_are_easier_to_hit(world: LevelState) -> None:
    aim = math.asin(0.25 / 5.0)
    assert hitscan(world, [Boss(7.5, 5.5)], 2.5, 5.5, aim) is not None
    assert hitscan(world, [Scout(7.5, 5.5)], 2.5, 5.5, aim) is None


def test_shots_hit_the_part_of_an_enemy_showing_past_a_corner(world: LevelState) -> None:
    world.maze[4][3] = 1
    px, py = 1.5, 5.5
    center = math.radians(-43)
    enemy = Enemy(px + 3.5 * math.cos(center), py + 3.5 * math.sin(center))
    assert not world.has_line_of_sight(px, py, enemy.x, enemy.y)
    assert hitscan(world, [enemy], px, py, center) is None
    # Aiming 3 degrees above the corner still passes through the body.
    assert hitscan(world, [enemy], px, py, math.radians(-46)) is enemy


def test_shots_do_not_hit_enemies_behind_the_shooter(world: LevelState) -> None:
    assert hitscan(world, [Enemy(1.5, 5.5)], 2.5, 5.5, 0.0) is None


def test_damage_cooldown_blocks_other_attackers_until_it_expires(
    sounds: SoundMocks, state: GameState
) -> None:
    first = Enemy(state.px + 0.5, state.py)
    second = Enemy(state.px, state.py + 0.5)
    state.enemies = [first, second]

    update_enemies(state, 16, sounds.sfx)
    assert state.hp == PLAYER_MAX_HP - first.damage
    assert state.damage_cooldown == DAMAGE_COOLDOWN_MS
    assert first.attack_cooldown == first.attack_cooldown_duration
    assert second.attack_cooldown == 0
    sounds["enemy_attack"].play.assert_called_once()

    update_enemies(state, DAMAGE_COOLDOWN_MS - 1, sounds.sfx)
    assert state.hp == PLAYER_MAX_HP - first.damage
    assert state.damage_cooldown == 1
    assert second.attack_cooldown == 0
    sounds["enemy_attack"].play.assert_called_once()

    update_enemies(state, 1, sounds.sfx)
    assert state.hp == PLAYER_MAX_HP - first.damage - second.damage
    assert state.damage_cooldown == DAMAGE_COOLDOWN_MS
    assert first.attack_cooldown > 0
    assert second.attack_cooldown == second.attack_cooldown_duration
    assert sounds["enemy_attack"].play.call_count == 2


def test_released_barrels_coast_forward_to_a_stop() -> None:
    state = GameState()
    state.weapon = Weapon.GATLING
    state.mouse_held = True
    sfx = MagicMock()
    for _ in range(20):
        update_combat(state, 16, sfx)
    state.mouse_held = False

    steps: list[float] = []
    for _ in range(40):
        before = state.gatling_spin
        update_combat(state, 16, sfx)
        steps.append((state.gatling_spin - before) % (2 * math.pi))
    assert steps[0] > 0.0
    assert all((step < math.pi for step in steps))
    assert all((a >= b for a, b in zip(steps, steps[1:], strict=False)))
    assert steps[-1] == 0.0


@pytest.mark.parametrize(
    "enemy_type, sound",
    ((Enemy, "enemy_die"), (Spider, "spider_die"), (Boss, "boss_die")),
    ids=("enemy", "spider", "boss"),
)
def test_multi_damage_plays_one_sound_and_reports_death_only_once(
    enemy_type: type[Enemy], sound: str
) -> None:
    enemy = enemy_type(5.5, 5.5)
    sounds = SoundMocks()
    sfx = sounds.sfx
    assert apply_hit(enemy, sfx, enemy.hp + 10)
    assert enemy.hp == 0
    assert not enemy.alive
    sounds[sound].play.assert_called_once()
    assert not apply_hit(enemy, sfx, 10)
    sounds[sound].play.assert_called_once()
    sounds["enemy_hurt"].play.assert_not_called()


def test_nonlethal_damage_and_zero_damage() -> None:
    enemy = Enemy(5.5, 5.5)
    sounds = SoundMocks()
    sfx = sounds.sfx
    assert not apply_hit(enemy, sfx, 2)
    assert enemy.hp == 1
    assert enemy.alive
    sounds["enemy_hurt"].play.assert_called_once()
    assert not apply_hit(enemy, sfx, 0)
    assert enemy.hp == 1
    sounds["enemy_hurt"].play.assert_called_once()
