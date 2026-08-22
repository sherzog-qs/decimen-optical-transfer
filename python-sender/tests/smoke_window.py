"""Rauchtest fuer das Sender-Fenster, inklusive der Klickpfade.

Die Klicks sind synthetisch: `pygame.event.post` legt sie in dieselbe
Warteschlange, aus der die Schleife liest. Das beweist nicht, dass das
Betriebssystem echte Klicks liefert — aber es beweist, dass die Verdrahtung
von Trefferflaeche zu Aktion stimmt, und genau die war beim tkinter-Panel
nicht pruefbar.

Muss eine Datei sein, kein stdin: die Arbeiter des Prozess-Pools importieren
das __main__-Modul des Elternprozesses neu.

    uv run python tests/smoke_window.py
"""
from __future__ import annotations

import hashlib
import multiprocessing
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def click(pygame, app, key: str) -> None:
    """Auf die Trefferflaeche eines Bedienelements klicken und eine Runde drehen."""
    rect = app.ui.rects.get(key)
    assert rect is not None, f"kein Bedienelement namens {key!r} gezeichnet"
    for kind in ("down", "up"):
        app_event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN if kind == "down" else pygame.MOUSEBUTTONUP,
            {"pos": rect.center, "button": 1})
        pygame.event.post(app_event)
    app._tick()


def incompressible(n: int) -> bytes:
    out, seed = bytearray(), b"smoke"
    while len(out) < n:
        seed = hashlib.sha256(seed).digest()
        out += seed
    return bytes(out[:n])


def main() -> int:
    import pygame

    from decimen import protocol as p
    from decimen.app import SenderApp

    app = SenderApp()
    try:
        return drive(pygame, p, app)
    finally:
        app._shutdown()


def drive(pygame, p, app) -> int:
    app._tick()                              # zeichnet das Panel, fuellt rects
    assert "fps:24" in app.ui.rects, sorted(app.ui.rects)
    print(f"  Panel           {len(app.ui.rects)} Bedienelemente gezeichnet")

    click(pygame, app, "fps:24")
    assert app.settings["fps"] == 24, app.settings
    click(pygame, app, "ecc:M")
    assert app.settings["ecc"] == "M", app.settings
    print(f"  Klickpfad       fps -> {app.settings['fps']}, "
          f"ECC -> {app.settings['ecc']} (ohne Nutzlast kein Neustart)")
    assert app.source is None, "ohne Nutzlast darf kein Strom laufen"

    app.settings.update(fps=60, ecc="L")
    app.packed = p.pack_snippet("smoke test payload for the sender window")
    app.payload_label = "snippet.txt"
    t0 = time.perf_counter()
    app.restart()
    print(f"  Start           {(time.perf_counter() - t0) * 1000:5.0f} ms  "
          f"QR v{app.source.version}  K = {app.specs['k']}")

    t0 = time.perf_counter()
    for _ in range(60):
        app._next_frame()
    dt = time.perf_counter() - t0
    assert app.source is not None, "Pool ist mitten im Zeichnen gestorben"
    print(f"  60 Frames       {dt * 1000:5.0f} ms  ({60 / dt:5.1f} fps ungebremst)  "
          f"Bild {app.frame_rgb[0]}x{app.frame_rgb[1]}")

    t0 = time.perf_counter()
    click(pygame, app, "codes:4")
    assert app.settings["codes"] == 4 and app.source is not None
    print(f"  Klick auf 4er   {(time.perf_counter() - t0) * 1000:5.0f} ms  "
          f"QR v{app.source.version}  frame {app.specs['frame']}")
    for _ in range(20):
        app._next_frame()
    assert app.source is not None, "Pool nach Reglerwechsel gestorben"
    print(f"  4er-Grid        Bild {app.frame_rgb[0]}x{app.frame_rgb[1]}  "
          f"Fenster {app.screen.get_size()}")

    app.packed = p.pack_file("big.bin", "application/octet-stream",
                             incompressible(40 * 1024 * 1024))
    app.payload_label = "big.bin"
    app.settings["bytes"] = 500
    app.restart()
    assert app.source is None and app.status_error, app.status
    print(f"  Kapazitaet      abgefangen: {app.status[:58]}...")

    print("\nSender-Fenster: gezeichnet, geklickt, gestreamt, umgestellt, beendet.")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
