"""Hand-drawn controls, because pygame has none.

Immediate mode: no widget objects, no layout engine, no retained state beyond
the mouse, the keyboard buffer and whichever slider is being dragged. Every
frame redraws the panel and asks each control whether it was hit. For a dozen
controls that is far less machinery than a widget tree, and the drawing code
reads top to bottom in the order the panel appears.

Everything is pygame because on macOS tkinter and SDL both want to be the
NSApplication, and the loser stops receiving input — the tkinter panel came up
and never saw a click.

Two notes on how this ends up looking:

* **The system font matters more than anything else here.** pygame's default is
  a bundled sans that reads as programmer art at any size. SF Pro is on every
  Mac, SF Mono alongside it, and setting numbers in a monospace stops the spec
  readouts from jittering as they update.
* pygame draws in points and macOS scales that up to real pixels — 1800x1169
  against 3024x1964 on the machine this was built on. Text is therefore
  slightly soft, and getting around it needs a semi-private window API. Not
  worth risking the QR path for.
"""

from __future__ import annotations

import pygame

# Dark panel, dark stage, white codes. The stage is where a camera looks, and a
# white quiet zone against near-black is the strongest edge on offer.
STAGE = (14, 15, 18)
BG = (22, 24, 29)
SURFACE = (32, 35, 42)
SURFACE_HI = (44, 48, 57)
INK = (232, 234, 237)
MUTED = (138, 144, 153)
FAINT = (92, 98, 108)
LINE = (42, 46, 54)
ACCENT = (76, 141, 255)
ACCENT_DOWN = (60, 120, 226)
ACCENT_INK = (11, 13, 17)
ERROR = (255, 107, 107)
ERROR_TINT = (52, 30, 34)
LIVE = (64, 200, 130)

# macOS first, then Windows, then whatever a Linux box has. pygame falls
# through the list and only lands on its own bundled font if none exist.
_FONT_STACK = ("SF Pro Text", "Helvetica Neue", "Segoe UI", "Inter",
               "DejaVu Sans", "Arial")
_MONO_STACK = ("SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier New")


def _font(stack, size: int, bold: bool = False) -> pygame.font.Font:
    for name in stack:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size, bold=bold)


