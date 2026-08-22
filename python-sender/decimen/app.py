"""The sender: one pygame window, a control panel beside the QR stream.

Everything is pygame, including the controls, which pygame does not have — see
`ui.py`. The alternative was tkinter for the panel, and on macOS tkinter and
SDL both want to be the NSApplication: the panel came up but never received a
click. One toolkit avoids the question entirely.

One window rather than two, because several SDL windows need a semi-private
API. The camera only ever frames the QR area, so the panel beside it costs
screen space and nothing else.

Changing any setting restarts the stream, exactly as the web sender does
(send/main.ts:454). Only bytes-per-frame *has* to: it moves `k` and `blockLen`,
which the receiver reads as a different stream. The other four could apply
live, and deliberately do not — matching the reference sender beats saving the
receiver's progress, so nobody ever has to wonder whether the two behave alike.
"""

from __future__ import annotations

import mimetypes
import os
import pathlib
import platform
import random
import subprocess
import time

import pygame

from . import protocol as p
from . import send_settings as cfg
from . import ui as theme
from .frame_capacity import (
    MAX_SOURCE_BLOCKS,
    block_length,
    fits_in_one_stream,
    smallest_sufficient_frame_size,
    source_block_count,
)
from .fountain import LTEncoder
from .pool import FrameSource
from .ui import UI

SIDEBAR_W = 320
PAD = 20
INNER = SIDEBAR_W - 2 * PAD
MIN_HEIGHT = 780
IDLE_SIZE = 520


