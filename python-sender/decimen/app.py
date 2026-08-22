"""The sender: a control window and a stream window.

Two ordinary windows with title bars, in one process. tkinter owns the
controls because pygame has no widgets at all; pygame owns the stream because
tkinter cannot hold the frame rate. Both event loops are pumped from the same
loop — on macOS that is the only arrangement that works, since Cocoa wants
window work on the main thread.

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
import tkinter as tk
from tkinter import filedialog, ttk

import pygame

from . import protocol as p
from . import send_settings as cfg
from .frame_capacity import (
    MAX_SOURCE_BLOCKS,
    block_length,
    fits_in_one_stream,
    smallest_sufficient_frame_size,
    source_block_count,
)
from .fountain import LTEncoder
from .pool import FrameSource


class SenderApp:
    def __init__(self):
        self.packed = None
        self.payload_label = "—"
        self.source = None
        self.screen = None
        self.caffeinate = None
        self.shown = 0
        self.t0 = 0.0
        self.rate_window = []
        self.running = True

        self.root = tk.Tk()
        self.root.title("decimen sender")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self._build_controls()
        pygame.init()
        self._set_status(
            "Choose a file or a text snippet. Open decimen.app/receive on the "
            "other device and point it at the stream window."
        )

    # ------------------------------------------------------------- controls

    def _build_controls(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        row = 0

        def heading(text: str) -> None:
            nonlocal row
            if row:
                ttk.Separator(frame).grid(row=row, column=0, columnspan=2,
                                          sticky="ew", pady=(12, 10))
                row += 1
            ttk.Label(frame, text=text, font=("", 13, "bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
            row += 1

        heading("Send")
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Choose file…", command=self.choose_file).pack(side="left")
        ttk.Button(buttons, text="Text snippet…", command=self.choose_snippet).pack(
            side="left", padx=6)
        row += 1
        self.payload_line = ttk.Label(frame, text="nothing picked yet",
                                      foreground="#666", wraplength=330)
        self.payload_line.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        row += 1
        ttk.Label(frame, text="…or drop a file on the stream window.",
                  foreground="#999").grid(row=row, column=0, columnspan=2,
                                          sticky="w", pady=(2, 0))
        row += 1

        heading("Transfer settings")
        self.controls = {}
        for key, label, values, default in (
            ("fps", "tx fps", cfg.TX_FPS_OPTIONS, cfg.DEFAULT_TX_FPS),
            ("bytes", "bytes / frame", cfg.FRAME_BYTES_OPTIONS, cfg.DEFAULT_FRAME_BYTES),
            ("ecc", "error correction", cfg.ECC_OPTIONS, cfg.DEFAULT_ECC),
        ):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(default))
            box = ttk.Combobox(frame, textvariable=var, state="readonly", width=12,
                               values=[str(v) for v in values])
            box.grid(row=row, column=1, sticky="e", pady=3)
            box.bind("<<ComboboxSelected>>", lambda _e: self.restart())
            self.controls[key] = var
            row += 1

        ttk.Label(frame, text="layout").grid(row=row, column=0, sticky="w", pady=3)
        self.grid_var = tk.StringVar(value=cfg.GRID_OPTIONS[0][0])
        grid_box = ttk.Combobox(frame, textvariable=self.grid_var, state="readonly",
                                width=12, values=[name for name, _ in cfg.GRID_OPTIONS])
        grid_box.grid(row=row, column=1, sticky="e", pady=3)
        grid_box.bind("<<ComboboxSelected>>", lambda _e: self.restart())
        row += 1

        ttk.Label(frame, text="display size").grid(row=row, column=0, sticky="w", pady=3)
        self.size_var = tk.IntVar(value=cfg.DEFAULT_DISPLAY_SIZE)
        scale = ttk.Scale(frame, from_=cfg.DISPLAY_SIZE_MIN, to=cfg.DISPLAY_SIZE_MAX,
                          variable=self.size_var, orient="horizontal")
        scale.grid(row=row, column=1, sticky="ew", pady=3)
        # On release, never per increment. The web binds the range input to
        # `change`, which fires once when the thumb is let go; tkinter's Scale
        # would otherwise restart the stream on every step of the drag.
        scale.bind("<ButtonRelease-1>", lambda _e: self.restart())
        row += 1

        heading("Stream")
        self.specs = {}
        for key, label in (("rate", "tx rate"), ("frame", "frame"), ("qr", "QR"),
                           ("payload", "payload"), ("compression", "compression"),
                           ("k", "K")):
            ttk.Label(frame, text=label, foreground="#777").grid(row=row, column=0,
                                                                sticky="w")
            value = ttk.Label(frame, text="—")
            value.grid(row=row, column=1, sticky="e")
            self.specs[key] = value
            row += 1

        frame.rowconfigure(row, weight=1)
        row += 1
        self.status = ttk.Label(frame, text="", wraplength=330, foreground="#444")
        self.status.grid(row=row, column=0, columnspan=2, sticky="w", pady=(14, 0))
        row += 1
        # The receiver carries the "nothing is decoding?" hint, and it has to:
        # a screen-to-camera link has no back-channel, so this side cannot know
        # whether anything is arriving. The advice still belongs here, just
        # without a trigger to hang it on.
        ttk.Label(frame, foreground="#999", wraplength=330,
                  text=(f"Not picking it up? Try {cfg.NO_SIGNAL_HINT_TX_FPS} fps and "
                        f"{cfg.NO_SIGNAL_HINT_FRAME_BYTES} bytes / frame.")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.config(text=text, foreground="#a00" if error else "#444")

    # -------------------------------------------------------------- payload

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(parent=self.root)
        if not path:
            return
        path = pathlib.Path(path)
        try:
            data = path.read_bytes()
            media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.packed = p.pack_file(path.name, media, data)
        except (OSError, p.OpticalError) as exc:
            self._set_status(f"Could not send {path.name}: {exc}", error=True)
            return
        self.payload_label = f"{path.name} · {_bytes(self.packed.original_size)}"
        self.payload_line.config(text=self.payload_label)
        self.restart()

    def choose_snippet(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Text snippet")
        dialog.transient(self.root)
        text = tk.Text(dialog, width=52, height=12, wrap="word")
        text.pack(padx=12, pady=12, fill="both", expand=True)
        text.focus_set()

        def send() -> None:
            body = text.get("1.0", "end-1c")
            dialog.destroy()
            try:
                self.packed = p.pack_snippet(body)
            except p.OpticalError as exc:
                self._set_status(f"Snippet not sent: {exc.code}", error=True)
                return
            self.payload_label = f"snippet.txt · {_bytes(self.packed.original_size)}"
            self.payload_line.config(text=self.payload_label)
            self.restart()

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(bar, text="Send", command=send).pack(side="right")
        ttk.Button(bar, text="Cancel", command=dialog.destroy).pack(side="right", padx=6)

    # --------------------------------------------------------------- stream

    def restart(self) -> None:
        """Any setting change starts a fresh stream, as the web sender does.

        Dropping the old FrameSource cancels its outstanding work; the render
        loop is single-threaded, so a discarded source is simply unreachable
        and no generation counter is needed to fence it off.
        """
        if self.packed is None:
            return
        if self.source is not None:
            self.source.close()
            self.source = None

        container = self.packed.container
        frame_bytes = int(self.controls["bytes"].get())
        block_len = block_length(frame_bytes)
        codes = dict(cfg.GRID_OPTIONS)[self.grid_var.get()]
        ecc = self.controls["ecc"].get()

        if not fits_in_one_stream(len(container), frame_bytes):
            # Keep the pick: raising bytes/frame is the fix, and dropping the
            # file would hide that. Name a value that is in the dropdown.
            suggestion = smallest_sufficient_frame_size(len(container),
                                                        cfg.FRAME_BYTES_OPTIONS)
            self._set_status(
                f"{self.payload_label} needs "
                f"{source_block_count(len(container), frame_bytes):,} blocks at "
                f"{frame_bytes} bytes / frame, and a stream carries at most "
                f"{MAX_SOURCE_BLOCKS:,}. Try {suggestion} bytes / frame.",
                error=True,
            )
            return

        session_id = random.randint(1, 0xFFFF)   # random per sender start
        encoder = LTEncoder(container, block_len, session_id)
        header = p.FrameHeader(
            session_id=session_id, seq=0, k=encoder.k, block_len=block_len,
            total_len=len(container), payload_fnv=p.fnv1a(container), flags=0,
        )
        self.source = FrameSource(container, block_len, session_id, header, ecc,
                                  codes, self.size_var.get())
        self.codes = codes
        self.target_fps = int(self.controls["fps"].get())
        self.shown = 0
        self.t0 = time.perf_counter()
        self.rate_window.clear()
        self.screen = None
        self._start_caffeinate()

        tiling = f" x{codes}" if codes > 1 else ""
        self.specs["frame"].config(text=f"{frame_bytes} B{tiling}")
        self.specs["qr"].config(text=f"V{self.source.version}{tiling} · ECC {ecc}")
        self.specs["payload"].config(text=self.payload_label)
        self.specs["compression"].config(
            text=("gzip to " + _bytes(self.packed.transmitted_size))
            if self.packed.compression == "gzip" else "none")
        self.specs["k"].config(text=f"K = {encoder.k:,}")
        self._set_status(f"Streaming {self.payload_label}. "
                         "Changing any setting restarts the stream.")

    def _start_caffeinate(self) -> None:
        """A 40 MB transfer at 20 fps runs for minutes; the screensaver would
        kill it mid-flight.

        `-w <pid>` makes caffeinate wait on this process and exit with it. That
        matters more than the tidy terminate() in _shutdown: a finally block
        does not run when the sender is killed, and a caffeinate left behind
        keeps the machine awake indefinitely.
        """
        if self.caffeinate is not None or platform.system() != "Darwin":
            return
        try:
            self.caffeinate = subprocess.Popen(
                ["caffeinate", "-di", "-w", str(os.getpid())])
        except OSError:
            self.caffeinate = None

    # ----------------------------------------------------------- main loop

    def _draw(self) -> None:
        try:
            width, height, rgb = self.source.next()
        except Exception as exc:                      # a worker died mid-stream
            self.source.close()
            self.source = None
            self._set_status(f"The encoder pool stopped: {exc}. "
                             "Pick the payload again to restart.", error=True)
            return
        if self.screen is None or self.screen.get_size() != (width, height):
            self.screen = pygame.display.set_mode((width, height))
            pygame.display.set_caption("decimen — stream")
        self.screen.blit(pygame.image.frombuffer(rgb, (width, height), "RGB"), (0, 0))
        pygame.display.flip()
        self.shown += 1

        now = time.perf_counter()
        self.rate_window.append(now)
        while self.rate_window and now - self.rate_window[0] > 1.0:
            self.rate_window.pop(0)
        if len(self.rate_window) > 1:
            achieved = len(self.rate_window) - 1
            # Show what is actually reaching the screen, not what was asked
            # for: a knob that no longer does anything should say so.
            self.specs["rate"].config(
                text=f"{achieved} / {self.target_fps} fps"
                     + (f" x{self.codes}" if self.codes > 1 else ""))

    def _pump_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            elif event.type == pygame.DROPFILE:
                path = pathlib.Path(event.file)
                try:
                    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    self.packed = p.pack_file(path.name, media, path.read_bytes())
                except (OSError, p.OpticalError) as exc:
                    self._set_status(f"Could not send {path.name}: {exc}", error=True)
                    continue
                self.payload_label = f"{path.name} · {_bytes(self.packed.original_size)}"
                self.payload_line.config(text=self.payload_label)
                self.restart()

    def quit(self) -> None:
        self.running = False

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
            if self.source is not None:
                self._draw()
            self._pump_events()
            try:
                self.root.update()
            except tk.TclError:
                break
            if self.source is None:
                time.sleep(0.02)
                continue
            target = self.t0 + self.shown / self.target_fps
            if (wait := target - time.perf_counter()) > 0:
                time.sleep(wait)

    def _shutdown(self) -> None:
        if self.source is not None:
            self.source.close()
        if self.caffeinate is not None:
            self.caffeinate.terminate()
        pygame.quit()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def _bytes(n: int) -> str:
    for unit, size in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} B"


def main() -> int:
    SenderApp().run()
    return 0