class UI:
    """One panel's worth of drawing and hit-testing for a single frame."""

    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.body = _font(_FONT_STACK, 14)
        self.small = _font(_FONT_STACK, 12)
        self.strong = _font(_FONT_STACK, 14, bold=True)
        self.label = _font(_FONT_STACK, 11, bold=True)
        self.mono = _font(_MONO_STACK, 12)
        self.mono_small = _font(_MONO_STACK, 11)
        self.click = None          # (x, y) of a completed click this frame
        self.press = None          # (x, y) while a button is held
        self.drag_released = False
        self.text_events = []      # (kind, value) for the snippet field
        self._drag = None          # which slider owns the mouse, across frames
        # Where each control ended up this frame. Immediate mode keeps no
        # widget objects, so without this there is no way to aim a test at a
        # control — and the click path is exactly what needs testing.
        self.rects = {}

    # ----------------------------------------------------------- per frame

    def begin(self, events) -> None:
        self.click = None
        self.drag_released = False
        self.text_events = []
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.press = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.press is not None:
                    self.click = event.pos
                self.press = None
                self.drag_released = True
            elif event.type == pygame.TEXTINPUT:
                self.text_events.append(("text", event.text))
            elif event.type == pygame.KEYDOWN:
                self.text_events.append(("key", event.key))

    # -------------------------------------------------------------- pieces

    def text(self, x: int, y: int, value: str, color=INK, font=None) -> int:
        font = font or self.body
        self.surface.blit(font.render(value, True, color), (x, y))
        return y + font.get_linesize()

    def wrapped(self, x: int, y: int, width: int, value: str, color=INK,
                font=None) -> int:
        font = font or self.small
        line = ""
        for word in value.split():
            probe = f"{line} {word}".strip()
            if font.size(probe)[0] > width and line:
                y = self.text(x, y, line, color, font)
                line = word
            else:
                line = probe
        if line:
            y = self.text(x, y, line, color, font)
        return y

    def section(self, x: int, y: int, value: str) -> int:
        """A quiet uppercase label. Spacing does the separating, not rules."""
        return self.text(x, y, value.upper(), FAINT, self.label) + 6

    def button(self, rect: pygame.Rect, label: str, key: str | None = None,
               primary: bool = False) -> bool:
        self.rects[key or label] = rect
        held = self.press is not None and rect.collidepoint(self.press)
        if primary:
            fill, ink = (ACCENT_DOWN if held else ACCENT), ACCENT_INK
        else:
            fill, ink = (SURFACE_HI if held else SURFACE), INK
        radius = rect.height // 2
        pygame.draw.rect(self.surface, fill, rect, border_radius=radius)
        if not primary:
            pygame.draw.rect(self.surface, LINE, rect, width=1, border_radius=radius)
        text = self.body.render(label, True, ink)
        self.surface.blit(text, text.get_rect(center=rect.center))
        return self.click is not None and rect.collidepoint(self.click)

    def chips(self, x: int, y: int, width: int, values, current, labels=None,
              key: str | None = None, height: int = 26):
        """A row of selectable values. Returns the value after any click."""
        labels = labels or [str(v) for v in values]
        gap = 5
        chip_w = (width - gap * (len(values) - 1)) // len(values)
        picked = current
        for i, value in enumerate(values):
            rect = pygame.Rect(x + i * (chip_w + gap), y, chip_w, height)
            if key is not None:
                self.rects[f"{key}:{value}"] = rect
            selected = value == current
            held = self.press is not None and rect.collidepoint(self.press)
            fill = ACCENT if selected else (SURFACE_HI if held else SURFACE)
            pygame.draw.rect(self.surface, fill, rect, border_radius=7)
            if not selected:
                pygame.draw.rect(self.surface, LINE, rect, width=1, border_radius=7)
            font = self.mono_small if labels[i].isdigit() else self.small
            text = font.render(labels[i], True, ACCENT_INK if selected else INK)
            self.surface.blit(text, text.get_rect(center=rect.center))
            if self.click is not None and rect.collidepoint(self.click):
                picked = value
        return picked, y + height

    def slider(self, key: str, x: int, y: int, width: int, lo: int, hi: int,
               step: int, current: int):
        """Returns (value, committed). Committed only on release.

        The web binds its range input to `change`, which fires once when the
        thumb is let go — and every restart throws away an encoder pool, so a
        value per pixel of drag would be brutal. The drag has to survive across
        frames, so this one control keeps state.
        """
        hit = pygame.Rect(x - 10, y, width + 20, 24)
        self.rects[key] = hit
        if self._drag is None and self.press is not None and hit.collidepoint(self.press):
            self._drag = key

        value = current
        if self._drag == key:
            mouse_x = pygame.mouse.get_pos()[0]
            ratio = min(1.0, max(0.0, (mouse_x - x) / max(1, width)))
            value = lo + round(ratio * (hi - lo) / step) * step

        committed = False
        if self._drag == key and self.drag_released:
            self._drag = None
            committed = True

        mid = y + 11
        pygame.draw.rect(self.surface, SURFACE, pygame.Rect(x, mid - 2, width, 4),
                         border_radius=2)
        filled = (value - lo) / (hi - lo)
        pygame.draw.rect(self.surface, ACCENT,
                         pygame.Rect(x, mid - 2, int(width * filled), 4), border_radius=2)
        knob = (x + int(width * filled), mid)
        pygame.draw.circle(self.surface, INK, knob, 8)
        pygame.draw.circle(self.surface, ACCENT, knob, 8, width=2)
        return value, committed

    def spec(self, x: int, y: int, width: int, label: str, value: str) -> int:
        """Label left, value right in mono so digits stop dancing as they update."""
        self.surface.blit(self.small.render(label, True, MUTED), (x, y))
        text = self.mono.render(value, True, INK)
        self.surface.blit(text, (x + width - text.get_width(), y + 1))
        return y + 21

    def note(self, x: int, y: int, width: int, value: str, color=INK,
             tint=SURFACE) -> int:
        """A rounded slab, so the status line reads as one thing."""
        inner = width - 24
        lines, line = [], ""
        for word in value.split():
            probe = f"{line} {word}".strip()
            if self.small.size(probe)[0] > inner and line:
                lines.append(line)
                line = word
            else:
                line = probe
        if line:
            lines.append(line)
        height = 16 + len(lines) * self.small.get_linesize()
        pygame.draw.rect(self.surface, tint, pygame.Rect(x, y, width, height),
                         border_radius=8)
        text_y = y + 8
        for entry in lines:
            self.surface.blit(self.small.render(entry, True, color), (x + 12, text_y))
            text_y += self.small.get_linesize()
        return y + height

    def dot(self, x: int, y: int, color) -> None:
        pygame.draw.circle(self.surface, color, (x, y), 4)
