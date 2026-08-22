"""Drag out a screen region, the way Cmd-Shift-4 does — in pygame, no native
overlay.

The trick that avoids a transparent click-through window (which pygame does not
do well on macOS): grab one full-screen shot, show it fullscreen frozen, and let
the user drag a rectangle on that still. It looks like the OS selection and is
plain pygame, so the same code ports wherever the capture backend does.

Coordinates matter — the whole point of ticket 01 was that capture wants screen
POINTS. A pygame fullscreen window reports points that equal screen points
(verified: 1800x1169 both sides), so the drag rectangle is already in the units
ScreenRegion expects. No scale-factor conversion, which is exactly the mistake
to avoid.
"""
from __future__ import annotations

import Quartz


def _full_screenshot_points():
    """The whole main display as an (w_pt, h_pt, RGB-bytes-at-point-res) still.

    Downsampled to point resolution so it maps 1:1 onto the pygame window; the
    real capture later works in physical pixels, this is only the picker canvas.
    """
    did = Quartz.CGMainDisplayID()
    bounds = Quartz.CGDisplayBounds(did)
    wpt, hpt = int(bounds.size.width), int(bounds.size.height)
    img = Quartz.CGWindowListCreateImage(
        bounds, Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
    import numpy as np
    w = Quartz.CGImageGetWidth(img)
    h = Quartz.CGImageGetHeight(img)
    bpr = Quartz.CGImageGetBytesPerRow(img)
    raw = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
    arr = np.frombuffer(raw, np.uint8).reshape(h, bpr // 4, 4)[:, :w, [2, 1, 0]]
    # to point resolution for the canvas
    sx, sy = w / wpt, h / hpt
    xs = (np.arange(wpt) * sx).astype(int)
    ys = (np.arange(hpt) * sy).astype(int)
    canvas = np.ascontiguousarray(arr[np.ix_(ys, xs)])
    return wpt, hpt, canvas


def select_region():
    """Blocks until the user drags a rectangle. Returns (x, y, w, h) in screen
    points, or None if cancelled with Esc. Minimum 20x20 to reject a stray click."""
    import pygame
    import numpy as np

    wpt, hpt, canvas = _full_screenshot_points()
    pygame.init()
    screen = pygame.display.set_mode((wpt, hpt), pygame.NOFRAME)
    shot = pygame.image.frombuffer(canvas.tobytes(), (wpt, hpt), "RGB")
    dim = shot.copy()
    dim.fill((0, 0, 0, 110), special_flags=pygame.BLEND_RGBA_MULT)

    start = None
    rect = None
    clock = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.quit()
                return None
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                start = e.pos
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and start:
                x0, y0 = start
                x1, y1 = e.pos
                x, y = min(x0, x1), min(y0, y1)
                w, h = abs(x1 - x0), abs(y1 - y0)
                pygame.quit()
                if w < 20 or h < 20:
                    return None
                return (x, y, w, h)

        screen.blit(dim, (0, 0))                      # darkened whole screen
        if start and pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            x, y = min(start[0], mx), min(start[1], my)
            w, h = abs(mx - start[0]), abs(my - start[1])
            if w and h:
                screen.blit(shot, (x, y), pygame.Rect(x, y, w, h))  # bright inside
                pygame.draw.rect(screen, (76, 141, 255), (x, y, w, h), 2)
        pygame.display.flip()
        clock.tick(60)
