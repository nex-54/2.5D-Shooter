"""
Billboarded sprite rendering: enemies, health/ammo pickups, and text billboards.

All functions project world-space positions onto the screen, z-buffer-test
against the wall depth buffer, and paint the sprite as pygame primitives.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

import pygame
import pygame.freetype

from shooter.constants import (
    EXPLOSION_DURATION,
    EYE_HEIGHT,
    FOV,
    HALF_FOV,
    HEIGHT,
    MAX_DEPTH,
    WEAPONS,
    WHITE,
    WIDTH,
    Weapon,
    normalize_angle,
)
from shooter.entities import Boss, Enemy, HealthPack, Rocket, Spider, WeaponPickup
from shooter.occlusion import DepthBuffer


class Camera(NamedTuple):
    """The viewpoint every sprite is projected from."""

    x: float
    y: float
    angle: float
    eye_height: float = EYE_HEIGHT


class Billboard(NamedTuple):
    """A world label that participates in sprite depth ordering."""

    label: str
    x: float
    y: float
    bg_color: tuple[int, int, int]


class _Projection(NamedTuple):
    depth: float  # camera depth, the same measure as the wall depth buffer
    screen_x: int


def _project(
    camera: Camera,
    x: float,
    y: float,
    *,
    min_dist: float,
    fov_margin: float,
    max_dist: float = math.inf,
) -> _Projection | None:
    """Project a world point onto the screen, or return None if it can't be seen.

    fov_margin widens the view cone for sprites that extend past their center.
    """
    dx = x - camera.x
    dy = y - camera.y
    dist = math.hypot(dx, dy)
    if dist < min_dist or dist > max_dist:
        return None
    diff = normalize_angle(math.atan2(dy, dx) - camera.angle)
    if abs(diff) > HALF_FOV + fov_margin:
        return None
    depth = dist * math.cos(diff)
    if depth < 0.1:
        return None
    return _Projection(depth, int((diff / FOV + 0.5) * WIDTH))


def _eye_row(depth: float, eye_height: float) -> int:
    """Screen row of standing eye height, where sprites are anchored, at a depth.

    Raising the eye lowers nearby objects more than distant ones."""
    return HEIGHT // 2 + int((eye_height - EYE_HEIGHT) * HEIGHT / depth)


def _shade(color: tuple[int, int, int], shade: float, boost: float = 1.0) -> tuple[int, int, int]:
    return (
        min(255, max(0, int(color[0] * shade * boost))),
        min(255, max(0, int(color[1] * shade * boost))),
        min(255, max(0, int(color[2] * shade * boost))),
    )


def draw_world_sprites(
    screen: pygame.Surface,
    camera: Camera,
    z_buffer: DepthBuffer,
    font: pygame.freetype.Font,
    *,
    enemies: Sequence[Enemy] = (),
    health_packs: Sequence[HealthPack] = (),
    weapon_pickups: Sequence[WeaponPickup] = (),
    rockets: Sequence[Rocket] = (),
    billboards: Sequence[Billboard] = (),
) -> None:
    """Draw all world sprites back to front, sharing the wall clipping buffer."""
    sprites: list[Enemy | HealthPack | WeaponPickup | Rocket | Billboard] = [
        *enemies,
        *health_packs,
        *weapon_pickups,
        *rockets,
        *billboards,
    ]
    px, py = camera.x, camera.y
    cos_a, sin_a = math.cos(camera.angle), math.sin(camera.angle)
    # Camera depth matches the projection and wall buffer, unlike radial distance.
    # Stable ties leave labels over their own enemies at the same world position.
    sprites.sort(key=lambda sprite: (sprite.x - px) * cos_a + (sprite.y - py) * sin_a, reverse=True)
    for sprite in sprites:
        if isinstance(sprite, Enemy):
            draw_enemy(screen, sprite, camera, z_buffer)
        elif isinstance(sprite, HealthPack):
            draw_health_pack(screen, sprite, camera, z_buffer)
        elif isinstance(sprite, WeaponPickup):
            draw_weapon_pickup(screen, sprite, camera, z_buffer)
        elif isinstance(sprite, Rocket):
            draw_rocket(screen, sprite, camera, z_buffer)
        else:
            draw_billboard(screen, font, sprite, camera, z_buffer)


# ---------------------------------------------------------------------------
# Enemy sprites
# ---------------------------------------------------------------------------
def draw_enemy(screen: pygame.Surface, enemy: Enemy, camera: Camera, z_buffer: DepthBuffer) -> None:
    """Draw an enemy, clipping only pixels covered by nearer geometry."""
    if not enemy.alive:
        return
    # Body parts can extend into view even when the center is outside FOV.
    view = _project(camera, enemy.x, enemy.y, min_dist=0.2, fov_margin=0.8)
    if view is None:
        return
    corrected, screen_x = view
    sprite_h = min(int(HEIGHT / corrected * enemy.sprite_scale), HEIGHT * 2)
    sprite_w = max(sprite_h // 2, 4)
    screen_y = _eye_row(corrected, camera.eye_height) - sprite_h // 2
    # Include arms, horns, legs and health bars in the clipping bounds.
    half_w = int(sprite_w * 1.2) + 4
    top_ext = sprite_h // 2 + 4
    bottom_ext = sprite_h + sprite_h // 4 + 4
    bounds = pygame.Rect(screen_x - half_w, screen_y - top_ext, half_w * 2, top_ext + bottom_ext)
    with z_buffer.sprite(screen, bounds, corrected) as layer:
        if layer is None:
            return
        target, origin_x, origin_y = layer
        hit = enemy.damage_timer > 0
        shade = max(0.3, min(1.0, 1.0 - (corrected - 1) / MAX_DEPTH))
        anim = enemy.anim_time
        if enemy.moving:
            walk_cycle = math.sin(anim * 6)
            bob_offset = int(abs(math.sin(anim * 6)) * sprite_h * 0.03)
        elif enemy.attacking:
            walk_cycle = 0
            bob_offset = 0
        else:
            walk_cycle = 0
            bob_offset = int(math.sin(anim * 2) * sprite_h * 0.015)
        attack_phase = (math.sin(anim * 8) * 0.5 + 0.5) if enemy.attacking else 0
        if isinstance(enemy, Spider):
            _draw_spider(
                target,
                enemy,
                screen_x - origin_x,
                screen_y - origin_y,
                sprite_h,
                sprite_w,
                shade,
                hit,
                anim,
                attack_phase,
            )
        else:
            _draw_humanoid(
                target,
                enemy,
                screen_x - origin_x,
                screen_y - origin_y,
                sprite_h,
                sprite_w,
                shade,
                hit,
                walk_cycle,
                bob_offset,
                attack_phase,
            )


def _draw_spider(
    screen: pygame.Surface,
    e: Enemy,
    screen_x: int,
    screen_y: int,
    sprite_h: int,
    sprite_w: int,
    shade: float,
    hit: bool,
    anim: float,
    attack_phase: float,
) -> None:
    """Draw a spider enemy sprite."""
    sp_y = screen_y + sprite_h // 3

    # Hits flash the body shaded white; legs, eyes, and fangs flash pure white.
    body = _shade(WHITE if hit else (70, 40, 20), shade)
    highlight = _shade(WHITE if hit else (100, 60, 30), shade, 1.3)

    # abdomen
    abd_rx = max(sprite_w * 2 // 5, 3)
    abd_ry = max(sprite_h // 5, 3)
    abd_cx = screen_x
    abd_cy = sp_y + sprite_h // 3
    pygame.draw.ellipse(screen, body, (abd_cx - abd_rx, abd_cy - abd_ry, abd_rx * 2, abd_ry * 2))
    if abd_rx > 4:
        pygame.draw.ellipse(
            screen,
            highlight,
            (abd_cx - abd_rx // 2, abd_cy - abd_ry + 2, abd_rx, abd_ry * 2 // 3),
        )
    if abd_rx > 5 and not hit:
        mark_color = _shade((200, 20, 20), shade)
        mw = max(abd_rx // 3, 2)
        mh = max(abd_ry // 2, 2)
        pygame.draw.polygon(
            screen,
            mark_color,
            [
                (abd_cx, abd_cy - mh),
                (abd_cx + mw, abd_cy),
                (abd_cx, abd_cy + mh),
                (abd_cx - mw, abd_cy),
            ],
        )

    # cephalothorax
    ceph_r = max(sprite_w // 4, 3)
    ceph_cx = screen_x
    ceph_cy = sp_y + sprite_h // 6
    pygame.draw.circle(screen, body, (ceph_cx, ceph_cy), ceph_r)
    if ceph_r > 4:
        pygame.draw.circle(
            screen, highlight, (ceph_cx - ceph_r // 4, ceph_cy - ceph_r // 4), ceph_r // 3
        )

    # 8 legs
    leg_thickness = max(2, sprite_w // 16)
    leg_color = WHITE if hit else _shade((50, 25, 10), shade)
    for side in (-1, 1):
        for i in range(4):
            phase_off = i * 0.8 + (0.4 if side > 0 else 0)
            leg_anim = (
                math.sin(anim * 10 + phase_off) * 0.3
                if e.moving
                else math.sin(anim * 2 + phase_off) * 0.08
            )
            base_angle = -0.6 + i * 0.45
            angle = base_angle + leg_anim

            seg1_len = sprite_w * 0.45
            seg2_len = sprite_w * 0.5
            knee_x = int(ceph_cx + side * math.cos(angle) * seg1_len)
            knee_y = int(ceph_cy - abs(math.sin(angle)) * seg1_len * 0.7 - sprite_h * 0.06)
            tip_x = int(knee_x + side * math.cos(angle + 0.5) * seg2_len)
            tip_y = int(ceph_cy + sprite_h * 0.18 + int(abs(leg_anim) * sprite_h * 0.08))

            pygame.draw.line(screen, leg_color, (ceph_cx, ceph_cy), (knee_x, knee_y), leg_thickness)
            pygame.draw.line(screen, leg_color, (knee_x, knee_y), (tip_x, tip_y), leg_thickness)

    # eyes
    if ceph_r > 4:
        eye_color = WHITE if hit else _shade((220, 20, 20), shade)
        eye_size = max(ceph_r // 5, 1)
        for ox, oy in [(-2, -2), (2, -2), (-4, 0), (4, 0)]:
            ex = ceph_cx + ox * eye_size
            ey = ceph_cy - ceph_r // 3 + oy * eye_size // 2
            pygame.draw.circle(screen, eye_color, (ex, ey), eye_size)

    # fangs
    if ceph_r > 5:
        fang_color = WHITE if hit else _shade((180, 160, 130), shade)
        fang_len = ceph_r * 2 // 3
        fang_y_base = ceph_cy + ceph_r // 2
        fang_spread = 2 + int(attack_phase * 3)
        pygame.draw.line(
            screen,
            fang_color,
            (ceph_cx - fang_spread, fang_y_base),
            (ceph_cx - fang_spread - 1, fang_y_base + fang_len),
            max(leg_thickness, 2),
        )
        pygame.draw.line(
            screen,
            fang_color,
            (ceph_cx + fang_spread, fang_y_base),
            (ceph_cx + fang_spread + 1, fang_y_base + fang_len),
            max(leg_thickness, 2),
        )

    # HP bar
    if e.hp < e.max_hp:
        bar_w = sprite_w
        bar_h = max(3, sprite_h // 20)
        bar_y = ceph_cy - ceph_r - bar_h - 4
        bar_x = screen_x - bar_w // 2
        pygame.draw.rect(screen, (60, 0, 0), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * e.hp / e.max_hp)
        pygame.draw.rect(screen, (220, 30, 30), (bar_x, bar_y, fill_w, bar_h))


def _draw_humanoid(
    screen: pygame.Surface,
    e: Enemy,
    screen_x: int,
    screen_y: int,
    sprite_h: int,
    sprite_w: int,
    shade: float,
    hit: bool,
    walk_cycle: float,
    bob_offset: int,
    attack_phase: float,
) -> None:
    """Draw a humanoid enemy sprite (regular, scout, or boss)."""
    is_boss = isinstance(e, Boss)

    # --- Legs ---
    leg_top = screen_y + sprite_h * 3 // 4 - bob_offset
    leg_h = sprite_h // 4
    leg_w = max(sprite_w // 5, 2)
    leg_gap = sprite_w // 4
    leg_color = (40, 40, 40) if not hit else WHITE
    left_leg_offset = int(walk_cycle * sprite_w * 0.2)
    right_leg_offset = -left_leg_offset
    pygame.draw.rect(
        screen,
        leg_color,
        (screen_x - leg_gap - leg_w // 2 + left_leg_offset, leg_top, leg_w, leg_h),
    )
    pygame.draw.rect(
        screen,
        leg_color,
        (screen_x + leg_gap - leg_w // 2 + right_leg_offset, leg_top, leg_w, leg_h),
    )
    boot_h = max(leg_h // 4, 2)
    boot_color = (30, 30, 30) if not hit else WHITE
    pygame.draw.rect(
        screen,
        boot_color,
        (screen_x - leg_gap - leg_w + left_leg_offset, leg_top + leg_h - boot_h, leg_w * 2, boot_h),
    )
    pygame.draw.rect(
        screen,
        boot_color,
        (
            screen_x + leg_gap - leg_w + right_leg_offset,
            leg_top + leg_h - boot_h,
            leg_w * 2,
            boot_h,
        ),
    )

    # --- Torso ---
    torso_top = screen_y + sprite_h * 2 // 7 - bob_offset
    torso_h = sprite_h * 3 // 7
    torso_w = sprite_w
    base = WHITE if hit else e.body_color
    pygame.draw.rect(
        screen, _shade(base, shade), (screen_x - torso_w // 2, torso_top, torso_w, torso_h)
    )
    highlight_w = max(torso_w // 5, 2)
    pygame.draw.rect(
        screen,
        _shade(base, shade, 1.4),
        (screen_x - torso_w // 2, torso_top, highlight_w, torso_h),
    )
    pygame.draw.rect(
        screen,
        _shade(base, shade, 0.5),
        (screen_x + torso_w // 2 - highlight_w, torso_top, highlight_w, torso_h),
    )
    belt_y = torso_top + torso_h - max(torso_h // 8, 2)
    pygame.draw.rect(
        screen,
        (50, 30, 20) if not hit else WHITE,
        (screen_x - torso_w // 2, belt_y, torso_w, max(torso_h // 8, 2)),
    )

    # --- Arms ---
    arm_w = max(torso_w // 5, 2)
    arm_h = torso_h * 3 // 4
    arm_top = torso_top + torso_h // 8
    arm_color = WHITE if hit else _shade(e.arm_color, shade)
    left_arm_swing = int(-walk_cycle * sprite_h * 0.08)
    right_arm_swing = int(walk_cycle * sprite_h * 0.08)
    right_arm_raise = int(attack_phase * arm_h * 0.6)
    pygame.draw.rect(
        screen, arm_color, (screen_x - torso_w // 2 - arm_w, arm_top + left_arm_swing, arm_w, arm_h)
    )
    pygame.draw.rect(
        screen,
        arm_color,
        (screen_x + torso_w // 2, arm_top + right_arm_swing - right_arm_raise, arm_w, arm_h),
    )
    hand_r = max(arm_w * 2 // 3, 2)
    hand_color = WHITE if hit else _shade((200, 160, 120), shade)
    pygame.draw.circle(
        screen,
        hand_color,
        (screen_x - torso_w // 2 - arm_w // 2, arm_top + arm_h + left_arm_swing),
        hand_r,
    )
    pygame.draw.circle(
        screen,
        hand_color,
        (screen_x + torso_w // 2 + arm_w // 2, arm_top + arm_h + right_arm_swing - right_arm_raise),
        hand_r,
    )

    # --- Neck ---
    neck_w = max(torso_w // 5, 2)
    neck_h = max(sprite_h // 16, 2)
    neck_color = WHITE if hit else _shade((200, 160, 120), shade)
    pygame.draw.rect(
        screen, neck_color, (screen_x - neck_w // 2, torso_top - neck_h, neck_w, neck_h)
    )

    # --- Head ---
    head_r = max(sprite_w // 3, 4)
    head_cy = torso_top - neck_h - head_r
    skin_r, skin_g, skin_b = WHITE if hit else _shade((210, 170, 130), shade)
    pygame.draw.circle(screen, (skin_r, skin_g, skin_b), (screen_x, head_cy), head_r)
    if head_r > 6:
        hl_r = head_r // 3
        hl_x = screen_x - head_r // 4
        hl_y = head_cy - head_r // 4
        hl_color = (min(255, skin_r + 40), min(255, skin_g + 40), min(255, skin_b + 40))
        pygame.draw.circle(screen, hl_color, (hl_x, hl_y), hl_r)
    if head_r > 6:
        sh_r = head_r // 3
        sh_x = screen_x + head_r // 4
        sh_y = head_cy + head_r // 4
        sh_color = (max(0, skin_r - 50), max(0, skin_g - 50), max(0, skin_b - 50))
        pygame.draw.circle(screen, sh_color, (sh_x, sh_y), sh_r)

    # --- Eyes ---
    if head_r > 5:
        eye_off = head_r // 3
        eye_r_size = max(head_r // 4, 2)
        pygame.draw.circle(
            screen, (240, 240, 240), (screen_x - eye_off, head_cy - head_r // 6), eye_r_size
        )
        pygame.draw.circle(
            screen, (240, 240, 240), (screen_x + eye_off, head_cy - head_r // 6), eye_r_size
        )
        pupil_r = max(eye_r_size // 2, 1)
        pygame.draw.circle(
            screen, (20, 20, 20), (screen_x - eye_off, head_cy - head_r // 6), pupil_r
        )
        pygame.draw.circle(
            screen, (20, 20, 20), (screen_x + eye_off, head_cy - head_r // 6), pupil_r
        )
        brow_y = head_cy - head_r // 6 - eye_r_size - 1
        brow_w = eye_r_size + 2
        pygame.draw.line(
            screen,
            (40, 20, 20),
            (screen_x - eye_off - brow_w // 2, brow_y - 2),
            (screen_x - eye_off + brow_w // 2, brow_y + 1),
            2,
        )
        pygame.draw.line(
            screen,
            (40, 20, 20),
            (screen_x + eye_off - brow_w // 2, brow_y + 1),
            (screen_x + eye_off + brow_w // 2, brow_y - 2),
            2,
        )

    # --- Mouth ---
    if head_r > 6:
        mouth_y = head_cy + head_r // 3
        mouth_w = head_r // 2
        pygame.draw.arc(
            screen,
            (60, 20, 20),
            (screen_x - mouth_w, mouth_y - mouth_w // 3, mouth_w * 2, mouth_w),
            math.pi,
            2 * math.pi,
            2,
        )

    # --- Boss horns ---
    if is_boss and head_r > 5:
        horn_color = (180, 160, 60) if not hit else WHITE
        horn_h = head_r
        pygame.draw.polygon(
            screen,
            horn_color,
            [
                (screen_x - head_r + 2, head_cy - head_r // 2),
                (screen_x - head_r - horn_h // 2, head_cy - head_r - horn_h),
                (screen_x - head_r // 2, head_cy - head_r + 2),
            ],
        )
        pygame.draw.polygon(
            screen,
            horn_color,
            [
                (screen_x + head_r - 2, head_cy - head_r // 2),
                (screen_x + head_r + horn_h // 2, head_cy - head_r - horn_h),
                (screen_x + head_r // 2, head_cy - head_r + 2),
            ],
        )

    # --- HP bar ---
    if e.hp < e.max_hp:
        bar_w = sprite_w if not is_boss else int(sprite_w * 1.5)
        bar_h = max(3, sprite_h // 20)
        bar_y = head_cy - head_r - bar_h - 4
        if is_boss:
            bar_y -= head_r
        bar_x = screen_x - bar_w // 2
        pygame.draw.rect(screen, (60, 0, 0), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * e.hp / e.max_hp)
        pygame.draw.rect(screen, (220, 30, 30), (bar_x, bar_y, fill_w, bar_h))
        if is_boss and bar_w > 20:
            pygame.draw.rect(screen, (60, 0, 60), (bar_x, bar_y - bar_h - 2, bar_w, bar_h))


# ---------------------------------------------------------------------------
# Billboards & Pickups
# ---------------------------------------------------------------------------
def draw_billboard(
    screen: pygame.Surface,
    font: pygame.freetype.Font,
    billboard: Billboard,
    camera: Camera,
    z_buffer: DepthBuffer,
) -> None:
    """Draw a floating text label at the billboard's world position."""
    view = _project(
        camera, billboard.x, billboard.y, min_dist=0.3, max_dist=MAX_DEPTH, fov_margin=0.1
    )
    if view is None:
        return
    corrected, screen_x = view
    font_size = max(8, min(int(200 / corrected), 60))
    text_surf, text_rect = font.render(billboard.label, WHITE, size=font_size)
    tx = screen_x - text_rect.width // 2
    ty = _eye_row(corrected, camera.eye_height) - text_rect.height // 2
    bg_rect = pygame.Rect(tx - 6, ty - 4, text_rect.width + 12, text_rect.height + 8)
    with z_buffer.sprite(screen, bg_rect, corrected) as layer:
        if layer is None:
            return
        target, origin_x, origin_y = layer
        local_rect = bg_rect.move(-origin_x, -origin_y)
        pygame.draw.rect(target, billboard.bg_color, local_rect)
        pygame.draw.rect(target, WHITE, local_rect, 1)
        target.blit(text_surf, (tx - origin_x, ty - origin_y))


