"""Screen-region capture, macOS — the interface a later Windows/Linux backend
slots behind: a rectangle in screen points -> an RGB numpy array of physical
pixels.

Quartz CGWindowListCreateImage rather than ScreenCaptureKit: one call, no async
completion handler, and it returns physical (Retina) pixels — which QR decoding
needs, since a module wants as many pixels as it can get. It is deprecated as of
macOS 14 and still works on 26.5.2; ScreenCaptureKit (SCScreenshotManager, also
present via pyobjc) is the upgrade path if a future macOS removes it. Measured
here at ~120 fps for a 740pt region, far above the 60 fps ceiling a sender ever
produces, so the deprecated-but-simple path wins today.

mss was rejected: it returns logical points, halving every module's pixels.

Needs Screen Recording permission for the running process, or capture returns
a black image with no error.
"""
from __future__ import annotations

import numpy as np
import Quartz
from Quartz import CGWindowListCreateImage, CGRectMake


class ScreenRegion:
    def __init__(self, x: int, y: int, w: int, h: int):
        # Points, top-left origin — what the selection gesture yields.
        self.rect = CGRectMake(x, y, w, h)

    def grab(self) -> np.ndarray | None:
        """(H, W, 3) uint8 RGB of physical pixels, or None if capture failed."""
        img = CGWindowListCreateImage(
            self.rect, Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
        if img is None:
            return None
        w = Quartz.CGImageGetWidth(img)
        h = Quartz.CGImageGetHeight(img)
        bpr = Quartz.CGImageGetBytesPerRow(img)      # row stride, may exceed w*4
        raw = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
        buf = np.frombuffer(raw, dtype=np.uint8).reshape(h, bpr // 4, 4)
        bgra = buf[:, :w, :]                          # drop row padding
        return bgra[:, :, [2, 1, 0]]                  # BGRA -> RGB, one view


def has_screen_permission() -> bool:
    """True if this process may capture other apps' windows.

    Without it, CGWindowListCreateImage returns only the desktop and our own
    windows — everything else is invisible, which looks like a black or
    wallpaper-only capture. The permission is granted per executable, so a fresh
    `uv run python` is not on the list until the user adds it.
    """
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except AttributeError:
        return True                     # pre-10.15: no gate to check


def request_screen_permission() -> None:
    """Register this process in the Screen Recording list and open the prompt.
    macOS will not activate it live — the user ticks the box and relaunches."""
    try:
        Quartz.CGRequestScreenCaptureAccess()
    except AttributeError:
        pass
