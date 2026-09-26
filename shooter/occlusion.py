"""Screen-space wall depths and clipped drawing targets for world sprites."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import numpy as np
import pygame
from numpy.typing import NDArray

from shooter.constants import HEIGHT, WIDTH


class DepthBuffer:
    """Store obstacle depth per pixel so openings don't hide entire sprites."""

    def __init__(self) -> None:
        self.pixels: NDArray[np.float32] = np.full((WIDTH, HEIGHT), np.inf, dtype=np.float32)

    def clear(self) -> None:
        self.pixels.fill(np.inf)

    def block_column(
        self, x: int, width: int, depth: float, top: int = 0, bottom: int = HEIGHT
    ) -> None:
        """Record a wall slice; callers draw farther surfaces before nearer ones."""
        left, right = max(0, x), min(WIDTH, x + width)
        top, bottom = max(0, top), min(HEIGHT, bottom)
        if left < right and top < bottom:
            self.pixels[left:right, top:bottom] = depth

    @contextmanager
    def sprite(
        self, screen: pygame.Surface, bounds: pygame.Rect, depth: float
    ) -> Generator[tuple[pygame.Surface, int, int] | None, None, None]:
        """Yield a target and its screen origin, then composite visible pixels.

        Fully visible sprites draw directly to the screen. Partial sprites use a
        temporary surface bounded to the viewport, with hidden pixels masked out.
        """
        bounds = bounds.clip(screen.get_clip())
        if not bounds:
            yield None
            return
        visible = self.pixels[bounds.left : bounds.right, bounds.top : bounds.bottom] >= depth - 0.1
        if visible.all():
            yield screen, 0, 0
        elif not visible.any():
            yield None
        else:
            target = pygame.Surface(bounds.size, pygame.SRCALPHA)
            yield target, bounds.left, bounds.top
            alpha = pygame.surfarray.pixels_alpha(target)
            alpha[~visible] = 0
            del alpha
            screen.blit(target, bounds.topleft)
