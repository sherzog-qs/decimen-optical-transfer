"""The receiver window over a FakeRegion — no real screen, no user.

Feeds prepared QR frames through the whole app: engine thread, panel, preview.
The file must arrive SHA-256-verified and the two draw paths must not crash.
select_region and the save dialog need a human, so they are not exercised here;
that is the field check.

    uv run python tests/smoke_window.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys
import time
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def _sender():
    root = HERE.parent.parent / "python-sender" / "decimen"
    pkg = types.ModuleType("snd"); pkg.__path__ = [str(root)]; sys.modules["snd"] = pkg
    out = {}
    for n in ("protocol", "frame_capacity", "fountain", "qr"):
        spec = importlib.util.spec_from_file_location(f"snd.{n}", root / f"{n}.py")
        m = importlib.util.module_from_spec(spec); sys.modules[f"snd.{n}"] = m
        spec.loader.exec_module(m); out[n] = m
    return out


class FakeRegion:
    def __init__(self, frames): self._f = frames; self._i = 0
    def grab(self):
        im = self._f[self._i % len(self._f)]; self._i += 1; return im


def main() -> int:
    import numpy as np
    import pygame
    from decimen.app import ReceiverApp
    from decimen.engine import ReceiverEngine
    from decimen.app import _EMPTY as _EMPTY_SNAP_OBJ

    def _EMPTY_SNAP():
        return _EMPTY_SNAP_OBJ

    snd = _sender()
    original = (b"".join(hashlib.sha256(bytes([i])).digest()
                         for i in range(256)) * 10)[:60 * 1024]
    packed = snd["protocol"].pack_file("shot.bin", "application/octet-stream", original)
    bl = snd["frame_capacity"].block_length(1465)
    enc = snd["fountain"].LTEncoder(packed.container, bl, 4242)
    hdr = dict(session_id=4242, seq=0, k=enc.k, block_len=bl,
               total_len=len(packed.container),
               payload_fnv=snd["protocol"].fnv1a(packed.container), flags=0)
    ver, frames = None, []
    for seq in range(enc.k * 3):
        if (seq * 7919) % 100 < 15:
            continue
        wire = snd["protocol"].pack_frame(
            snd["protocol"].FrameHeader(**{**hdr, "seq": seq}), enc.encode(seq))
        code = snd["qr"].create_frame_qr(wire, "L", ver); ver = code.version
        w, h, rgb = snd["qr"].rasterize_qr_grid([list(code.matrix)], 4)
        frames.append(np.frombuffer(rgb, np.uint8).reshape(h, w, 3))
    print(f"  Sender: k={enc.k}, {len(frames)} Frames")

    # Klickpfad: der "Select region"-Button muss auf einen synthetischen Klick
    # reagieren. Ohne ui.begin() im Loop feuert er nie — genau der Fehler, den
    # der Sender schon einmal hatte.
    probe = ReceiverApp()
    probe._draw_panel(_EMPTY_SNAP())          # zeichnet -> fuellt ui.rects
    rect = probe.ui.rects.get("pick")
    assert rect is not None, "kein 'pick'-Button gezeichnet"
    probe._want_pick = False
    for kind in ("down", "up"):
        ev = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN if kind == "down" else pygame.MOUSEBUTTONUP,
            {"pos": rect.center, "button": 1})
        pygame.event.post(ev)
    evs = pygame.event.get()
    probe.ui.begin(evs)
    probe._draw_panel(_EMPTY_SNAP())          # hit-test unter dem Klick
    assert probe._want_pick, "Klick auf den Button wurde nicht erkannt (ui.begin fehlt?)"
    pygame.quit()
    print("  Klickpfad: 'Select region' reagiert auf einen Klick")

    app = ReceiverApp()
    app.region = FakeRegion(frames)
    app.engine = ReceiverEngine(app.region); app.engine.start()
    drew, t0 = 0, time.perf_counter()
    while time.perf_counter() - t0 < 20:
        snap = app.engine.snapshot()
        app._draw_panel(snap); app._draw_preview(snap)
        app.screen.blit(app.panel, (0, 0)); pygame.display.flip(); drew += 1
        if snap.complete:
            break
        time.sleep(0.02)
    snap = app.engine.snapshot()
    app.engine.stop(); pygame.quit()

    assert snap.complete, "nicht rechtzeitig fertig"
    assert snap.file and snap.file.name == "shot.bin", "Datei/Name falsch"
    assert snap.sha256_ok, "SHA-256 fehlgeschlagen"
    assert snap.file.data == original, "Bytes weichen ab"
    print(f"  Panel+Vorschau {drew}x gezeichnet ohne Absturz")
    print(f"  Empfangen: {snap.file.name}, px/Modul {snap.px_per_module:.1f}, "
          f"Fangrate {snap.catch_rate:.0f}/s, SHA-256 ok")
    print("\nEmpfaenger-Fenster: gezeichnet, Strom empfangen, verifiziert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
