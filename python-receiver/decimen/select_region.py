"""Drag out a screen region, the way Cmd-Shift-4 does — in pygame, on a frozen
full-screen still.

Grab one full-screen shot, show it fullscreen, let the user drag a rectangle on
that still. Plain pygame, so it ports wherever the capture backend does.

Two macOS traps this went through:

* A borderless window sized to the screen inherits the app window's top-left on
  a resize, so it hangs off the edge and only part of it is selectable. Real
  FULLSCREEN sidesteps the position question entirely.
* On Retina the fullscreen surface may report physical pixels (e.g. 3600x2338)
  while capture wants screen POINTS (1800x1169). So mouse coordinates are scaled
  by points/surface, whatever the surface turns out to be — never assumed equal.

Runs on the caller's pygame; it rebuilds the display for fullscreen and the
caller rebuilds its own window afterwards. It must not pygame.quit().

Set DECIMEN_SELECT_DEBUG=1 to print the surface size and each click, so a
capture that misbehaves reports facts instead of a shrug.
"""
from __future__ import annotations

import os

import numpy as np
import Quartz

_DEBUG = os.environ.get("DECIMEN_SELECT_DEBUG") == "1"


def _full_screenshot_points():
    """The whole main display as (w_pt, h_pt, RGB array at point resolution)."""
    did = Quartz.CGMainDisplayID()
    bounds = Quartz.CGDisplayBounds(did)
    wpt, hpt = int(bounds.size.width), int(bounds.size.height)
    img = Quartz.CGWindowListCreateImage(
        bounds, Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
    w = Quartz.CGImageGetWidth(img)
    h = Quartz.CGImageGetHeight(img)
    bpr = Quartz.CGImageGetBytesPerRow(img)
    raw = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
    arr = np.frombuffer(raw, np.uint8).reshape(h, bpr // 4, 4)[:, :w, [2, 1, 0]]
    sx, sy = w / wpt, h / hpt
    xs = (np.arange(wpt) * sx).astype(int)
    ys = (np.arange(hpt) * sy).astype(int)
    return wpt, hpt, np.ascontiguousarray(arr[np.ix_(ys, xs)])


def select_region():
    """Blocks until the user drags a rectangle. Returns (x, y, w, h) in screen
    points, or None on Esc or a too-small drag (<20x20 points)."""
    import pygame

    wpt, hpt, canvas = _full_screenshot_points()

    pygame.display.quit()
    pygame.display.init()
    screen = pygame.display.set_mode((wpt, hpt), pygame.FULLSCREEN)
    sw, sh = screen.get_size()
    # points-per-surface-unit: 1.0 if the surface is in points, 0.5 if Retina
    # gave us physical pixels. Every mouse coord goes through this.
    to_pt_x = wpt / sw
    to_pt_y = hpt / sh
    if _DEBUG:
        print(f"[select] screenshot {wpt}x{hpt} pt, surface {sw}x{sh}, "
              f"scale {to_pt_x:.3f}x{to_pt_y:.3f}", flush=True)

    shot = pygame.transform.smoothscale(
        pygame.image.frombuffer(canvas.tobytes(), (wpt, hpt), "RGB"), (sw, sh))
    dim = shot.copy()
    # Multiply each RGB channel by 110/255 (~43% brightness): dark, still
    # readable. (0,0,0) here would multiply by ZERO and paint the whole screen
    # black — the "nothing to select" bug.
    dim.fill((110, 110, 110), special_flags=pygame.BLEND_RGB_MULT)
    font = pygame.font.SysFont(None, 28)

    start = None
    clock = pygame.time.Clock()
    try:
        while True:
            for e in pygame.event.get():
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    return None
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    start = e.pos
                    if _DEBUG:
                        print(f"[select] down at {e.pos}", flush=True)
                if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and start:
                    if _DEBUG:
                        print(f"[select] up at {e.pos}", flush=True)
                    x0, y0 = start
                    x1, y1 = e.pos
                    x = round(min(x0, x1) * to_pt_x)
                    y = round(min(y0, y1) * to_pt_y)
                    w = round(abs(x1 - x0) * to_pt_x)
                    h = round(abs(y1 - y0) * to_pt_y)
                    if w < 20 or h < 20:
                        return None
                    return (x, y, w, h)

            screen.blit(dim, (0, 0))
            if start and pygame.mouse.get_pressed()[0]:
                mx, my = pygame.mouse.get_pos()
                x, y = min(start[0], mx), min(start[1], my)
                w, h = abs(mx - start[0]), abs(my - start[1])
                if w and h:
                    screen.blit(shot, (x, y), pygame.Rect(x, y, w, h))
                    pygame.draw.rect(screen, (76, 141, 255), (x, y, w, h), 2)
            else:
                hint = font.render(
                    "Drag a rectangle around the QR stream   ·   Esc to cancel",
                    True, (235, 235, 235))
                screen.blit(hint, hint.get_rect(center=(sw // 2, 44)))
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.display.quit()
        pygame.display.init()
