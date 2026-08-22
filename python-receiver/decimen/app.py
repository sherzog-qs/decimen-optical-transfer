"""The receiver: pick a screen region, watch the file arrive off it.

One pygame window — a sidebar of numbers and the recommendation on the left, a
live preview of the captured region on the right. The capture-and-decode work
runs in ReceiverEngine's background thread; this loop only reads snapshots and
draws, so a slow-drawing window never throttles the catch rate.

Citrix-agnostic: the engine decodes whatever is in the region, never asking
what is underneath. The recommendation targets sender settings — the only
thing the user can change — and appears only when the catch rate stays low.
"""

from __future__ import annotations

import os
import pathlib
import time

import numpy as np
import pygame

from . import platform_bits as plat
from . import send_settings_hint as hint
from . import ui as theme
from .engine import ReceiverEngine
from .protocol import snippet_text
from .select_region import select_region

SIDEBAR_W = 320
PAD = 20
INNER = SIDEBAR_W - 2 * PAD
MIN_HEIGHT = 720
PREVIEW_W = 520

# Below this useful-frames-per-second, held for a few seconds, the recommendation
# appears. Above it the stream is fine and any advice is just noise.
LOW_CATCH = 6.0
LOW_CATCH_SECONDS = 4.0


def throughput_kb(snap) -> str:
    """Payload actually landing, in kB/s: useful frames per second times the
    block each one carries. It is wire payload — a compressed stream writes a
    bigger file than this number suggests."""
    return f"{snap.catch_rate * snap.block_len / 1000:.1f} kB/s"


def time_left(snap) -> str:
    if snap.complete:
        return "done"
    left = snap.frames_needed - snap.frames_collected
    if left <= 0 or snap.catch_rate <= 0:
        return "—"
    secs = round(left / snap.catch_rate)
    return f"{secs}s" if secs < 90 else f"{secs // 60}m {secs % 60}s"


