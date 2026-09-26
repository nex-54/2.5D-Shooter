"""Independent world and keyboard fixtures for simulation tests."""

from collections import defaultdict
from typing import cast
from unittest.mock import MagicMock

import pygame

from shooter.map import MAP_H, MAP_W, LevelState
from shooter.types import Sfx


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