def draw_health_pack(
    screen: pygame.Surface, pack: HealthPack, camera: Camera, z_buffer: DepthBuffer
) -> None:
    """Draw a health pack as a floating 3D cross."""
    if not pack.active:
        return
    view = _project(camera, pack.x, pack.y, min_dist=0.3, max_dist=MAX_DEPTH, fov_margin=0.2)
    if view is None:
        return
    corrected, screen_x = view
    size = max(int(HEIGHT / corrected * 0.25), 6)
    bob = int(math.sin(pack.anim_time) * size * 0.15)
    cy = _eye_row(corrected, camera.eye_height) + bob

    shade = max(0.4, min(1.0, 1.0 - (corrected - 1) / MAX_DEPTH))

    bounds = pygame.Rect(screen_x - size // 2, cy - size // 2, size, size)
    with z_buffer.sprite(screen, bounds, corrected) as layer:
        if layer is None:
            return
        target, origin_x, origin_y = layer
        screen_x -= origin_x
        cy -= origin_y
        box_s = size
        pygame.draw.rect(
            target,
            _shade((220, 220, 220), shade),
            (screen_x - box_s // 2, cy - box_s // 2, box_s, box_s),
        )
        cross_w = max(size // 5, 2)
        cross_h = size * 3 // 4
        cross_color = _shade((200, 30, 30), shade)
        pygame.draw.rect(
            target, cross_color, (screen_x - cross_w // 2, cy - cross_h // 2, cross_w, cross_h)
        )
        pygame.draw.rect(
            target, cross_color, (screen_x - cross_h // 2, cy - cross_w // 2, cross_h, cross_w)
        )

        glow = int(abs(math.sin(pack.anim_time * 2)) * 80 + 40)
        pygame.draw.rect(
            target,
            (glow, glow, glow),
            (screen_x - box_s // 2, cy - box_s // 2, box_s, box_s),
            1,
        )


def draw_weapon_pickup(
    screen: pygame.Surface, pack: WeaponPickup, camera: Camera, z_buffer: DepthBuffer
) -> None:
    """Draw a weapon pickup as a floating gun silhouette with a color-coded halo."""
    if not pack.active:
        return
    view = _project(camera, pack.x, pack.y, min_dist=0.3, max_dist=MAX_DEPTH, fov_margin=0.2)
    if view is None:
        return
    corrected, screen_x = view
    size = max(int(HEIGHT / corrected * 0.42), 14)
    bob = int(math.sin(pack.anim_time * 1.5) * size * 0.1)
    cy = _eye_row(corrected, camera.eye_height) + bob
    shade = max(0.4, min(1.0, 1.0 - (corrected - 1) / MAX_DEPTH))

    # Color-coded pulsing halo so weapon type reads at any distance.
    base = WEAPONS[pack.weapon_type].color
    pulse = abs(math.sin(pack.anim_time * 2))
    halo_r = int(size * (1.0 + pulse * 0.25))
    bounds = pygame.Rect(screen_x - halo_r, cy - halo_r, halo_r * 2, halo_r * 2)
    with z_buffer.sprite(screen, bounds, corrected) as layer:
        if layer is None:
            return
        target, origin_x, origin_y = layer
        screen_x -= origin_x
        cy -= origin_y
        # Close pickups can project far beyond the viewport. Keep the
        # original circle geometry, but allocate only its visible region.
        visible_bounds = bounds.move(-origin_x, -origin_y).clip(target.get_clip())
        center = (screen_x - visible_bounds.x, cy - visible_bounds.y)
        halo_surf = pygame.Surface(visible_bounds.size, pygame.SRCALPHA)
        pygame.draw.circle(
            halo_surf,
            (base[0], base[1], base[2], int(110 + pulse * 50)),
            center,
            halo_r,
        )
        pygame.draw.circle(
            halo_surf,
            (base[0], base[1], base[2], int(60 + pulse * 40)),
            center,
            halo_r,
            max(1, halo_r // 8),
        )
        target.blit(halo_surf, visible_bounds.topleft)

        if pack.weapon_type == Weapon.PISTOL:
            _draw_pistol_icon(target, screen_x, cy, size, shade)
        elif pack.weapon_type == Weapon.SHOTGUN:
            _draw_shotgun_icon(target, screen_x, cy, size, shade)
        elif pack.weapon_type == Weapon.GATLING:
            _draw_gatling_icon(target, screen_x, cy, size, shade)
        else:
            _draw_rocket_icon(target, screen_x, cy, size, shade)


def _draw_pistol_icon(screen: pygame.Surface, cx: int, cy: int, size: int, shade: float) -> None:
    """Pistol silhouette — slide on top, grip at the rear, barrel extending right."""
    metal = _shade((80, 80, 88), shade)
    metal_hi = _shade((130, 130, 138), shade)
    metal_dk = _shade((40, 40, 48), shade)
    wood = _shade((95, 65, 40), shade)
    wood_hi = _shade((130, 90, 55), shade)

    w = size
    h = int(size * 0.8)
    x = cx - w // 2
    y = cy - h // 2

    # Slide + barrel along the top
    slide_h = max(int(h * 0.3), 3)
    pygame.draw.rect(screen, metal, (x, y, w, slide_h))
    pygame.draw.rect(screen, metal_hi, (x, y, w, max(1, slide_h // 3)))
    pygame.draw.rect(screen, metal_dk, (x, y + slide_h - 1, w, 1))
    # muzzle hole at the front
    muzzle_w = max(2, size // 10)
    pygame.draw.rect(
        screen, metal_dk, (x + w - muzzle_w, y + slide_h // 4, muzzle_w, max(1, slide_h // 2))
    )

    # Grip sits at the rear, hanging below the slide
    grip_w = max(int(w * 0.4), 3)
    grip_h = h - slide_h
    pygame.draw.rect(screen, wood, (x, y + slide_h, grip_w, grip_h))
    pygame.draw.rect(screen, wood_hi, (x, y + slide_h, max(1, grip_w // 4), grip_h))
    pygame.draw.rect(screen, _shade((60, 40, 25), shade), (x + grip_w - 1, y + slide_h, 1, grip_h))

    # Trigger + guard just ahead of the grip
    guard_w = max(int(w * 0.2), 2)
    guard_h = max(int(h * 0.22), 2)
    pygame.draw.rect(screen, metal, (x + grip_w, y + slide_h, guard_w, max(2, guard_h // 2)))
    pygame.draw.rect(
        screen,
        metal_dk,
        (x + grip_w + guard_w // 3, y + slide_h + 1, max(1, guard_w // 3), guard_h - 1),
    )


def _draw_gatling_icon(screen: pygame.Surface, cx: int, cy: int, size: int, shade: float) -> None:
    """Gatling silhouette — stubby body + cluster of barrels up front."""
    steel = _shade((95, 95, 105), shade)
    steel_hi = _shade((140, 140, 150), shade)
    steel_dk = _shade((50, 50, 60), shade)
    brass = _shade((180, 150, 60), shade)

    w = size
    h = int(size * 0.75)
    x = cx - w // 2
    y = cy - h // 2

    # Housing (rear chunk)
    house_w = int(w * 0.55)
    house_h = int(h * 0.75)
    hx = x
    hy = y + (h - house_h) // 2
    pygame.draw.rect(screen, steel, (hx, hy, house_w, house_h))
    pygame.draw.rect(screen, steel_hi, (hx, hy, house_w, max(1, house_h // 4)))
    pygame.draw.rect(screen, steel_dk, (hx, hy + house_h - 1, house_w, 1))

    # Ammo belt dangling underneath
    belt_w = max(int(w * 0.3), 3)
    belt_h = max(int(h * 0.2), 2)
    pygame.draw.rect(screen, brass, (hx + 1, hy + house_h, belt_w, belt_h))

    # Barrel cluster (circle + individual barrels hinted)
    bc_x = x + int(w * 0.65)
    bc_r = max(int(h * 0.4), 3)
    pygame.draw.circle(screen, steel_dk, (bc_x, cy), bc_r + 1)
    pygame.draw.circle(screen, steel, (bc_x, cy), bc_r)
    if bc_r >= 4:
        for ang in (0, math.pi / 2, math.pi, 3 * math.pi / 2, math.pi / 4):
            dot = (int(bc_x + math.cos(ang) * bc_r * 0.55), int(cy + math.sin(ang) * bc_r * 0.55))
            pygame.draw.circle(screen, steel_dk, dot, max(1, bc_r // 4))

    # Barrels poking forward
    barrels_w = int(w * 0.25)
    if barrels_w > 0:
        for off in (-bc_r // 2, 0, bc_r // 2):
            pygame.draw.rect(screen, steel, (bc_x, cy + off - 1, barrels_w, 2))


def _draw_shotgun_icon(screen: pygame.Surface, cx: int, cy: int, size: int, shade: float) -> None:
    """Shotgun silhouette — long barrel + wooden stock at the rear."""
    metal = _shade((70, 70, 78), shade)
    metal_hi = _shade((120, 120, 128), shade)
    metal_dk = _shade((35, 35, 45), shade)
    wood = _shade((110, 75, 40), shade)
    wood_hi = _shade((150, 100, 55), shade)

    w = size
    h = int(size * 0.55)
    x = cx - w // 2
    y = cy - h // 2

    # Stock (wood, rear)
    stock_w = int(w * 0.35)
    stock_h = h
    pygame.draw.rect(screen, wood, (x, y, stock_w, stock_h))
    pygame.draw.rect(screen, wood_hi, (x, y, stock_w, max(1, stock_h // 4)))
    # butt pad
    pygame.draw.rect(screen, metal_dk, (x, y, max(2, stock_w // 6), stock_h))

    # Receiver (center dark block)
    recv_w = max(int(w * 0.15), 2)
    recv_h = max(int(h * 0.7), 2)
    rx = x + stock_w
    ry = y + (h - recv_h) // 2
    pygame.draw.rect(screen, metal_dk, (rx, ry, recv_w, recv_h))
    pygame.draw.rect(screen, metal, (rx, ry, recv_w, max(1, recv_h // 3)))

    # Pump (small wooden forend just ahead of receiver)
    pump_w = max(int(w * 0.12), 2)
    pump_h = max(int(h * 0.5), 2)
    pygame.draw.rect(screen, wood, (rx + recv_w, cy - pump_h // 2, pump_w, pump_h))

    # Long barrel
    bar_w = w - stock_w - recv_w - pump_w
    bar_h = max(int(h * 0.3), 2)
    bx = rx + recv_w + pump_w
    by = cy - bar_h // 2
    pygame.draw.rect(screen, metal, (bx, by, bar_w, bar_h))
    pygame.draw.rect(screen, metal_hi, (bx, by, bar_w, max(1, bar_h // 3)))
    pygame.draw.rect(screen, metal_dk, (bx + bar_w - 2, by, 2, bar_h))


def _draw_rocket_icon(screen: pygame.Surface, cx: int, cy: int, size: int, shade: float) -> None:
    """Rocket launcher silhouette — long olive tube with warhead tip and rear cone."""
    tube = _shade((70, 82, 48), shade)
    tube_hi = _shade((105, 118, 70), shade)
    tube_dk = _shade((45, 52, 30), shade)
    warhead = _shade((180, 60, 40), shade)
    metal_dk = _shade((35, 35, 40), shade)

    w = size
    h = int(size * 0.45)
    x = cx - w // 2
    y = cy - h // 2

    # Main tube
    tube_l = x + max(2, w // 8)
    tube_w = int(w * 0.7)
    pygame.draw.rect(screen, tube, (tube_l, y, tube_w, h))
    pygame.draw.rect(screen, tube_hi, (tube_l, y, tube_w, max(1, h // 4)))
    pygame.draw.rect(screen, tube_dk, (tube_l, y + h - max(1, h // 5), tube_w, max(1, h // 5)))

    # Warhead tip at the front
    tip_w = max(int(w * 0.12), 2)
    tip_x = tube_l - tip_w
    pygame.draw.polygon(
        screen,
        warhead,
        [
            (tip_x, y + 1),
            (tip_x, y + h - 1),
            (tip_x - tip_w, cy),
        ],
    )

    # Rear exhaust cone
    cone_w = max(int(w * 0.15), 2)
    cone_x = tube_l + tube_w
    pygame.draw.polygon(
        screen,
        tube_dk,
        [
            (cone_x, y),
            (cone_x + cone_w, y - max(1, h // 5)),
            (cone_x + cone_w, y + h + max(1, h // 5)),
            (cone_x, y + h),
        ],
    )
    pygame.draw.rect(screen, metal_dk, (cone_x + cone_w - 1, y, 1, h))

    # Sight on top
    sight_w = max(int(w * 0.14), 2)
    sight_h = max(int(h * 0.3), 2)
    pygame.draw.rect(screen, metal_dk, (tube_l + tube_w // 3, y - sight_h, sight_w, sight_h))

    # Grip underneath
    grip_w = max(int(w * 0.1), 2)
    grip_h = max(int(h * 0.6), 3)
    pygame.draw.rect(screen, metal_dk, (tube_l + tube_w // 2, y + h, grip_w, grip_h))


def draw_rocket(
    screen: pygame.Surface, rocket: Rocket, camera: Camera, z_buffer: DepthBuffer
) -> None:
    """Draw an in-flight rocket or its explosion burst as a billboard sprite."""
    if not rocket.alive:
        return
    view = _project(camera, rocket.x, rocket.y, min_dist=0.1, fov_margin=0.25)
    if view is None:
        return
    corrected, screen_x = view
    cy = _eye_row(corrected, camera.eye_height)

    if rocket.exploded:
        # Explosion: growing glow that fades.
        prog = 1.0 - max(0.0, rocket.explosion_timer) / EXPLOSION_DURATION
        prog = max(0.0, min(1.0, prog))
        base_size = int(HEIGHT / corrected * 1.6)
        radius = max(6, int(base_size * (0.35 + prog * 0.85)))
        alpha_core = max(0, int(255 * (1.0 - prog)))
        alpha_mid = max(0, int(200 * (1.0 - prog)))
        alpha_out = max(0, int(140 * (1.0 - prog)))
        # Nearby bursts can project to thousands of pixels in radius. Allocate
        # only the visible region, retaining the original circle geometry.
        bounds = pygame.Rect(screen_x - radius, cy - radius, radius * 2, radius * 2)
        with z_buffer.sprite(screen, bounds, corrected) as layer:
            if layer is None:
                return
            target, origin_x, origin_y = layer
            bounds = bounds.move(-origin_x, -origin_y)
            screen_x -= origin_x
            cy -= origin_y
            visible_bounds = bounds.clip(target.get_clip())
            if not visible_bounds:
                return
            center = (screen_x - visible_bounds.x, cy - visible_bounds.y)
            surf = pygame.Surface(visible_bounds.size, pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 90, 20, alpha_out), center, radius)
            pygame.draw.circle(surf, (255, 170, 40, alpha_mid), center, max(2, int(radius * 0.65)))
            pygame.draw.circle(
                surf, (255, 240, 180, alpha_core), center, max(1, int(radius * 0.32))
            )
            target.blit(surf, visible_bounds.topleft)
        return

    # Rocket viewed from behind — player sees the engine bell surrounded
    # by fins, with an exhaust plume radiating toward the camera.
    size = max(10, min(int(HEIGHT / corrected * 0.45), HEIGHT // 2))
    flicker = math.sin(rocket.trail_phase * 4.0) * 0.15 + 1.0

    # Outer exhaust glow — big soft halo behind everything.
    glow_r = int(size * 1.2 * flicker)
    bounds = pygame.Rect(screen_x - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)
    with z_buffer.sprite(screen, bounds, corrected) as layer:
        if layer is None:
            return
        target, origin_x, origin_y = layer
        screen_x -= origin_x
        cy -= origin_y
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 110, 30, 80), (glow_r, glow_r), glow_r)
        pygame.draw.circle(glow, (255, 160, 50, 130), (glow_r, glow_r), max(2, int(glow_r * 0.65)))
        target.blit(glow, (screen_x - glow_r, cy - glow_r))

        # Tail fins (4, cross layout) behind the body.
        fin_len = size // 2
        fin_thick = max(2, size // 6)
        fin_col = (70, 70, 80)
        fin_edge = (110, 110, 120)
        # Horizontal fins
        pygame.draw.rect(
            target,
            fin_col,
            (screen_x - size // 2 - fin_len, cy - fin_thick // 2, fin_len, fin_thick),
        )
        pygame.draw.rect(
            target, fin_col, (screen_x + size // 2, cy - fin_thick // 2, fin_len, fin_thick)
        )
        # Vertical fins
        pygame.draw.rect(
            target,
            fin_col,
            (screen_x - fin_thick // 2, cy - size // 2 - fin_len, fin_thick, fin_len),
        )
        pygame.draw.rect(
            target, fin_col, (screen_x - fin_thick // 2, cy + size // 2, fin_thick, fin_len)
        )
        # Fin highlights
        pygame.draw.line(
            target,
            fin_edge,
            (screen_x - size // 2 - fin_len, cy),
            (screen_x - size // 2, cy),
            1,
        )
        pygame.draw.line(
            target,
            fin_edge,
            (screen_x + size // 2, cy),
            (screen_x + size // 2 + fin_len, cy),
            1,
        )

        # Rocket body — circular cross-section seen end-on.
        body_r = size // 2
        pygame.draw.circle(target, (170, 170, 180), (screen_x, cy), body_r)
        # Shading: lit from upper-left.
        pygame.draw.circle(
            target,
            (210, 210, 220),
            (screen_x - body_r // 3, cy - body_r // 3),
            max(1, body_r // 2),
        )
        pygame.draw.circle(target, (120, 120, 130), (screen_x, cy), body_r, max(1, body_r // 8))

        # Engine bell — dark ring with a brighter interior (the flame).
        bell_r = max(3, int(body_r * 0.6))
        pygame.draw.circle(target, (30, 30, 35), (screen_x, cy), bell_r)
        pygame.draw.circle(target, (60, 60, 65), (screen_x, cy), bell_r, 1)

        # Flame plume coming out of the bell toward the camera.
        plume_r = max(2, int(bell_r * (0.75 + 0.25 * flicker)))
        plume = pygame.Surface((plume_r * 2, plume_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(plume, (255, 180, 60, 230), (plume_r, plume_r), plume_r)
        pygame.draw.circle(
            plume, (255, 230, 140, 255), (plume_r, plume_r), max(1, int(plume_r * 0.65))
        )
        pygame.draw.circle(
            plume, (255, 255, 220, 255), (plume_r, plume_r), max(1, int(plume_r * 0.3))
        )
        target.blit(plume, (screen_x - plume_r, cy - plume_r))
