"""Rauchtest fuer das Sender-Fenster: baut es, streamt, dreht Regler.

Muss eine Datei sein, kein stdin: die Arbeiter des Prozess-Pools importieren
das __main__-Modul des Elternprozesses neu, und ein Skript ohne Pfad koennen
sie nicht finden.

    uv run python tests/smoke_window.py
"""
from __future__ import annotations

import multiprocessing
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def main() -> int:
    from decimen import protocol as p
    from decimen.app import SenderApp

    app = SenderApp()
    try:
        return _drive(app)
    finally:
        app._shutdown()


def _drive(app) -> int:
    from decimen import protocol as p
    app.packed = p.pack_snippet("smoke test payload for the sender window")
    app.payload_label = "snippet.txt"
    app.payload_line.config(text=app.payload_label)

    t0 = time.perf_counter()
    app.restart()
    print(f"  Start           {(time.perf_counter() - t0) * 1000:5.0f} ms  "
          f"QR v{app.source.version}  Skalierung {app.source.scale}  "
          f"{app.specs['k'].cget('text')}")

    t0 = time.perf_counter()
    for _ in range(60):
        app._draw()
        app.root.update()
    dt = time.perf_counter() - t0
    assert app.source is not None, "Pool ist mitten im Zeichnen gestorben"
    print(f"  60 Frames       {dt * 1000:5.0f} ms  ({60 / dt:5.1f} fps ungebremst)  "
          f"Fenster {app.screen.get_size()}")

    app.grid_var.set("4 codes (2x2)")
    app.controls["bytes"].set("1465")
    t0 = time.perf_counter()
    app.restart()
    print(f"  Reglerwechsel   {(time.perf_counter() - t0) * 1000:5.0f} ms  "
          f"QR v{app.source.version}  {app.specs['k'].cget('text')}  "
          f"frame {app.specs['frame'].cget('text')}")
    for _ in range(30):
        app._draw()
        app.root.update()
    assert app.source is not None, "Pool nach Reglerwechsel gestorben"
    print(f"  4er-Grid        Fenster {app.screen.get_size()}  "
          f"tx rate '{app.specs['rate'].cget('text')}'")

    # Kapazitaetsfehler: winzige Frames fuer eine grosse Nutzlast. Die Daten
    # muessen inkompressibel sein — 40 MB Nullen schrumpfen auf nichts und
    # passen dann sehr wohl.
    import hashlib
    blob, seed = bytearray(), b"capacity"
    while len(blob) < 40 * 1024 * 1024:
        seed = hashlib.sha256(seed).digest()
        blob += seed
    app.packed = p.pack_file("big.bin", "application/octet-stream", bytes(blob))
    app.controls["bytes"].set("500")
    app.restart()
    status = app.status.cget("text")
    assert "bytes / frame" in status and app.source is None, status
    print(f"  Kapazitaet      abgefangen: {status[:64]}...")

    app.quit()
    print("\nSender-Fenster: sauber gestartet, gestreamt, umgestellt und beendet.")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