class SenderApp:
    def __init__(self):
        self.packed = None
        self.payload_label = "nothing picked yet"
        self.source = None
        self.codes = 1
        self.target_fps = cfg.DEFAULT_TX_FPS
        self.shown = 0
        self.t0 = 0.0
        self.rate_window = []
        self.achieved = "—"
        self.caffeinate = None
        self.awake = False
        self.running = True
        self.status = ("Drop a file on the stream area, or use the buttons. "
                       "Open decimen.app/receive on the other device.")
        self.status_error = False
        self.snippet = None          # open editor buffer, or None
        self.frame_rgb = None

        self.settings = {
            "fps": cfg.DEFAULT_TX_FPS,
            "bytes": cfg.DEFAULT_FRAME_BYTES,
            "ecc": cfg.DEFAULT_ECC,
            "codes": cfg.DEFAULT_GRID,
            "size": cfg.DEFAULT_DISPLAY_SIZE,
        }
        self.specs = {"rate": "—", "frame": "—", "qr": "—", "payload": "—",
                      "compression": "—", "k": "—"}

        pygame.init()
        pygame.key.set_repeat(400, 40)
        self.screen = pygame.display.set_mode((SIDEBAR_W + IDLE_SIZE, MIN_HEIGHT))
        pygame.display.set_caption("decimen sender")
        _set_icon()
        self.panel = pygame.Surface((SIDEBAR_W, MIN_HEIGHT))
        self.ui = UI(self.panel)
        self.panel_dirty = True

    # --------------------------------------------------------------- panel

    def _draw_panel(self) -> None:
        self.ui.rects.clear()
        self.panel.fill(theme.BG)
        pygame.draw.line(self.panel, theme.LINE, (SIDEBAR_W - 1, 0),
                         (SIDEBAR_W - 1, self.panel.get_height()))
        ui = self.ui
        x, y = PAD, PAD

        ui.text(x, y, "decimen", theme.INK, ui.strong)
        ui.dot(SIDEBAR_W - PAD - 4, y + 8,
               theme.LIVE if self.source is not None else theme.LINE)
        y = ui.text(x, y + 18, "optical transfer · sender", theme.FAINT, ui.small) + 18

        y = ui.section(x, y, "Send")
        if ui.button(pygame.Rect(x, y, 150, 32), "Choose file…", key="file",
                     primary=True):
            self._choose_file()
        if ui.button(pygame.Rect(x + 158, y, 122, 32), "Snippet…", key="snippet"):
            self.snippet = ""
            pygame.key.start_text_input()
        y += 42
        y = ui.wrapped(x, y, INNER, self.payload_label, theme.MUTED) + 20

        y = ui.section(x, y, "Transfer")
        for key, label, values, labels, suffix in (
            ("fps", "tx fps", cfg.TX_FPS_OPTIONS, None, ""),
            ("bytes", "bytes / frame", cfg.FRAME_BYTES_OPTIONS, None, ""),
            ("ecc", "error correction", cfg.ECC_OPTIONS, None, ""),
            ("codes", "layout", [n for _, n in cfg.GRID_OPTIONS],
             [str(n) for _, n in cfg.GRID_OPTIONS], " codes"),
        ):
            y = self._control_label(x, y, label, f"{self.settings[key]}{suffix}")
            picked, y = ui.chips(x, y, INNER, values, self.settings[key], labels,
                                 key=key)
            y += 12
            if picked != self.settings[key]:
                self.settings[key] = picked
                self.restart()

        y = self._control_label(x, y, "display size", f"{self.settings['size']} px")
        size, committed = ui.slider("size", x, y, INNER, cfg.DISPLAY_SIZE_MIN,
                                    cfg.DISPLAY_SIZE_MAX, cfg.DISPLAY_SIZE_STEP,
                                    self.settings["size"])
        y += 30
        if size != self.settings["size"]:
            self.settings["size"] = size
        if committed:
            self.restart()

        y = ui.section(x, y + 6, "Stream")
        self.specs["rate"] = self.achieved
        for key, label in (("rate", "tx rate"), ("frame", "frame"), ("qr", "QR"),
                           ("payload", "payload"), ("compression", "compression"),
                           ("k", "source blocks")):
            y = ui.spec(x, y, INNER, label, self.specs[key])

        # Flow, not anchored to the bottom edge: a two-line payload name or a
        # long error grows the status slab, and a fixed offset put the hint
        # underneath it.
        y = ui.note(x, y + 14, INNER, self.status,
                    theme.ERROR if self.status_error else theme.MUTED,
                    theme.ERROR_TINT if self.status_error else theme.SURFACE)
        ui.wrapped(x, y + 12, INNER,
                   f"Not picking it up? Try {cfg.NO_SIGNAL_HINT_TX_FPS} fps and "
                   f"{cfg.NO_SIGNAL_HINT_FRAME_BYTES} bytes / frame.", theme.FAINT)

    def _control_label(self, x: int, y: int, label: str, value: str) -> int:
        """Name on the left, the value it currently holds on the right."""
        self.panel.blit(self.ui.small.render(label, True, theme.MUTED), (x, y))
        text = self.ui.mono_small.render(value, True, theme.INK)
        self.panel.blit(text, (x + INNER - text.get_width(), y + 1))
        return y + 19

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error
        self.panel_dirty = True

    # ------------------------------------------------------------- payload

    def _choose_file(self) -> None:
        """No file dialog in pygame, so borrow the platform's.

        macOS: `choose file` is a Standard Additions command and needs no
        automation permission, unlike anything routed through System Events.
        Windows: PowerShell can put a WinForms dialog on screen, but only from
        a single-threaded apartment, hence `-STA`.

        Either way a failure is not fatal — dropping a file on the stream area
        always works, so the dialog is a convenience, never the only way in.
        """
        system = platform.system()
        if system == "Darwin":
            command = ["osascript", "-e",
                       'POSIX path of (choose file with prompt "Send a file over light")']
        elif system == "Windows":
            command = ["powershell", "-NoProfile", "-STA", "-Command",
                       "Add-Type -AssemblyName System.Windows.Forms; "
                       "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                       "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"]
        else:
            self._set_status("Drop a file on the stream area to send it.", error=True)
            return
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            self._set_status("Could not open the file dialog. Drop a file instead.",
                             error=True)
            return
        path = done.stdout.strip()
        if done.returncode != 0 or not path:
            return                                   # cancelled
        self._load(pathlib.Path(path))

    def _load(self, path: pathlib.Path) -> None:
        try:
            media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.packed = p.pack_file(path.name, media, path.read_bytes())
        except (OSError, p.OpticalError) as exc:
            self._set_status(f"Could not send {path.name}: {exc}", error=True)
            return
        self.payload_label = f"{path.name} · {_bytes(self.packed.original_size)}"
        self.restart()

    def _send_snippet(self, text: str) -> None:
        try:
            self.packed = p.pack_snippet(text)
        except p.OpticalError as exc:
            self._set_status(f"Snippet not sent: {exc.code}", error=True)
            return
        self.payload_label = f"snippet.txt · {_bytes(self.packed.original_size)}"
        self.restart()

    # -------------------------------------------------------------- stream

    def restart(self) -> None:
        """Any setting change starts a fresh stream, as the web sender does.

        Dropping the old FrameSource cancels its outstanding work; the loop is
        single-threaded, so a discarded source is simply unreachable and no
        generation counter is needed to fence it off.
        """
        self.panel_dirty = True
        if self.packed is None:
            return
        if self.source is not None:
            self.source.close()
            self.source = None
        self.frame_rgb = None

        container = self.packed.container
        frame_bytes = self.settings["bytes"]
        block_len = block_length(frame_bytes)
        codes = self.settings["codes"]
        ecc = self.settings["ecc"]

        if not fits_in_one_stream(len(container), frame_bytes):
            # Keep the pick: raising bytes/frame is the fix, and dropping the
            # file would hide that. Name a value that is on the chip row.
            suggestion = smallest_sufficient_frame_size(len(container),
                                                        cfg.FRAME_BYTES_OPTIONS)
            self._set_status(
                f"Needs {source_block_count(len(container), frame_bytes):,} blocks "
                f"at {frame_bytes} bytes / frame, and a stream carries at most "
                f"{MAX_SOURCE_BLOCKS:,}. Try {suggestion}.", error=True)
            return

        session_id = random.randint(1, 0xFFFF)      # random per sender start
        encoder = LTEncoder(container, block_len, session_id)
        header = p.FrameHeader(
            session_id=session_id, seq=0, k=encoder.k, block_len=block_len,
            total_len=len(container), payload_fnv=p.fnv1a(container), flags=0,
        )
        self.source = FrameSource(container, block_len, session_id, header, ecc,
                                  codes, self.settings["size"])
        self.codes = codes
        self.target_fps = self.settings["fps"]
        self.shown = 0
        self.t0 = time.perf_counter()
        self.rate_window.clear()
        self._keep_awake()

        tiling = f" x{codes}" if codes > 1 else ""
        self.specs.update(
            frame=f"{frame_bytes} B{tiling}",
            qr=f"V{self.source.version}{tiling} · {ecc}",
            payload=self.payload_label.split(" · ")[0][:20],
            compression=("gzip " + _bytes(self.packed.transmitted_size))
            if self.packed.compression == "gzip" else "none",
            k=f"{encoder.k:,}",
        )
        self._set_status("Streaming. Changing any setting restarts the stream.")

    def _keep_awake(self) -> None:
        """A 40 MB transfer at 20 fps runs for minutes; the screensaver would
        kill it mid-flight.

        macOS: `caffeinate -w <pid>` waits on this process and exits with it.
        That matters more than a tidy terminate() — cleanup does not run when
        the sender is killed, and a caffeinate left behind keeps the machine
        awake indefinitely.

        Windows: SetThreadExecutionState is scoped to the calling thread and
        released when the process ends, so it needs no undoing. UNTESTED — see
        the platform note on the map.
        """
        if self.awake:
            return
        system = platform.system()
        if system == "Darwin":
            try:
                self.caffeinate = subprocess.Popen(
                    ["caffeinate", "-di", "-w", str(os.getpid())])
                self.awake = True
            except OSError:
                pass
        elif system == "Windows":
            try:
                import ctypes
                ES_CONTINUOUS, ES_SYSTEM, ES_DISPLAY = 0x80000000, 0x1, 0x2
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM | ES_DISPLAY)
                self.awake = True
            except Exception:
                pass

    # ----------------------------------------------------------- main loop

    def _next_frame(self) -> None:
        try:
            width, height, rgb = self.source.next()
        except Exception as exc:                    # a worker died mid-stream
            self.source.close()
            self.source = None
            self._set_status(f"The encoder pool stopped: {exc}. "
                             "Pick the payload again to restart.", error=True)
            return
        self.frame_rgb = (width, height, rgb)
        self._fit_window(width, height)
        self.shown += 1

        now = time.perf_counter()
        self.rate_window.append(now)
        while self.rate_window and now - self.rate_window[0] > 1.0:
            self.rate_window.pop(0)
        if len(self.rate_window) > 1:
            # What actually reaches the screen, not what was asked for: a knob
            # that no longer does anything should say so.
            achieved = f"{len(self.rate_window) - 1} / {self.target_fps} fps"
            if achieved != self.achieved:
                self.achieved = achieved
                self.panel_dirty = True

    def _fit_window(self, qr_w: int, qr_h: int) -> None:
        want = (SIDEBAR_W + qr_w, max(MIN_HEIGHT, qr_h))
        if self.screen.get_size() != want:
            self.screen = pygame.display.set_mode(want)
            self.panel = pygame.Surface((SIDEBAR_W, want[1]))
            self.ui.surface = self.panel
            self.panel_dirty = True

    def _blit(self) -> None:
        self.screen.fill(theme.STAGE)
        area = pygame.Rect(SIDEBAR_W, 0, self.screen.get_width() - SIDEBAR_W,
                           self.screen.get_height())
        if self.snippet is not None:
            self._blit_snippet(area)
        elif self.frame_rgb is not None:
            width, height, rgb = self.frame_rgb
            surface = pygame.image.frombuffer(rgb, (width, height), "RGB")
            self.screen.blit(surface, surface.get_rect(center=area.center))
        else:
            box = pygame.Rect(0, 0, 260, 120)
            box.center = area.center
            pygame.draw.rect(self.screen, theme.LINE, box, width=2, border_radius=12)
            label = self.ui.body.render("Drop a file here", True, theme.MUTED)
            self.screen.blit(label, label.get_rect(center=box.center))
        self.screen.blit(self.panel, (0, 0))
        pygame.display.flip()

    def _blit_snippet(self, area: pygame.Rect) -> None:
        box = area.inflate(-72, -72)
        pygame.draw.rect(self.screen, theme.BG, box, border_radius=12)
        pygame.draw.rect(self.screen, theme.LINE, box, width=1, border_radius=12)
        y = box.y + 14
        for line in (self.snippet or "").split("\n"):
            for chunk in _wrap(line, self.ui.body, box.width - 28) or [""]:
                self.screen.blit(self.ui.body.render(chunk, True, theme.INK),
                                 (box.x + 14, y))
                y += 22
        hint = self.ui.small.render(
            "Enter sends · Shift+Enter for a new line · Esc cancels", True, theme.FAINT)
        self.screen.blit(hint, (box.x + 14, box.bottom - 26))

    def _handle_snippet_keys(self) -> None:
        for kind, value in self.ui.text_events:
            if kind == "text":
                self.snippet += value
            elif value == pygame.K_BACKSPACE:
                self.snippet = self.snippet[:-1]
            elif value == pygame.K_ESCAPE:
                self.snippet = None
                pygame.key.stop_text_input()
                return
            elif value == pygame.K_RETURN:
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    self.snippet += "\n"
                else:
                    text, self.snippet = self.snippet, None
                    pygame.key.stop_text_input()
                    self._send_snippet(text)
                    return

    def run(self) -> None:
        # try/finally, not a trailing call: anything raising in here would
        # otherwise leak twelve worker processes and a caffeinate, and the
        # process would never exit.
        try:
            self._loop()
        finally:
            self._shutdown()

    def _loop(self) -> None:
        while self.running:
            self._tick()

    def _tick(self) -> None:
        """One pass: events, a frame, the panel, the blit, the pacing."""
        events = pygame.event.get()
        self.ui.begin(events)
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.DROPFILE:
                self.snippet = None
                self._load(pathlib.Path(event.file))
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                                pygame.KEYDOWN, pygame.TEXTINPUT,
                                pygame.MOUSEMOTION):
                self.panel_dirty = True

        if self.snippet is not None:
            self._handle_snippet_keys()
        if self.source is not None and self.snippet is None:
            self._next_frame()
        if self.panel_dirty:
            # Rebuilding the panel is also what hit-tests it, so any frame
            # carrying a click has to redraw before the click is consumed.
            self._draw_panel()
            self.panel_dirty = False
        self._blit()

        if self.source is None or self.snippet is not None:
            time.sleep(0.02)
            return
        target = self.t0 + self.shown / self.target_fps
        if (wait := target - time.perf_counter()) > 0:
            time.sleep(wait)

    def _shutdown(self) -> None:
        if self.source is not None:
            self.source.close()
        if self.caffeinate is not None:
            self.caffeinate.terminate()
        pygame.quit()


def _wrap(line: str, font, width: int):
    out, current = [], ""
    for word in line.split():
        probe = f"{current} {word}".strip()
        if font.size(probe)[0] > width and current:
            out.append(current)
            current = word
        else:
            current = probe
    if current:
        out.append(current)
    return out


ICON = pathlib.Path(__file__).with_name("icon.png")


def _set_icon() -> None:
    """The project's own icon, so both senders look like one product.

    `set_icon` covers Windows and Linux. macOS takes the Cmd-Tab and Dock icon
    from the application, not the window, so it needs a second route: handing
    the image to NSApplication at runtime. pyobjc is a macOS-only dependency
    and its absence is not worth failing a launch over — without it the window
    still carries the icon, only the Dock keeps showing Python's.
    """
    if not ICON.exists():
        return
    try:
        pygame.display.set_icon(pygame.image.load(str(ICON)))
    except pygame.error:
        return
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        image = NSImage.alloc().initWithContentsOfFile_(str(ICON))
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        pass


def _bytes(n: int) -> str:
    for unit, size in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} B"


def main() -> int:
    SenderApp().run()
    return 0