class ReceiverApp:
    def __init__(self):
        pygame.init()
        pygame.key.set_repeat(0)
        self.screen = pygame.display.set_mode((SIDEBAR_W + PREVIEW_W, MIN_HEIGHT))
        pygame.display.set_caption("decimen receiver")
        plat.set_icon()
        self.panel = pygame.Surface((SIDEBAR_W, MIN_HEIGHT))
        self.ui = theme.UI(self.panel)
        self.awake = plat.KeepAwake()

        self.engine: ReceiverEngine | None = None
        self.region = None
        # Without screen-recording permission, capture sees only the desktop —
        # other windows are invisible. Check up front and, if missing, register
        # in the list and tell the user plainly rather than capturing nothing.
        from .capture import has_screen_permission, request_screen_permission
        if has_screen_permission():
            self.status = "Press Space to select the region the QR stream plays in."
            self.status_error = False
            self.blocked = False
        else:
            request_screen_permission()
            self.status = ("Screen Recording permission is needed to read another "
                           "window. Grant it in System Settings › Privacy & "
                           "Security › Screen Recording (add your terminal or "
                           "Python), then relaunch.")
            self.status_error = True
            self.blocked = True
        # The file we already handled. Cancelling the save must not re-open the
        # dialog every frame, so the guard hangs on the file object, not on
        # whether a path came back.
        self._offered = None
        self._low_since: float | None = None
        self._high_since: float | None = None
        self.running = True

    # ------------------------------------------------------------ region

    def pick_region(self) -> None:
        if self.blocked:
            return                       # no permission — the still would be desktop-only
        # select_region takes the display fullscreen and drags on a frozen
        # still, then re-inits the display subsystem on the way out. Our own
        # window shows in that still — harmless, since the target is the sender
        # area, not us.
        sel = select_region()
        # Rebuild our window after the selector's display teardown.
        self.screen = pygame.display.set_mode((SIDEBAR_W + PREVIEW_W, MIN_HEIGHT))
        self.panel = pygame.Surface((SIDEBAR_W, self.screen.get_height()))
        self.ui.surface = self.panel
        pygame.display.set_caption("decimen receiver")
        plat.set_icon()
        if sel is None:
            return
        from .capture import ScreenRegion
        self.region = ScreenRegion(*sel)
        if self.engine is None:
            self.engine = ReceiverEngine(self.region)
            self.engine.start()
            self.awake.on()
        else:
            self.engine.set_region(self.region)     # re-drag, decoder keeps going
        self.status = "Watching the region. Point it at the QR stream."
        self.status_error = False

    # ------------------------------------------------------------- panel

    def _recommendation(self, snap) -> str | None:
        """Sender settings, from the measured px/module (see the
        Citrix-Robustheit ticket). Two directions off the same number: rescue
        while the catch rate is low, and — once the stream has settled and is
        clearly healthy — what the margin above the threshold would buy."""
        now = time.perf_counter()
        if snap.complete or snap.frames_collected == 0:
            self._low_since = self._high_since = None
            return None
        if snap.catch_rate < LOW_CATCH:
            self._low_since = self._low_since or now
            if now - self._low_since < LOW_CATCH_SECONDS:
                return None
            return hint.recommend(snap.px_per_module, snap.grid_codes)
        self._low_since = None
        # Advice to go faster is never urgent, so it waits out the same settling
        # window rather than flashing up on the first good second.
        self._high_since = self._high_since or now
        if now - self._high_since < LOW_CATCH_SECONDS:
            return None
        return hint.headroom(snap.px_per_module, snap.block_len,
                             snap.grid_codes, snap.ecc)

    def _draw_panel(self, snap) -> None:
        self.panel.fill(theme.BG)
        pygame.draw.line(self.panel, theme.LINE, (SIDEBAR_W - 1, 0),
                         (SIDEBAR_W - 1, self.panel.get_height()))
        ui = self.ui
        x, y = PAD, PAD
        ui.text(x, y, "decimen", theme.INK, ui.strong)
        live = self.engine is not None and not snap.complete
        ui.dot(SIDEBAR_W - PAD - 4, y + 8, theme.LIVE if live else theme.LINE)
        y = ui.text(x, y + 18, "optical transfer · receiver", theme.FAINT, ui.small) + 18

        y = ui.section(x, y, "Region")
        if ui.button(pygame.Rect(x, y, INNER, 32),
                     "Select region…" if self.region is None else "Re-select region…",
                     key="pick", primary=self.region is None):
            self._want_pick = True
        y += 44

        if self.engine is not None:
            y = ui.section(x, y, "Progress")
            frac = (snap.frames_collected / snap.frames_needed
                    if snap.frames_needed else 0.0)
            bar = pygame.Rect(x, y, INNER, 8)
            pygame.draw.rect(self.panel, theme.SURFACE, bar, border_radius=4)
            pygame.draw.rect(self.panel, theme.ACCENT if not snap.complete else theme.LIVE,
                             pygame.Rect(x, y, int(INNER * min(1.0, frac)), 8),
                             border_radius=4)
            y += 18
            y = ui.spec(x, y, INNER, "frames", f"{snap.frames_collected} / ~{snap.frames_needed}")
            y = ui.spec(x, y, INNER, "catch rate", f"{snap.catch_rate:.0f}/s")
            y = ui.spec(x, y, INNER, "throughput", throughput_kb(snap))
            y = ui.spec(x, y, INNER, "time left", time_left(snap))
            y = ui.spec(x, y, INNER, "px / module",
                        f"{snap.px_per_module:.1f} · {snap.ecc}")
            y = ui.spec(x, y, INNER, "codes", str(snap.grid_codes or "—"))
            y = ui.spec(x, y, INNER, "K", str(snap.k or "—"))
            y = ui.spec(x, y, INNER, "compression", snap.compression)
            if snap.file is not None:
                y = ui.spec(x, y, INNER, "file", snap.file.name[:20])
            y += 8

        rec = self._recommendation(snap) if self.engine else None
        if rec:
            y = ui.note(x, y, INNER, rec, theme.INK, theme.SURFACE) + 8

        msg = snap.verdict_message or self.status
        err = self.status_error or (snap.verdict_message is not None and not snap.sha256_ok
                                    and snap.complete)
        ui.note(x, self.panel.get_height() - 80, INNER, msg,
                theme.ERROR if err else theme.MUTED,
                theme.ERROR_TINT if err else theme.SURFACE)

    # ------------------------------------------------------------- preview

    def _draw_preview(self, snap) -> None:
        area = pygame.Rect(SIDEBAR_W, 0, PREVIEW_W, self.screen.get_height())
        self.screen.fill(theme.STAGE, area)
        frame = snap.last_frame
        if frame is None:
            label = self.ui.body.render("No region selected", True, theme.MUTED)
            self.screen.blit(label, label.get_rect(center=area.center))
            return
        h, w = frame.shape[:2]
        scale = min((PREVIEW_W - 40) / w, (self.screen.get_height() - 40) / h)
        dw, dh = int(w * scale), int(h * scale)
        surf = pygame.image.frombuffer(np.ascontiguousarray(frame).tobytes(), (w, h), "RGB")
        surf = pygame.transform.smoothscale(surf, (dw, dh))
        self.screen.blit(surf, surf.get_rect(center=area.center))

    # ------------------------------------------------------------- saving

    def _offer(self, snap, force: bool = False) -> None:
        """Once complete and verified: save a file, or show a snippet. Offered
        once per file; S offers the same file again after a cancel."""
        if not snap.complete or snap.file is None or not snap.sha256_ok:
            return
        if snap.file is self._offered and not force:
            return
        self._offered = snap.file
        self.awake.off()
        if snap.file.is_snippet:
            self.status = f"Snippet: {snippet_text(snap.file)}"
            return
        path = plat.save_dialog(snap.file.name)
        if path:
            pathlib.Path(path).write_bytes(snap.file.data)
            self.status = f"Saved to {pathlib.Path(path).name}."
        else:
            self.status = "Not saved. Press S to save it after all."

    # ------------------------------------------------------------- loop

    def run(self) -> None:
        try:
            self._loop()
        finally:
            if self.engine:
                self.engine.stop()
            self.awake.off()
            pygame.quit()

    def _loop(self) -> None:
        self._want_pick = self._want_save = False
        while self.running:
            events = pygame.event.get()
            # ui.begin consumes the mouse events into ui.click; without it the
            # immediate-mode buttons never register a press. The sender learned
            # this the hard way — a panel that draws but never begins() is a
            # panel that ignores every click.
            self.ui.begin(events)
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                    self._want_pick = True
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                    self._want_save = True
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    self.running = False

            snap = self.engine.snapshot() if self.engine else _EMPTY
            self._draw_panel(snap)
            self._draw_preview(snap)
            self.screen.blit(self.panel, (0, 0))
            pygame.display.flip()

            self._offer(snap, force=self._want_save)
            self._want_save = False
            if self._want_pick:
                self._want_pick = False
                self.pick_region()
            time.sleep(1 / 30)


class _Empty:
    frames_collected = frames_needed = k = block_len = grid_codes = 0
    px_per_module = catch_rate = 0.0
    compression = "—"
    ecc = "L"
    complete = sha256_ok = False
    verdict_message = None
    last_frame = None
    file = None


_EMPTY = _Empty()


def main() -> int:
    ReceiverApp().run()
    return 0
