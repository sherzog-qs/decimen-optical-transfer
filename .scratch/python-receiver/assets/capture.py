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
