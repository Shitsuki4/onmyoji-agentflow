"""A device that replays recorded screenshots: used for replay tests and CI."""
from __future__ import annotations

import os

import cv2
import numpy as np

from .base import Device


class ReplayDevice(Device):
    """Serves frames from a list (or a folder of PNGs, sorted by name).

    By default each screenshot() advances one frame; ``advance_on_input=True``
    instead advances only after a tap/swipe/back (useful to model "the screen
    changes when you press the button"). The last frame repeats forever.
    """

    name = "replay"

    def __init__(self, frames, advance_on_input: bool = False):
        if isinstance(frames, (str, os.PathLike)):
            folder = str(frames)
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg")))
            frames = [cv2.imdecode(np.fromfile(os.path.join(folder, f), np.uint8), cv2.IMREAD_COLOR) for f in files]
        if not frames:
            raise ValueError("ReplayDevice needs at least one frame")
        self.frames = list(frames)
        self.index = 0
        self.advance_on_input = advance_on_input
        self.inputs: list[tuple] = []

    def _advance(self):
        self.index = min(self.index + 1, len(self.frames) - 1)

    def screenshot(self) -> np.ndarray:
        frame = self.frames[self.index]
        if not self.advance_on_input:
            self._advance()
        return frame.copy()

    def tap(self, x, y, press_ms=40):
        self.inputs.append(("tap", x, y))
        if self.advance_on_input:
            self._advance()

    def swipe(self, p1, p2, duration_ms=400):
        self.inputs.append(("swipe", tuple(p1), tuple(p2)))
        if self.advance_on_input:
            self._advance()

    def back(self):
        self.inputs.append(("back",))
        if self.advance_on_input:
            self._advance()

    def start_app(self, package):
        self.inputs.append(("start_app", package))
