"""Fresh, typed gameplay and rendering fixtures for each test case."""

from collections.abc import Iterator

import pygame
import pygame.freetype
import pytest

from shooter.constants import HEIGHT, WIDTH
from shooter.map import LevelState
from shooter.occlusion import DepthBuffer
from shooter.state import GameState
from shooter.types import Sfx
from tests.support import SoundMocks, open_world


@pytest.fixture
def world() -> LevelState:
    return open_world()


@pytest.fixture
def state(world: LevelState) -> GameState:
    state = GameState(seed=0)
    state.world = world
    return state


@pytest.fixture
def sounds() -> SoundMocks:
    return SoundMocks()


@pytest.fixture
def sfx(sounds: SoundMocks) -> Sfx:
    return sounds.sfx


@pytest.fixture
def pressed() -> set[int]:
    return set()


@pytest.fixture
def screen() -> pygame.Surface:
    return pygame.Surface((WIDTH, HEIGHT))


@pytest.fixture
def depth() -> DepthBuffer:
    return DepthBuffer()


@pytest.fixture
def font() -> Iterator[pygame.freetype.Font]:
    was_initialized = pygame.freetype.get_init()
    pygame.freetype.init()
    try:
        yield pygame.freetype.Font(None, 20)
    finally:
        if not was_initialized:
            pygame.freetype.quit()
