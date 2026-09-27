"""Procedural weapon art: perspective solids, material shading, and mechanical details.

Artwork is drawn at twice its display resolution, then cached in a small set of
mechanical poses. No image files, display conversion, or font setup are required.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache

import numpy as np
import pygame

from shooter.constants import Weapon

type Point = tuple[float, float]
type Color = tuple[int, int, int]

MODEL_SIZE = (360, 320)
MUZZLES: dict[Weapon, tuple[int, int]] = {
    Weapon.PISTOL: (98, 69),
    Weapon.SHOTGUN: (66, 23),
    Weapon.GATLING: (78, 44),
    Weapon.ROCKETS: (97, 47),
    Weapon.NUKE: (0, 0),
}
_STEEL: Color = (75, 84, 91)
_DARK: Color = (26, 30, 33)
_EDGE: Color = (132, 143, 146)
_WOOD: Color = (113, 69, 38)
_OLIVE: Color = (93, 104, 67)


def _shade(color: Color, factor: float) -> Color:
    r, g, b = (min(255, max(0, int(c * factor))) for c in color)
    return r, g, b


def _mix(a: Point, b: Point, t: float) -> Point:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


class _Painter:
    """Draw in model coordinates; supersampling keeps slanted edges clean."""

    def __init__(self) -> None:
        self.surface = pygame.Surface((MODEL_SIZE[0] * 2, MODEL_SIZE[1] * 2), pygame.SRCALPHA)

    def polygon(self, color: Color, points: Sequence[Point]) -> None:
        pygame.draw.polygon(self.surface, color, [(round(x * 2), round(y * 2)) for x, y in points])

    def line(self, color: Color, a: Point, b: Point, width: float = 1) -> None:
        pygame.draw.line(
            self.surface,
            color,
            (round(a[0] * 2), round(a[1] * 2)),
            (round(b[0] * 2), round(b[1] * 2)),
            max(1, round(width * 2)),
        )

    def ellipse(self, color: Color, rect: tuple[float, float, float, float]) -> None:
        pygame.draw.ellipse(self.surface, color, tuple(round(v * 2) for v in rect))

    def bolt(self, x: float, y: float, radius: float = 2.5) -> None:
        self.ellipse((15, 19, 21), (x - radius, y - radius, radius * 2 + 1, radius * 2 + 1))
        self.ellipse((112, 118, 114), (x - radius, y - radius, radius * 2, radius * 2))
        self.line((35, 39, 39), (x - radius * 0.55, y + 0.5), (x + radius * 0.55, y - 0.5))

    def block(
        self, a: Point, b: Point, front: float, rear: float, depth: float, color: Color
    ) -> None:
        """Tapered receiver, with a lit top, dark side, and bevels."""
        length = math.dist(a, b)
        nx, ny = (b[1] - a[1]) / length, (a[0] - b[0]) / length
        p = [
            (a[0] - nx * front, a[1] - ny * front),
            (a[0] + nx * front, a[1] + ny * front),
            (b[0] + nx * rear, b[1] + ny * rear),
            (b[0] - nx * rear, b[1] - ny * rear),
        ]
        self.polygon(
            _shade(color, 0.52),
            [p[1], p[2], (p[2][0], p[2][1] + depth), (p[1][0], p[1][1] + depth * 0.6)],
        )
        self.polygon(
            _shade(color, 0.68),
            [p[3], p[2], (p[2][0], p[2][1] + depth), (p[3][0], p[3][1] + depth)],
        )
        for i in range(12):
            t0, t1 = i / 12, (i + 1) / 12
            self.polygon(
                _shade(color, 1.10 - t0 * 0.24),
                [
                    _mix(p[0], p[3], t0),
                    _mix(p[1], p[2], t0),
                    _mix(p[1], p[2], t1),
                    _mix(p[0], p[3], t1),
                ],
            )
        self.line(_shade(color, 1.5), p[0], p[3], 1.5)
        self.line(_shade(color, 1.2), p[0], p[1])
        self.line(_shade(color, 0.7), p[1], p[2], 2)
        self.line(_shade(color, 0.4), (p[3][0], p[3][1] + depth), (p[2][0], p[2][1] + depth), 1.5)

    def tube(self, a: Point, b: Point, front: float, rear: float, color: Color) -> None:
        """A tapered cylinder with a broad highlight and a narrow specular edge."""
        length = math.dist(a, b)
        nx, ny = (b[1] - a[1]) / length, (a[0] - b[0]) / length
        for i in range(16):
            u, v = i / 8 - 1, (i + 1) / 8 - 1
            light = 0.40 + 0.65 * math.sin((i + 0.5) / 16 * math.pi)
            light += 0.3 * math.exp(-(((i - 4) / 1.8) ** 2))
            self.polygon(
                _shade(color, light),
                [
                    (a[0] + nx * front * u, a[1] + ny * front * u),
                    (a[0] + nx * front * v, a[1] + ny * front * v),
                    (b[0] + nx * rear * v, b[1] + ny * rear * v),
                    (b[0] + nx * rear * u, b[1] + ny * rear * u),
                ],
            )
        self.line(
            _shade(color, 0.45),
            (a[0] + nx * front, a[1] + ny * front),
            (b[0] + nx * rear, b[1] + ny * rear),
        )


def _sleeve(p: _Painter, x: float, y: float, left: bool = False) -> None:
    lean = -45 if left else 60
    p.polygon(
        (30, 35, 30), [(x - 22, y), (x + 19, y - 9), (x + 55 + lean, 340), (x - 28 + lean, 340)]
    )
    p.polygon(
        (53, 60, 47), [(x - 18, y + 6), (x + 12, y), (x + 33 + lean, 340), (x - 17 + lean, 340)]
    )
    p.line((77, 81, 62), (x - 16, y + 15), (x + lean - 6, 340), 2)
    p.line((23, 28, 25), (x + 17, y + 25), (x + lean + 37, 340), 3)


def _hand(p: _Painter, x: float, y: float, left: bool = False) -> None:
    """Leather glove with a shaped palm, padded knuckles, seams, and cuff."""
    _sleeve(p, x + 9, y + 40, left)
    p.polygon(
        (31, 27, 24),
        [
            (x - 24, y + 4),
            (x - 8, y - 17),
            (x + 13, y - 16),
            (x + 31, y + 2),
            (x + 30, y + 40),
            (x + 15, y + 56),
            (x - 16, y + 49),
            (x - 27, y + 26),
        ],
    )
    p.polygon(
        (72, 60, 46),
        [
            (x - 22, y + 5),
            (x - 6, y - 12),
            (x + 12, y - 10),
            (x + 22, y + 4),
            (x + 21, y + 36),
            (x + 10, y + 44),
            (x - 14, y + 38),
            (x - 23, y + 23),
        ],
    )
    p.polygon(
        (89, 75, 56),
        [(x - 18, y + 5), (x - 5, y - 7), (x + 8, y - 7), (x + 13, y + 12), (x - 10, y + 20)],
    )
    for i in range(3):
        p.line((111, 94, 71), (x - 17 + i * 9, y + 4), (x - 12 + i * 9, y + 15))
    p.line((119, 100, 75), (x - 17, y + 30), (x + 11, y + 38))
    p.line((22, 23, 21), (x - 18, y + 44), (x + 20, y + 49), 9)
    p.line((77, 76, 59), (x - 16, y + 42), (x + 21, y + 47), 2)


def _fingers(p: _Painter, x: float, y: float, count: int = 3) -> None:
    for i in range(count):
        dx, dy = i * 3, i * 10
        p.line((29, 26, 23), (x + dx, y + dy), (x + dx + 22, y + dy - 10), 11)
        p.line(
            (86 - i * 5, 71 - i * 4, 53 - i * 3),
            (x + dx, y + dy - 2),
            (x + dx + 21, y + dy - 12),
            8,
        )
        p.line((119, 99, 73), (x + dx + 2, y + dy - 5), (x + dx + 15, y + dy - 11))


def _pistol(p: _Painter, pose: int) -> None:
    _hand(p, 235, 253)
    # Raked polymer grip, checkering, trigger guard, and frame.
    p.block((163, 208), (220, 282), 24, 27, 17, (40, 43, 41))
    for i in range(9):
        y = 222 + i * 6
        x = 164 + i * 4.6
        p.line((22, 26, 26), (x, y + 6), (x + 30, y - 10), 2)
        p.line((77, 78, 69), (x + 2, y + 4), (x + 28, y - 10), 0.5)
    p.line(_DARK, (206, 199), (235, 214), 7)
    p.line(_DARK, (235, 214), (230, 244), 7)
    p.line(_DARK, (230, 244), (206, 247), 7)
    p.line((96, 102, 99), (208, 201), (231, 216), 1.5)
    p.line((22, 24, 26), (211, 207), (218, 227), 4)
    p.block((103, 94), (177, 208), 18, 34, 19, (42, 48, 49))
    # Fixed barrel remains exposed as the slide travels backward.
    p.tube((98, 70), (135, 124), 10, 14, (107, 117, 124))
    dx, dy = pose * 1.0, pose * 1.7
    a, b = (101 + dx, 81 + dy), (177 + dx, 191 + dy)
    p.block(a, b, 18, 34, 21, _STEEL)
    p.polygon(
        (100, 111, 119),
        [
            (a[0] - 9, a[1] + 3),
            (a[0] + 5, a[1] - 6),
            (b[0] + 13, b[1] - 10),
            (b[0] - 18, b[1] + 10),
        ],
    )
    # Ejection port, polished chamber, and rear slide serrations.
    p.polygon(
        (21, 26, 31),
        [(137 + dx, 116 + dy), (151 + dx, 108 + dy), (171 + dx, 138 + dy), (154 + dx, 149 + dy)],
    )
    p.line((157, 164, 158), (142 + dx, 118 + dy), (158 + dx, 141 + dy), 6)
    for i in range(6):
        x, y = 163 + dx + i * 3, 157 + dy + i * 4.5
        p.line((37, 44, 51), (x + 18, y - 9), (x + 22, y + 8), 2)
        p.line((126, 135, 139), (x + 20, y - 8), (x + 24, y + 7), 0.7)
    p.line(_EDGE, (92 + dx, 100 + dy), (144 + dx, 177 + dy), 0.7)
    p.block((96 + dx, 73 + dy), (100 + dx, 80 + dy), 3, 3, 5, _DARK)
    p.line((210, 202, 163), (95 + dx, 72 + dy), (98 + dx, 76 + dy), 2)
    p.block((169 + dx, 177 + dy), (177 + dx, 188 + dy), 23, 25, 5, (26, 31, 35))
    for x, y in ((160, 189), (185, 172)):
        p.ellipse((204, 211, 181), (x + dx, y + dy, 3, 3))
    p.bolt(169, 222)
    p.line((111, 118, 113), (191, 214), (202, 207), 3)
    p.polygon(
        (64, 53, 40), [(199, 242), (220, 239), (242, 259), (242, 284), (222, 287), (211, 269)]
    )
    _fingers(p, 199, 247)
    p.line((44, 37, 29), (177, 226), (205, 238), 13)
    p.line((112, 93, 66), (175, 222), (201, 233), 9)


def _shotgun(p: _Painter, pose: int) -> None:
    pump = pose / 12
    sx, sy = pump * 18, pump * 28
    _hand(p, 121 + sx, 184 + sy, True)
    _hand(p, 239, 269)
    # Walnut stock expands toward the shoulder.
    p.block((191, 217), (271, 326), 25, 46, 23, _WOOD)
    for i in range(9):
        x = 180 + i * 5
        p.line((143, 91, 47) if i % 2 else (78, 46, 28), (x, 241 - i * 2), (x + 64, 328 - i * 3), 1)
    p.block((252, 302), (270, 327), 41, 47, 25, (29, 31, 29))
    # Magazine tube below the longer barrel; bands bind the two together.
    p.tube((88, 74), (176, 205), 8, 14, (49, 57, 62))
    p.tube((66, 24), (172, 188), 8, 15, (81, 92, 101))
    p.tube((67, 26), (72, 34), 9, 10, (121, 129, 128))
    p.tube((93, 66), (99, 77), 11, 12, _DARK)
    p.line((161, 168, 164), (64, 28), (166, 183), 1)
    # Raised rib and small brass bead on the muzzle end.
    p.line((24, 29, 32), (65, 20), (169, 180), 4)
    p.line((121, 129, 132), (64, 18), (167, 176), 1)
    p.ellipse((215, 191, 129), (63, 17, 4, 4))
    p.block((155, 155), (211, 236), 19, 30, 24, (62, 72, 79))
    p.polygon((23, 29, 32), [(184, 173), (196, 167), (220, 202), (207, 213)])
    p.line((139, 145, 143), (192, 178), (210, 204), 5)
    p.line((17, 22, 24), (205, 190), (222, 181), 4)
    p.bolt(192, 228)
    p.bolt(211, 214)
    # Action bars follow the forend through the pump cycle.
    p.line((133, 140, 136), (142 + sx, 143 + sy), (194, 217), 3)
    p.block((112 + sx, 108 + sy), (148 + sx, 161 + sy), 18, 24, 22, _WOOD)
    for i in range(8):
        x, y = 113 + sx + i * 4.4, 111 + sy + i * 6.3
        p.line((49, 33, 25), (x - 14, y + 12), (x + 15, y - 8), 3)
        p.line((164, 107, 58), (x - 13, y + 10), (x + 14, y - 10), 1)
    _fingers(p, 127 + sx, 175 + sy)
    _fingers(p, 216, 257)


def _gatling(p: _Painter, pose: int) -> None:
    _hand(p, 142, 233, True)
    _hand(p, 269, 273)
    # Heavy rear motor, side feed tray, and linked brass cartridges.
    p.block((176, 161), (260, 295), 43, 59, 24, (52, 61, 64))
    p.block((242, 203), (287, 261), 18, 22, 22, (34, 40, 42))
    p.line((39, 43, 40), (284, 210), (319, 305), 13)
    p.line((94, 95, 74), (284, 210), (319, 305), 3)
    for i in range(8):
        x, y = 284 + i * 4.2, 222 + i * 11
        p.line((33, 29, 24), (x - 12, y + 4), (x + 13, y - 10), 10)
        p.line((164, 126, 58), (x - 13, y + 1), (x + 10, y - 12), 7)
        p.line((222, 186, 100), (x - 12, y - 1), (x + 7, y - 12), 2)
        p.line((88, 79, 58), (x - 5, y + 2), (x - 3, y - 8), 3)
    p.tube((93, 67), (198, 219), 27, 43, (37, 43, 46))
    angle = pose / 16 * math.tau / 6
    barrels = [angle + i * math.tau / 6 for i in range(6)]
    # Back barrels first, so rotation preserves their depth ordering.
    for theta in sorted(barrels, key=math.sin):
        radial_x, radial_y = math.cos(theta), math.sin(theta)
        a = (82 + radial_x * 22, 51 + radial_y * 10)
        b = (187 + radial_x * 34, 203 + radial_y * 16)
        p.tube(a, b, 5, 8, (99, 111, 120))
        p.line((150, 156, 151), (a[0] - 2, a[1]), (b[0] - 4, b[1]), 0.7)
    # Clamp rings and a ribbed drive collar sit around the entire cluster.
    p.tube((82, 49), (92, 65), 29, 31, (70, 81, 88))
    p.tube((142, 137), (153, 153), 38, 40, (65, 75, 80))
    p.tube((178, 190), (202, 226), 46, 50, (64, 72, 75))
    for i in range(5):
        p.tube((183 + i * 4, 199 + i * 5), (185 + i * 4, 202 + i * 5), 47, 48, (41, 49, 53))
    p.block((189, 240), (214, 273), 27, 31, 12, (51, 60, 61))
    for i in range(4):
        p.line((22, 29, 31), (182 + i * 8, 240 + i * 11), (207 + i * 8, 225 + i * 11), 4)
    p.bolt(234, 269, 4)
    p.bolt(256, 255, 4)
    p.line((131, 139, 133), (155, 184), (162, 193), 1)
    p.line((133, 139, 132), (232, 286), (248, 277), 1)
    _fingers(p, 126, 226)
    _fingers(p, 244, 259)


def _rockets(p: _Painter) -> None:
    _hand(p, 130, 204, True)
    _hand(p, 256, 270)
    # A shoulder-fired tube recedes into the scene; its exhaust faces the player.
    p.tube((99, 55), (256, 293), 27, 58, _OLIVE)
    for a, b, r0, r1 in (
        ((97, 51), (107, 66), 30, 33),
        ((140, 119), (148, 131), 39, 41),
        ((218, 234), (228, 250), 54, 56),
    ):
        p.tube(a, b, r0, r1, (48, 56, 42))
        p.tube(a, _mix(a, b, 0.2), r0, r0 + 1, (129, 139, 99))
    # Shoulder pad and rear reinforced collar extend below the frame.
    p.block((204, 226), (265, 317), 45, 65, 21, (41, 44, 35))
    p.tube((244, 276), (265, 310), 61, 69, (65, 71, 55))
    for i in range(4):
        p.line((22, 29, 25), (205 + i * 12, 288 + i * 5), (222 + i * 12, 315 + i * 5), 3)
    # Offset sight bracket and protected amber optic.
    p.block((152, 136), (177, 172), 39, 43, 7, (44, 50, 45))
    p.line(_DARK, (128, 143), (107, 122), 9)
    p.block((92, 92), (114, 125), 14, 17, 11, (43, 50, 47))
    p.polygon((12, 23, 23), [(100, 125), (123, 109), (132, 121), (108, 138)])
    p.polygon((109, 103, 52), [(103, 125), (122, 113), (127, 121), (109, 133)])
    p.line((205, 185, 92), (105, 123), (118, 115), 1.5)
    # Front folding sight, safety lever, fasteners, and worn paint edges.
    p.line(_DARK, (92, 55), (79, 31), 4)
    p.line(_EDGE, (79, 31), (85, 27), 2)
    p.bolt(147, 140, 3)
    p.bolt(203, 227, 3)
    p.line((153, 73, 45), (186, 213), (196, 222), 4)
    for x, y in ((116, 90), (148, 151), (179, 175), (207, 206), (240, 266)):
        p.line((161, 164, 119), (x, y), (x + 3, y + 5), 1)
    # Stencilled bands curve with the tube, without depending on a system font.
    p.line((173, 162, 97), (142, 172), (170, 155), 5)
    for i in range(7):
        p.line((191, 190, 151), (158 + i * 3, 192 - i * 2), (161 + i * 3, 197 - i * 2), 1)
    _fingers(p, 119, 194)
    _fingers(p, 235, 256)


def _detonator(p: _Painter, pressed: bool) -> None:
    _hand(p, 106, 243, True)
    _hand(p, 250, 247)
    # Antenna, reinforced housing, and a sloping control panel.
    p.line((21, 26, 26), (124, 119), (106, 32), 7)
    p.line((96, 106, 98), (122, 110), (107, 34), 1.5)
    p.ellipse((25, 31, 31), (102, 28, 8, 8))
    p.polygon((27, 33, 29), [(102, 116), (236, 93), (279, 264), (129, 296), (91, 155)])
    p.polygon((74, 84, 63), [(103, 118), (225, 98), (263, 254), (132, 282)])
    p.polygon((110, 119, 85), [(108, 122), (219, 105), (224, 116), (109, 135)])
    p.polygon((43, 54, 43), [(132, 269), (259, 244), (263, 254), (132, 282)])
    for x, y in ((114, 139), (222, 122), (140, 261), (250, 240)):
        p.bolt(x, y, 3)
    # Recessed status display with seven-segment-style bars.
    p.polygon((18, 26, 25), [(125, 148), (203, 134), (211, 165), (132, 182)])
    p.line((135, 150, 119), (133, 182), (211, 165))
    for i in range(4):
        x, y = 135 + i * 17, 151 - i * 3
        color = (218, 116, 58) if pressed else (132, 175, 116)
        p.line(color, (x, y), (x + 8, y - 1), 2)
        p.line(color, (x + 2, y + 6), (x + 10, y + 5), 2)
        p.line(color, (x + 4, y + 12), (x + 12, y + 11), 2)
        p.line(color, (x, y), (x + 2, y + 5), 2)
        p.line(color, (x + 10, y + 6), (x + 12, y + 11), 2)
    # Hazard plate and a guarded, physical red pushbutton.
    p.polygon((178, 152, 66), [(142, 199), (176, 192), (187, 237), (154, 244)])
    p.polygon((42, 41, 30), [(147, 203), (154, 202), (164, 239), (158, 241)])
    p.polygon((42, 41, 30), [(163, 199), (170, 197), (180, 235), (174, 237)])
    p.ellipse((23, 25, 24), (189, 184, 52, 51))
    p.ellipse((133, 135, 113), (191, 184, 46, 45))
    p.ellipse((47, 30, 26), (194, 187, 40, 39))
    y = 193 if pressed else 185
    p.ellipse((106, 29, 23), (197, y + 4, 33, 34))
    p.ellipse((184, 49, 34), (197, y, 33, 31))
    p.ellipse((219, 81, 51), (201, y + 2, 23, 12))
    p.line((63, 72, 61), (192, 183), (187, 171), 6)
    p.line((63, 72, 61), (229, 177), (227, 164), 6)
    p.line((137, 144, 121), (187, 170), (226, 163), 4)
    p.ellipse((215, 105, 55) if pressed else (121, 185, 103), (223, 145, 6, 6))
    _fingers(p, 112, 224)
    _fingers(p, 245, 218)


@lru_cache(maxsize=48)
def weapon_frame(weapon: Weapon, pose: int = 0) -> pygame.Surface:
    """Read-only cached art. Callers must copy before tinting or changing alpha."""
    p = _Painter()
    if weapon == Weapon.PISTOL:
        _pistol(p, pose)
    elif weapon == Weapon.SHOTGUN:
        _shotgun(p, pose)
    elif weapon == Weapon.GATLING:
        _gatling(p, pose)
    elif weapon == Weapon.ROCKETS:
        _rockets(p)
    else:
        _detonator(p, bool(pose))
    surface = pygame.transform.smoothscale(p.surface, MODEL_SIZE)
    # Subtle matte grain keeps large panels from looking like flat vector fills.
    # A private, fixed seed makes every pose stable without touching game RNGs.
    pixels = pygame.surfarray.pixels3d(surface)
    grain = np.random.default_rng(1729).integers(-3, 4, (*MODEL_SIZE, 1), dtype=np.int16)
    pixels[:] = np.clip(pixels.astype(np.int16) + grain, 0, 255).astype(np.uint8)
    del pixels
    return surface
