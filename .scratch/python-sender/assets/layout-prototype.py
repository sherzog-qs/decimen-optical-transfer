"""Wegwerf-Prototyp fuer Ticket "Fensteraufteilung".

Zwei Fenster: tkinter fuer die Bedienung, pygame fuer den Strom. Beide im
selben Prozess, beide Ereignisschleifen in einem Durchlauf gepumpt.

Es geht um die Aufteilung, nicht um den Sender. Kein Drag & Drop, keine
Kapazitaetspruefung, keine Fehlerbehandlung, keine No-Signal-Zeitpolitik.

    uv run python ../../../.scratch/python-sender/assets/layout-prototype.py
    ... --seconds 5                     # beendet sich von selbst
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import sys
import time
import tkinter as tk
from tkinter import filedialog, ttk

CONTROL_POS = (40, 80)
STREAM_POS = (440, 80)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "python-sender"))

FPS_OPTIONS = [10, 15, 20, 24, 30, 55, 60]
BYTES_OPTIONS = [500, 1000, 1465, 1850, 2331, 2953]
ECC_OPTIONS = ["L", "M", "Q", "H"]
GRID_OPTIONS = [("1 code", 1), ("2 codes (1x2)", 2), ("4 codes (2x2)", 4), ("6 codes (2x3)", 6)]

os.environ.setdefault("SDL_VIDEO_WINDOW_POS", f"{STREAM_POS[0]},{STREAM_POS[1]}")

from decimen import protocol as p           # noqa: E402
from decimen import qr as q                 # noqa: E402
from decimen.fountain import LTEncoder      # noqa: E402
from decimen.frame_capacity import block_length  # noqa: E402

import pygame                               # noqa: E402

SNIPPET = "Prototype stream. Layout only — this is not the sender."


class Prototype:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self.generation = 0
        self.stream = None
        self.screen = None
        self.payload = p.pack_snippet(SNIPPET)
        self.label = f"snippet.txt · {self.payload.original_size} B"

        self.root = tk.Tk()
        self.root.title("decimen sender")
        self.root.geometry(f"380x600+{CONTROL_POS[0]}+{CONTROL_POS[1]}")
        self._build()
        pygame.init()
        self.restart()

    # ---------------------------------------------------------- Bedienung
    def _build(self):
        pad = dict(padx=12, pady=(0, 6), sticky="ew")
        f = ttk.Frame(self.root, padding=12)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(f, text="Send", font=("", 13, "bold")).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        bar = ttk.Frame(f)
        bar.grid(row=row, column=0, columnspan=2, **pad)
        ttk.Button(bar, text="Choose file…", command=self.pick_file).pack(side="left")
        ttk.Button(bar, text="Text snippet", command=self.pick_snippet).pack(side="left", padx=6)
        row += 1
        self.payload_label = ttk.Label(f, text=self.label, foreground="#555")
        self.payload_label.grid(row=row, column=0, columnspan=2, **pad)
        row += 1

        ttk.Separator(f).grid(row=row, column=0, columnspan=2, pady=10, sticky="ew")
        row += 1
        ttk.Label(f, text="Transfer settings", font=("", 13, "bold")).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        self.vars = {}
        for name, values, default in (
            ("tx fps", FPS_OPTIONS, 60),
            ("bytes / frame", BYTES_OPTIONS, 2953),
            ("error correction", ECC_OPTIONS, "L"),
        ):
            ttk.Label(f, text=name).grid(row=row, column=0, sticky="w", padx=(0, 8))
            var = tk.StringVar(value=str(default))
            box = ttk.Combobox(f, textvariable=var, values=[str(v) for v in values],
                               state="readonly", width=10)
            box.grid(row=row, column=1, sticky="e", pady=3)
            box.bind("<<ComboboxSelected>>", lambda _e: self.restart())
            self.vars[name] = var
            row += 1

        ttk.Label(f, text="layout").grid(row=row, column=0, sticky="w")
        self.grid_var = tk.StringVar(value=GRID_OPTIONS[0][0])
        gb = ttk.Combobox(f, textvariable=self.grid_var, state="readonly", width=14,
                          values=[n for n, _ in GRID_OPTIONS])
        gb.grid(row=row, column=1, sticky="e", pady=3)
        gb.bind("<<ComboboxSelected>>", lambda _e: self.restart())
        row += 1

        ttk.Label(f, text="display size").grid(row=row, column=0, sticky="w")
        self.size_var = tk.IntVar(value=900)
        scale = ttk.Scale(f, from_=300, to=1200, variable=self.size_var, orient="horizontal")
        scale.grid(row=row, column=1, sticky="ew", pady=3)
        # Erst beim Loslassen, nie bei jeder Rasterstufe — sonst Dauerneustart.
        scale.bind("<ButtonRelease-1>", lambda _e: self.restart())
        row += 1

        ttk.Separator(f).grid(row=row, column=0, columnspan=2, pady=10, sticky="ew")
        row += 1
        ttk.Label(f, text="Stream", font=("", 13, "bold")).grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1

        self.specs = {}
        for name in ("tx rate", "frame", "QR", "payload", "compression", "K"):
            ttk.Label(f, text=name, foreground="#777").grid(row=row, column=0, sticky="w")
            value = ttk.Label(f, text="—")
            value.grid(row=row, column=1, sticky="e")
            self.specs[name] = value
            row += 1

        f.rowconfigure(row, weight=1)
        row += 1
        self.status = ttk.Label(f, text="", foreground="#555", wraplength=340)
        self.status.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))

    # ------------------------------------------------------------- Aktionen
    def pick_file(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        data = pathlib.Path(path).read_bytes()
        self.payload = p.pack_file(pathlib.Path(path).name, "application/octet-stream", data)
        self.label = f"{pathlib.Path(path).name} · {self.payload.original_size} B"
        self.payload_label.config(text=self.label)
        self.restart()

    def pick_snippet(self):
        self.payload = p.pack_snippet(SNIPPET)
        self.label = f"snippet.txt · {self.payload.original_size} B"
        self.payload_label.config(text=self.label)
        self.restart()

    def restart(self):
        """Jede Aenderung startet den Strom neu — wie der Web-Sender."""
        self.generation += 1
        frame_bytes = int(self.vars["bytes / frame"].get())
        block_len = block_length(frame_bytes)
        codes = dict(GRID_OPTIONS)[self.grid_var.get()]
        session_id = random.randint(1, 0xFFFF)
        encoder = LTEncoder(self.payload.container, block_len, session_id)
        self.stream = {
            "encoder": encoder, "seq": 0, "version": None, "codes": codes,
            "fps": int(self.vars["tx fps"].get()), "ecc": self.vars["error correction"].get(),
            "px": self.size_var.get(), "shown": 0, "t0": time.perf_counter(),
            "header": p.FrameHeader(session_id=session_id, seq=0, k=encoder.k,
                                    block_len=block_len, total_len=len(self.payload.container),
                                    payload_fnv=p.fnv1a(self.payload.container), flags=0),
        }
        self.screen = None
        self.specs["payload"].config(text=self.label)
        self.specs["compression"].config(text=self.payload.compression)
        self.specs["K"].config(text=f"K = {encoder.k}")
        self.status.config(text=f"Streaming {self.label}. Changing any setting restarts the stream.")

    # ------------------------------------------------------------- Ausgabe
    def tick(self):
        s = self.stream
        matrices = []
        for _ in range(s["codes"]):
            frame = p.pack_frame(p.FrameHeader(**{**s["header"].__dict__, "seq": s["seq"]}),
                                 s["encoder"].encode(s["seq"]))
            code = q.create_frame_qr(frame, s["ecc"], s["version"])
            if s["version"] is None:
                s["version"] = code.version
                tiling = f" x{s['codes']}" if s["codes"] > 1 else ""
                self.specs["QR"].config(
                    text=f"V{code.version}{tiling} · ECC {s['ecc']}")
                self.specs["frame"].config(text=f"{s['header'].block_len + 22} B x{s['codes']}")
            matrices.append(list(code.matrix))
            s["seq"] += 1

        cell_scale = max(1, s["px"] // (len(matrices[0]) + 8) // (2 if s["codes"] > 1 else 1))
        w, h, rgb = q.rasterize_qr_grid(matrices, cell_scale)
        if self.screen is None or self.screen.get_size() != (w, h):
            self.screen = pygame.display.set_mode((w, h))
            pygame.display.set_caption("decimen — stream")
        self.screen.blit(pygame.image.frombuffer(rgb, (w, h), "RGB"), (0, 0))
        pygame.display.flip()
        s["shown"] += 1
        elapsed = time.perf_counter() - s["t0"]
        if elapsed > 0.5:
            self.specs["tx rate"].config(
                text=f"{s['shown'] / elapsed:.0f} / {s['fps']} fps x{s['codes']}")

    def run(self):
        deadline = time.perf_counter() + self.seconds if self.seconds else None
        running = True
        while running:
            self.tick()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            try:
                self.root.update()
            except tk.TclError:
                running = False
            if deadline and time.perf_counter() > deadline:
                running = False
            target = self.stream["t0"] + self.stream["shown"] / self.stream["fps"]
            if (wait := target - time.perf_counter()) > 0:
                time.sleep(wait)
        pygame.quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = bis geschlossen")
    Prototype(ap.parse_args().seconds).run()
