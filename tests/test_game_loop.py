"""Drive real input and simulation through main-loop pause and restart transitions."""

from collections.abc import Iterator
from unittest.mock import MagicMock, call, patch

import pygame
import pygame.freetype
import pytest

from shooter import game
from shooter.constants import PLAYER_MAX_HP, PLAYER_MOVE_SPEED
from shooter.entities import Enemy
from shooter.state import GameState
from shooter.types import Textures
from tests.support import Keys, SoundMocks


@pytest.fixture
def loop(screen: pygame.Surface) -> Iterator[MagicMock]:
    """Control timing and platform I/O while keeping input, simulation, and overlays real."""
    calls = MagicMock()
    calls.tick.return_value = 16
    calls.get_pressed.return_value = Keys()
    calls.update_game = MagicMock(wraps=game.update_game)
    calls.draw_pause_overlay = MagicMock(wraps=game.draw_pause_overlay)
    calls.draw_game_over = MagicMock(wraps=game.draw_game_over)

    def paint_gameplay(*_args: object) -> None:
        screen.fill((40, 60, 80))

    calls.draw_frame.side_effect = paint_gameplay
    with (
        patch("shooter.game.pygame.time.Clock", return_value=MagicMock(tick=calls.tick)),
        patch("shooter.game.pygame.event.get", calls.events),
        patch("shooter.game.pygame.event.clear", calls.clear_events),
        patch("shooter.game.pygame.key.get_pressed", calls.get_pressed),
        patch("shooter.game.pygame.display.flip", calls.present),
        patch("shooter.game.pygame.mixer.pause", calls.pause_audio),
        patch("shooter.game.pygame.mixer.unpause", calls.resume_audio),
        patch("shooter.game.capture_mouse", calls.capture_mouse),
        patch("shooter.game.update_game", calls.update_game),
        patch("shooter.game.draw_frame", calls.draw_frame),
        patch("shooter.game.draw_level_banner", calls.draw_level_banner),
        patch("shooter.game.draw_pause_overlay", calls.draw_pause_overlay),
        patch("shooter.game.draw_game_over", calls.draw_game_over),
    ):
        yield calls


@pytest.mark.parametrize("escape", (True, False), ids=("escape", "click"))
def test_pause_freezes_the_frame_and_resumes_simulation_mouse_and_audio(
    escape: bool,
    loop: MagicMock,
    font: pygame.freetype.Font,
    screen: pygame.Surface,
    sounds: SoundMocks,
    state: GameState,
) -> None:
    state.px, state.py = 5.5, 5.5
    forward = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w, scancode=pygame.KSCAN_W)
    pause = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=pygame.KSCAN_ESCAPE)
    resume = pause if escape else pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    loop.events.side_effect = [
        [forward],
        [pause],
        [],
        [resume],
        [forward],
        [pygame.event.Event(pygame.QUIT)],
    ]
    frames: list[bytes] = []
    times: list[float] = []
    positions: list[float] = []

    def present() -> None:
        index = len(frames)
        assert state.paused == (index in (1, 2))
        assert loop.update_game.call_count == (1, 1, 1, 2, 3)[index]
        assert loop.draw_frame.call_count == (1, 1, 1, 2, 3)[index]
        assert loop.pause_audio.call_count == (0, 1, 1, 1, 1)[index]
        assert loop.resume_audio.call_count == (0, 0, 0, 1, 1)[index]
        frames.append(pygame.image.tobytes(screen, "RGB"))
        times.append(state.game_time)
        positions.append(state.px)

    loop.present.side_effect = present
    game.run_game(state, screen, font, font, sounds.sfx, Textures())

    assert times == pytest.approx([0.016, 0.016, 0.016, 0.032, 0.048])
    first_step = 5.5 + PLAYER_MOVE_SPEED * 16
    assert positions == pytest.approx([first_step] * 4 + [5.5 + PLAYER_MOVE_SPEED * 32])
    assert frames[0] != frames[1]
    assert frames[1] == frames[2]
    assert frames[3] == frames[4] == frames[0]
    loop.draw_pause_overlay.assert_called_once()
    loop.draw_game_over.assert_not_called()
    assert loop.capture_mouse.call_args_list == [call(False), call(True)]
    loop.clear_events.assert_called_once_with(pygame.MOUSEMOTION)
    assert loop.update_game.call_count == loop.draw_frame.call_count == 3
    sounds["pistol"].play.assert_not_called()


def test_death_draws_game_over_until_restart_resumes_the_main_loop(
    loop: MagicMock,
    font: pygame.freetype.Font,
    screen: pygame.Surface,
    sounds: SoundMocks,
    state: GameState,
) -> None:
    state.px, state.py = 5.5, 5.5
    state.hp = 5
    state.enemies = [Enemy(6.0, 5.5, state.rng)]
    previous_world = state.world
    forward = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w, scancode=pygame.KSCAN_W)
    restart = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, scancode=pygame.KSCAN_R)
    loop.events.side_effect = [[forward], [], [], [restart], [], [pygame.event.Event(pygame.QUIT)]]
    frames: list[bytes] = []
    times: list[float] = []

    def present() -> None:
        index = len(frames)
        assert state.game_over == (index < 3)
        assert loop.update_game.call_count == (1, 1, 1, 2, 3)[index]
        assert loop.draw_frame.call_count == (1, 1, 1, 2, 3)[index]
        assert loop.draw_game_over.call_count == (0, 1, 2, 2, 2)[index]
        frames.append(pygame.image.tobytes(screen, "RGB"))
        times.append(state.game_time)

    loop.present.side_effect = present
    game.run_game(state, screen, font, font, sounds.sfx, Textures())

    assert times == pytest.approx([0.016, 0.016, 0.016, 0.016, 0.032])
    assert frames[0] != frames[1]
    assert frames[1] == frames[2]
    assert frames[3] == frames[4] == frames[0]
    assert state.world is not previous_world
    assert state.hp == PLAYER_MAX_HP
    assert (state.px, state.py) == state.world.player_spawn
    assert not state.game_over
    assert loop.update_game.call_count == loop.draw_frame.call_count == 3
    loop.draw_pause_overlay.assert_not_called()
    sounds["enemy_attack"].play.assert_called_once()
