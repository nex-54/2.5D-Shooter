"""
First-person weapon rendering — draws the pistol, gatling gun, and shotgun viewmodels.
"""

from __future__ import annotations

import math
import random

import pygame

from shooter.constants import HEIGHT, WEAPONS, WIDTH, Weapon


def _cooldown(weapon: Weapon, shoot_timer: int) -> float:
    """Share of the weapon's fire interval still to run: 1.0 on firing, <= 0 once ready."""
    return shoot_timer / WEAPONS[weapon].fire_interval_ms


def draw_gatling(
    screen: pygame.Surface,
    shooting: bool,
    shoot_timer: int,
    player_moving: bool,
    game_time: float,
    spin: float,
) -> None:
    """Draw a gatling gun with spinning barrels."""
    cx = WIDTH // 2 + 100
    by = HEIGHT + 30

    # --- Animation offsets ---
    if player_moving:
        bob_x = int(math.sin(game_time * 5) * 5)
        bob_y = int(abs(math.sin(game_time * 10)) * 4)
    else:
        bob_x = int(math.sin(game_time * 1.2) * 2)
        bob_y = int(math.sin(game_time * 1.8) * 2)

    recoil_x = 0
    recoil_y = 0
    if shooting:
        recoil_x = random.randint(-3, 3)
        recoil_y = random.randint(-2, 4)

    ox = cx + bob_x + recoil_x
    oy = by + bob_y + recoil_y

    # --- Hands ---
    hand_skin = (200, 160, 120)
    pygame.draw.ellipse(screen, hand_skin, (ox - 65, oy - 140, 30, 35))
    pygame.draw.ellipse(screen, hand_skin, (ox - 30, oy - 80, 45, 45))
    for i in range(4):
        fy = oy - 100 + i * 10
        pygame.draw.ellipse(screen, hand_skin, (ox - 15, fy, 12, 10))

    # --- Main body / housing ---
    housing_l = ox - 55
    housing_t = oy - 165
    housing_w = 50
    housing_h = 100
    pygame.draw.rect(screen, (60, 60, 65), (housing_l, housing_t, housing_w, housing_h))
    pygame.draw.rect(screen, (80, 80, 85), (housing_l, housing_t, 8, housing_h))
    pygame.draw.rect(screen, (40, 40, 45), (housing_l + housing_w - 8, housing_t, 8, housing_h))
    pygame.draw.rect(screen, (75, 75, 80), (housing_l, housing_t, housing_w, 6))

    # --- Barrel cluster ---
    barrel_cx = ox - 30
    barrel_cy = oy - 200
    barrel_len = 70
    num_barrels = 6
    barrel_radius = 18

    pygame.draw.circle(screen, (50, 50, 55), (barrel_cx, barrel_cy), barrel_radius + 6)
    pygame.draw.circle(screen, (65, 65, 70), (barrel_cx, barrel_cy), barrel_radius + 6, 2)

    for i in range(num_barrels):
        angle = spin + (i * 2 * math.pi / num_barrels)
        bx = barrel_cx + int(math.cos(angle) * barrel_radius)
        by_b = barrel_cy + int(math.sin(angle) * barrel_radius)
        pygame.draw.circle(screen, (45, 45, 50), (bx, by_b), 5)
        pygame.draw.circle(screen, (25, 25, 30), (bx, by_b), 3)
        pygame.draw.rect(screen, (50, 50, 55), (bx - 3, barrel_cy - barrel_len, 6, barrel_len))

    pygame.draw.circle(screen, (70, 70, 75), (barrel_cx, barrel_cy), 6)
    pygame.draw.circle(screen, (40, 40, 45), (barrel_cx, barrel_cy), 3)

    for i in range(num_barrels):
        angle = spin + (i * 2 * math.pi / num_barrels)
        bx = barrel_cx + int(math.cos(angle) * barrel_radius)
        pygame.draw.circle(screen, (35, 35, 40), (bx, barrel_cy - barrel_len), 4)
        pygame.draw.circle(screen, (20, 20, 20), (bx, barrel_cy - barrel_len), 2)

    # --- Ammo belt / feed ---
    belt_x = housing_l + housing_w
    belt_y = housing_t + 20
    pygame.draw.rect(screen, (70, 60, 30), (belt_x, belt_y, 20, 60))
    for i in range(6):
        ly = belt_y + 4 + i * 9
        pygame.draw.rect(screen, (90, 80, 40), (belt_x + 2, ly, 16, 5))
        pygame.draw.rect(screen, (50, 45, 20), (belt_x + 2, ly + 5, 16, 2))

    # --- Rear grip ---
    grip_l = ox - 20
    grip_t = oy - 68
    pygame.draw.rect(screen, (50, 40, 30), (grip_l, grip_t, 20, 55))
    pygame.draw.rect(screen, (65, 52, 38), (grip_l, grip_t, 4, 55))
    pygame.draw.rect(screen, (35, 28, 20), (grip_l + 16, grip_t, 4, 55))
    for i in range(5):
        gy = grip_t + 6 + i * 9
        pygame.draw.line(screen, (40, 30, 22), (grip_l + 3, gy), (grip_l + 17, gy), 1)

    # --- Front grip ---
    fg_l = ox - 60
    fg_t = oy - 135
    pygame.draw.rect(screen, (55, 45, 35), (fg_l, fg_t, 15, 35))
    pygame.draw.rect(screen, (70, 58, 42), (fg_l, fg_t, 4, 35))

    # --- Muzzle flash ---
    if shooting and _cooldown(Weapon.GATLING, shoot_timer) > 0.5:
        flash_x = barrel_cx
        flash_y = barrel_cy - barrel_len - 20
        flash_surf = pygame.Surface((120, 120), pygame.SRCALPHA)
        pygame.draw.circle(flash_surf, (255, 180, 30, 80), (60, 60), 50)
        pygame.draw.circle(flash_surf, (255, 220, 80, 140), (60, 60), 30)
        pygame.draw.circle(flash_surf, (255, 255, 200, 200), (60, 60), 12)
        screen.blit(flash_surf, (flash_x - 60, flash_y - 60))
        for a in range(0, 360, 30):
            rad = math.radians(a + game_time * 800)
            ex = flash_x + int(math.cos(rad) * 40)
            ey = flash_y + int(math.sin(rad) * 40)
            pygame.draw.line(screen, (255, 240, 100), (flash_x, flash_y), (ex, ey), 2)


def draw_shotgun(
    screen: pygame.Surface, shooting: bool, shoot_timer: int, player_moving: bool, game_time: float
) -> None:
    """Draw a pump-action shotgun."""
    cx = WIDTH // 2 + 80
    by = HEIGHT + 30

    if player_moving:
        bob_x = int(math.sin(game_time * 6) * 6)
        bob_y = int(abs(math.sin(game_time * 12)) * 5)
    else:
        bob_x = int(math.sin(game_time * 1.3) * 2)
        bob_y = int(math.sin(game_time * 1.8) * 2)

    recoil_y = 0
    pump_offset = 0
    t = _cooldown(Weapon.SHOTGUN, shoot_timer)
    if t > 0:
        if t > 0.75:
            kick = (t - 0.75) / 0.25
            recoil_y = int(kick * 45)
        elif t > 0.4:
            pump_offset = int((1 - (t - 0.4) / 0.35) * 25)
        else:
            pump_offset = int(t / 0.4 * 25)

    ox = cx + bob_x
    oy = by + bob_y + recoil_y

    # --- Hand ---
    hand_skin = (200, 160, 120)
    pygame.draw.ellipse(screen, hand_skin, (ox - 50, oy - 90, 60, 50))
    for i in range(4):
        fy = oy - 115 + i * 11
        pygame.draw.ellipse(screen, hand_skin, (ox - 30, fy, 13, 11))
    pygame.draw.ellipse(screen, hand_skin, (ox - 55, oy - 170 + pump_offset, 35, 30))

    # --- Stock ---
    stock_l = ox - 25
    stock_t = oy - 60
    pygame.draw.rect(screen, (80, 55, 30), (stock_l, stock_t, 30, 70))
    for i in range(6):
        gy = stock_t + 8 + i * 10
        pygame.draw.line(screen, (65, 42, 22), (stock_l + 3, gy), (stock_l + 27, gy), 1)
    pygame.draw.rect(screen, (100, 70, 38), (stock_l, stock_t, 5, 70))
    pygame.draw.rect(screen, (55, 38, 20), (stock_l + 25, stock_t, 5, 70))
    pygame.draw.rect(screen, (40, 40, 45), (stock_l - 2, stock_t + 60, 34, 10))

    # --- Receiver ---
    recv_l = ox - 27
    recv_t = oy - 110
    recv_w = 34
    recv_h = 55
    pygame.draw.rect(screen, (55, 55, 60), (recv_l, recv_t, recv_w, recv_h))
    pygame.draw.rect(screen, (70, 70, 75), (recv_l, recv_t, 6, recv_h))
    pygame.draw.rect(screen, (38, 38, 42), (recv_l + recv_w - 6, recv_t, 6, recv_h))
    pygame.draw.rect(screen, (30, 30, 35), (recv_l + 8, recv_t + 10, 16, 12))
    pygame.draw.arc(screen, (50, 50, 55), (recv_l + 5, recv_t + 35, 22, 20), 0, math.pi, 2)
    pygame.draw.rect(screen, (45, 45, 50), (recv_l + 14, recv_t + 38, 4, 12))

    # --- Barrel ---
    barrel_l = ox - 18
    barrel_t = oy - 230
    barrel_w = 16
    barrel_h = 125
    pygame.draw.rect(screen, (50, 50, 55), (barrel_l, barrel_t, barrel_w, barrel_h))
    pygame.draw.rect(screen, (65, 65, 70), (barrel_l, barrel_t, 4, barrel_h))
    pygame.draw.rect(screen, (35, 35, 40), (barrel_l + barrel_w - 4, barrel_t, 4, barrel_h))
    pygame.draw.circle(screen, (20, 20, 20), (barrel_l + barrel_w // 2, barrel_t), 6)
    pygame.draw.circle(screen, (40, 40, 45), (barrel_l + barrel_w // 2, barrel_t), 6, 1)

    # --- Pump / forend ---
    pump_l = ox - 30
    pump_t = oy - 175 + pump_offset
    pump_w = 24
    pump_h = 40
    pygame.draw.rect(screen, (90, 65, 35), (pump_l, pump_t, pump_w, pump_h))
    for i in range(4):
        gy = pump_t + 5 + i * 9
        pygame.draw.line(screen, (70, 48, 25), (pump_l + 3, gy), (pump_l + pump_w - 3, gy), 1)
    pygame.draw.rect(screen, (110, 80, 42), (pump_l, pump_t, 4, pump_h))
    pygame.draw.rect(screen, (65, 45, 25), (pump_l + pump_w - 4, pump_t, 4, pump_h))

    # --- Front sight ---
    pygame.draw.rect(screen, (80, 80, 85), (barrel_l + barrel_w // 2 - 2, barrel_t - 6, 4, 6))

    # --- Muzzle flash ---
    if shooting and t > 0.75:
        flash_x = barrel_l + barrel_w // 2
        flash_y = barrel_t - 20
        flash_surf = pygame.Surface((140, 140), pygame.SRCALPHA)
        pygame.draw.circle(flash_surf, (255, 180, 30, 90), (70, 70), 60)
        pygame.draw.circle(flash_surf, (255, 220, 80, 150), (70, 70), 35)
        pygame.draw.circle(flash_surf, (255, 255, 200, 220), (70, 70), 14)
        screen.blit(flash_surf, (flash_x - 70, flash_y - 70))
        for a in range(0, 360, 25):
            rad = math.radians(a + game_time * 600)
            ex = flash_x + int(math.cos(rad) * 50)
            ey = flash_y + int(math.sin(rad) * 50)
            pygame.draw.line(screen, (255, 230, 120), (flash_x, flash_y), (ex, ey), 2)


def _draw_pistol(
    screen: pygame.Surface, shooting: bool, shoot_timer: int, player_moving: bool, game_time: float
) -> None:
    """Draw the pistol viewmodel."""
    cx = WIDTH // 2 + 120
    by = HEIGHT + 20

    if player_moving:
        bob_x = int(math.sin(game_time * 7) * 8)
        bob_y = int(abs(math.sin(game_time * 14)) * 6)
    else:
        bob_x = int(math.sin(game_time * 1.5) * 3)
        bob_y = int(math.sin(game_time * 2) * 2)

    recoil_y = 0
    t = _cooldown(Weapon.PISTOL, shoot_timer)
    if t > 0:
        if t > 0.7:
            kick = (t - 0.7) / 0.3
            recoil_y = int(kick * 30)
        else:
            recoil_y = int(t / 0.7 * 8)

    ox = cx + bob_x
    oy = by + bob_y + recoil_y

    # --- Hand ---
    hand_skin = (200, 160, 120)
    hand_dark = (170, 130, 95)
    pygame.draw.ellipse(screen, hand_skin, (ox - 45, oy - 80, 70, 55))
    pygame.draw.ellipse(screen, hand_dark, (ox - 48, oy - 70, 20, 35))
    for i in range(4):
        fy = oy - 105 + i * 12
        pygame.draw.ellipse(screen, hand_skin, (ox - 28, fy, 14, 12))

    # --- Slide ---
    slide_l = ox - 22
    slide_t = oy - 175
    slide_w = 28
    slide_h = 85
    pygame.draw.rect(screen, (55, 55, 60), (slide_l, slide_t, slide_w, slide_h))
    pygame.draw.rect(screen, (75, 75, 80), (slide_l, slide_t, 6, slide_h))
    pygame.draw.rect(screen, (35, 35, 40), (slide_l + slide_w - 6, slide_t, 6, slide_h))
    pygame.draw.rect(screen, (80, 80, 85), (slide_l, slide_t, slide_w, 4))
    for i in range(5):
        sy = slide_t + 8 + i * 7
        pygame.draw.line(screen, (40, 40, 45), (slide_l + 2, sy), (slide_l + slide_w - 2, sy), 1)
    pygame.draw.rect(screen, (30, 30, 35), (slide_l + 6, slide_t + 30, 14, 10))

    # --- Barrel ---
    barrel_x = ox - 10
    barrel_t = slide_t - 20
    pygame.draw.rect(screen, (50, 50, 55), (barrel_x, barrel_t, 14, 24))
    pygame.draw.circle(screen, (15, 15, 15), (barrel_x + 7, barrel_t), 5)
    pygame.draw.circle(screen, (30, 30, 30), (barrel_x + 7, barrel_t), 5, 1)

    # --- Frame ---
    frame_l = ox - 20
    frame_t = oy - 92
    frame_w = 24
    frame_h = 30
    pygame.draw.rect(screen, (65, 65, 65), (frame_l, frame_t, frame_w, frame_h))
    pygame.draw.rect(screen, (85, 85, 85), (frame_l, frame_t, 5, frame_h))
    pygame.draw.arc(screen, (60, 60, 60), (frame_l + 2, frame_t + 12, 20, 22), 0, math.pi, 2)
    pygame.draw.rect(screen, (45, 45, 50), (frame_l + 10, frame_t + 14, 4, 12))

    # --- Grip ---
    grip_l = ox - 18
    grip_t = oy - 64
    grip_w = 22
    grip_h = 50
    pygame.draw.rect(screen, (50, 40, 30), (grip_l, grip_t, grip_w, grip_h))
    for i in range(6):
        gy = grip_t + 6 + i * 7
        pygame.draw.line(screen, (40, 30, 22), (grip_l + 3, gy), (grip_l + grip_w - 3, gy), 1)
    pygame.draw.rect(screen, (65, 52, 38), (grip_l, grip_t, 4, grip_h))
    pygame.draw.rect(screen, (35, 28, 20), (grip_l + grip_w - 4, grip_t, 4, grip_h))
    pygame.draw.rect(screen, (55, 55, 60), (grip_l + 2, grip_t + grip_h - 2, grip_w - 4, 6))

    # --- Details ---
    pygame.draw.rect(screen, (50, 50, 55), (slide_l + slide_w - 4, slide_t + slide_h - 12, 8, 12))
    pygame.draw.rect(screen, (90, 90, 95), (barrel_x + 5, barrel_t - 4, 4, 5))
    pygame.draw.rect(screen, (90, 90, 95), (slide_l + 4, slide_t - 3, 4, 4))
    pygame.draw.rect(screen, (90, 90, 95), (slide_l + slide_w - 8, slide_t - 3, 4, 4))

    # --- Muzzle flash ---
    if shooting and t > 0.75:
        flash_x = barrel_x + 7
        flash_y = barrel_t - 15
        flash_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.circle(flash_surf, (255, 200, 50, 100), (40, 40), 35)
        pygame.draw.circle(flash_surf, (255, 230, 100, 160), (40, 40), 20)
        pygame.draw.circle(flash_surf, (255, 255, 220, 220), (40, 40), 10)
        screen.blit(flash_surf, (flash_x - 40, flash_y - 40))
        for angle in range(0, 360, 45):
            rad = math.radians(angle + game_time * 500)
            ex = flash_x + int(math.cos(rad) * 28)
            ey = flash_y + int(math.sin(rad) * 28)
            pygame.draw.line(screen, (255, 240, 150), (flash_x, flash_y), (ex, ey), 2)


def _draw_rocket_launcher(
    screen: pygame.Surface, shooting: bool, shoot_timer: int, player_moving: bool, game_time: float
) -> None:
    """Draw a shoulder-fired rocket launcher viewmodel, tube pointing forward (up on screen)."""
    cx = WIDTH // 2 + 90
    by = HEIGHT + 30

    if player_moving:
        bob_x = int(math.sin(game_time * 4) * 5)
        bob_y = int(abs(math.sin(game_time * 8)) * 5)
    else:
        bob_x = int(math.sin(game_time * 1.1) * 2)
        bob_y = int(math.sin(game_time * 1.5) * 2)

    # Recoil kicks the tube downward briefly after firing.
    recoil_y = 0
    t = _cooldown(Weapon.ROCKETS, shoot_timer)
    if t > 0:
        if t > 0.8:
            kick = (t - 0.8) / 0.2
            recoil_y = int(kick * 50)
        else:
            recoil_y = int(t * 8)

    ox = cx + bob_x
    oy = by + bob_y + recoil_y

    olive_lt = (100, 110, 65)
    olive = (70, 80, 45)
    olive_dk = (45, 52, 30)
    olive_sh = (55, 63, 38)
    metal_dk = (35, 35, 40)
    metal = (60, 60, 65)
    metal_hi = (95, 95, 100)
    hand_skin = (200, 160, 120)
    hand_dark = (170, 130, 95)

    # --- Main tube (vertical, held alongside the shoulder) ---
    tube_w = 70
    tube_h = 240
    tube_l = ox - tube_w // 2
    tube_t = oy - tube_h - 60
    pygame.draw.rect(screen, olive, (tube_l, tube_t, tube_w, tube_h))
    # Left-edge highlight / right-edge shadow for cylindrical shading
    pygame.draw.rect(screen, olive_lt, (tube_l, tube_t, 12, tube_h))
    pygame.draw.rect(screen, olive_sh, (tube_l + tube_w - 10, tube_t, 10, tube_h))
    pygame.draw.rect(screen, olive_dk, (tube_l + tube_w - 4, tube_t, 4, tube_h))
    # Reinforcement bands across the tube
    for i in range(4):
        by_band = tube_t + 30 + i * 55
        pygame.draw.rect(screen, olive_dk, (tube_l, by_band, tube_w, 4))
        pygame.draw.rect(screen, olive_lt, (tube_l, by_band, tube_w, 1))

    # --- Muzzle (front opening at the top) ---
    muzzle_w = tube_w + 10
    muzzle_h = 18
    muzzle_l = tube_l - 5
    muzzle_t = tube_t - muzzle_h
    pygame.draw.rect(screen, metal_dk, (muzzle_l, muzzle_t, muzzle_w, muzzle_h))
    pygame.draw.rect(screen, metal, (muzzle_l, muzzle_t, muzzle_w, 4))
    # Dark inner bore (ellipse for perspective)
    bore_inset = 8
    pygame.draw.ellipse(
        screen,
        (18, 18, 20),
        (muzzle_l + bore_inset, muzzle_t + 3, muzzle_w - bore_inset * 2, muzzle_h + 6),
    )
    pygame.draw.ellipse(
        screen,
        (8, 8, 10),
        (muzzle_l + bore_inset + 4, muzzle_t + 6, muzzle_w - (bore_inset + 4) * 2, muzzle_h),
    )

    # --- Warhead tip peeking out of the bore when not firing ---
    if shoot_timer < 150:
        warhead_w = tube_w - 28
        warhead_x = tube_l + (tube_w - warhead_w) // 2
        warhead_y = muzzle_t - 6
        pygame.draw.ellipse(screen, (180, 60, 40), (warhead_x, warhead_y, warhead_w, 14))
        pygame.draw.polygon(
            screen,
            (210, 80, 50),
            [
                (warhead_x, warhead_y + 4),
                (warhead_x + warhead_w, warhead_y + 4),
                (warhead_x + warhead_w // 2, warhead_y - 14),
            ],
        )
        # tip highlight
        pygame.draw.line(
            screen,
            (240, 150, 100),
            (warhead_x + warhead_w // 2 - 1, warhead_y - 10),
            (warhead_x + warhead_w // 2 - 1, warhead_y + 2),
            2,
        )

    # --- Rear exhaust cone (bottom of tube, flared backblast vent) ---
    rear_top = tube_t + tube_h
    rear_spread = 18
    pygame.draw.polygon(
        screen,
        olive_dk,
        [
            (tube_l, rear_top),
            (tube_l - rear_spread, rear_top + 34),
            (tube_l + tube_w + rear_spread, rear_top + 34),
            (tube_l + tube_w, rear_top),
        ],
    )
    pygame.draw.polygon(
        screen,
        olive,
        [
            (tube_l + 4, rear_top),
            (tube_l - rear_spread + 10, rear_top + 28),
            (tube_l + tube_w + rear_spread - 10, rear_top + 28),
            (tube_l + tube_w - 4, rear_top),
        ],
    )
    # Dark opening inside the cone
    pygame.draw.ellipse(
        screen,
        (15, 15, 18),
        (tube_l - rear_spread + 8, rear_top + 22, tube_w + rear_spread * 2 - 16, 14),
    )

    # --- Iron sight on top of the tube ---
    sight_w = 14
    sight_h = 18
    sight_l = tube_l + tube_w // 2 - sight_w // 2
    sight_t = tube_t + 40
    pygame.draw.rect(screen, metal_dk, (sight_l, sight_t, sight_w, sight_h))
    pygame.draw.rect(screen, metal, (sight_l, sight_t, sight_w, 4))
    # front blade peg
    pygame.draw.rect(screen, metal_hi, (sight_l + sight_w // 2 - 1, sight_t - 6, 2, 6))

    # --- Pistol-style trigger grip under the tube ---
    grip_w = 28
    grip_h = 60
    grip_l = tube_l + tube_w // 2 - grip_w // 2 + 4
    grip_t = rear_top - 18
    pygame.draw.rect(screen, olive_dk, (grip_l, grip_t, grip_w, grip_h))
    pygame.draw.rect(screen, olive_sh, (grip_l, grip_t, 5, grip_h))
    for i in range(5):
        gy = grip_t + 8 + i * 10
        pygame.draw.line(screen, (30, 36, 22), (grip_l + 3, gy), (grip_l + grip_w - 3, gy), 1)
    # Trigger guard (a small arc ahead of the grip)
    guard_l = grip_l - 14
    guard_t = grip_t + 4
    pygame.draw.arc(
        screen, metal_dk, (guard_l, guard_t, grip_w + 10, 30), -math.pi / 2, math.pi / 2, 3
    )
    pygame.draw.rect(screen, metal_dk, (grip_l - 4, guard_t + 8, 6, 10))

    # --- Firing hand wrapping the grip ---
    pygame.draw.ellipse(screen, hand_skin, (grip_l - 12, grip_t + 18, 40, 46))
    pygame.draw.ellipse(screen, hand_dark, (grip_l - 10, grip_t + 24, 14, 34))
    for i in range(4):
        fy = grip_t + 8 + i * 10
        pygame.draw.ellipse(screen, hand_skin, (grip_l + grip_w - 6, fy, 14, 10))
    # Thumb over the top of the grip
    pygame.draw.ellipse(screen, hand_skin, (grip_l + 2, grip_t - 4, 22, 14))

    # --- Forward support hand on the tube ---
    fwd_hand_x = tube_l - 22
    fwd_hand_y = tube_t + tube_h - 110
    pygame.draw.ellipse(screen, hand_skin, (fwd_hand_x, fwd_hand_y, 42, 36))
    pygame.draw.ellipse(screen, hand_dark, (fwd_hand_x + 4, fwd_hand_y + 8, 14, 22))
    for i in range(4):
        fy = fwd_hand_y - 6 + i * 11
        pygame.draw.ellipse(screen, hand_skin, (fwd_hand_x + 28, fy, 14, 11))

    # --- Muzzle flash + backblast on fire ---
    if shooting and t > 0.75:
        flash_cx = tube_l + tube_w // 2
        flash_cy = muzzle_t - 10
        flash_surf = pygame.Surface((220, 220), pygame.SRCALPHA)
        pygame.draw.circle(flash_surf, (255, 140, 40, 120), (110, 110), 95)
        pygame.draw.circle(flash_surf, (255, 200, 80, 180), (110, 110), 60)
        pygame.draw.circle(flash_surf, (255, 240, 180, 220), (110, 110), 26)
        screen.blit(flash_surf, (flash_cx - 110, flash_cy - 110))
        for a in range(0, 360, 30):
            rad = math.radians(a + game_time * 700)
            ex = flash_cx + int(math.cos(rad) * 60)
            ey = flash_cy + int(math.sin(rad) * 60)
            pygame.draw.line(screen, (255, 220, 120), (flash_cx, flash_cy), (ex, ey), 2)
        # Backblast puff out of the rear vent
        back_cx = tube_l + tube_w // 2
        back_cy = rear_top + 60
        back_surf = pygame.Surface((180, 180), pygame.SRCALPHA)
        pygame.draw.circle(back_surf, (210, 210, 210, 120), (90, 90), 75)
        pygame.draw.circle(back_surf, (240, 200, 140, 180), (90, 90), 40)
        screen.blit(back_surf, (back_cx - 90, back_cy - 90))


def _draw_nuke_detonator(
    screen: pygame.Surface, shooting: bool, shoot_timer: int, player_moving: bool, game_time: float
) -> None:
    """Draw a handheld detonator box with a big red button."""
    cx = WIDTH // 2 + 90
    by = HEIGHT + 30

    if player_moving:
        bob_x = int(math.sin(game_time * 5) * 4)
        bob_y = int(abs(math.sin(game_time * 10)) * 4)
    else:
        bob_x = int(math.sin(game_time * 1.2) * 2)
        bob_y = int(math.sin(game_time * 1.6) * 2)

    pressed = shooting and shoot_timer > 0
    press_off = 6 if pressed else 0

    ox = cx + bob_x
    oy = by + bob_y

    hand_skin = (200, 160, 120)
    hand_dark = (170, 130, 95)

    box_w = 140
    box_h = 90
    box_l = ox - box_w // 2
    box_t = oy - 160
    pygame.draw.rect(screen, (80, 60, 30), (box_l, box_t, box_w, box_h))
    pygame.draw.rect(screen, (110, 85, 45), (box_l, box_t, box_w, 6))
    pygame.draw.rect(screen, (55, 40, 20), (box_l, box_t + box_h - 6, box_w, 6))
    pygame.draw.rect(screen, (100, 78, 40), (box_l, box_t, 5, box_h))
    pygame.draw.rect(screen, (50, 38, 18), (box_l + box_w - 5, box_t, 5, box_h))
    for i in range(4):
        sx = box_l + 10 + i * 40
        pygame.draw.circle(screen, (180, 180, 60), (sx, box_t + 10), 3)
        pygame.draw.circle(screen, (180, 180, 60), (sx, box_t + box_h - 10), 3)

    label_l = box_l + 14
    label_t = box_t + 24
    pygame.draw.rect(screen, (200, 200, 180), (label_l, label_t, 44, 40))
    pygame.draw.rect(screen, (40, 40, 40), (label_l, label_t, 44, 40), 2)
    for i in range(4):
        ly = label_t + 6 + i * 8
        pygame.draw.line(screen, (60, 60, 60), (label_l + 4, ly), (label_l + 40, ly), 1)

    btn_cx = box_l + box_w - 40
    btn_cy = box_t + box_h // 2 + press_off
    pygame.draw.circle(screen, (40, 20, 20), (btn_cx, btn_cy + 4), 22)
    pygame.draw.circle(screen, (200, 40, 40), (btn_cx, btn_cy), 20)
    pygame.draw.circle(screen, (255, 120, 120), (btn_cx - 6, btn_cy - 6), 6)
    pygame.draw.circle(screen, (120, 20, 20), (btn_cx, btn_cy), 20, 2)

    pygame.draw.ellipse(screen, hand_skin, (box_l - 20, box_t + box_h - 10, 60, 50))
    pygame.draw.ellipse(screen, hand_dark, (box_l - 16, box_t + box_h + 2, 22, 32))
    pygame.draw.ellipse(screen, hand_skin, (box_l + box_w - 40, box_t + box_h - 10, 60, 50))
    for i in range(3):
        pygame.draw.ellipse(
            screen, hand_skin, (box_l + box_w - 10 + i * 4, box_t + box_h - 20 + i * 6, 12, 16)
        )

    if shooting and _cooldown(Weapon.NUKE, shoot_timer) > 0.75:
        glow = pygame.Surface((120, 120), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 80, 80, 120), (60, 60), 55)
        pygame.draw.circle(glow, (255, 200, 200, 200), (60, 60), 25)
        screen.blit(glow, (btn_cx - 60, btn_cy - 60))


def draw_weapon(
    screen: pygame.Surface,
    shooting: bool,
    shoot_timer: int,
    player_moving: bool,
    game_time: float,
    weapon: Weapon,
    gatling_spin: float,
) -> None:
    """Draw the current weapon viewmodel."""
    if weapon == Weapon.SHOTGUN:
        draw_shotgun(screen, shooting, shoot_timer, player_moving, game_time)
    elif weapon == Weapon.GATLING:
        draw_gatling(screen, shooting, shoot_timer, player_moving, game_time, gatling_spin)
    elif weapon == Weapon.ROCKETS:
        _draw_rocket_launcher(screen, shooting, shoot_timer, player_moving, game_time)
    elif weapon == Weapon.NUKE:
        _draw_nuke_detonator(screen, shooting, shoot_timer, player_moving, game_time)
    else:
        _draw_pistol(screen, shooting, shoot_timer, player_moving, game_time)
