"""The capture-and-decode engine, without a real screen.

A FakeRegion hands the engine prepared QR frames (rendered by python-sender),
so the whole thread architecture — grab, find, parse, stream-identity, peel — is
exercised end to end and the file must fall out SHA-256-verified.

    uv run python tests/test_engine.py
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

import numpy as np
from decimen import protocol as p
from decimen.engine import ReceiverEngine

checks = 0


def check(cond, label):
    global checks
    assert cond, f"FAILED: {label}"
    checks += 1


def _sender():
    root = HERE.parent.parent / "python-sender" / "decimen"
    pkg = types.ModuleType("snd"); pkg.__path__ = [str(root)]
    sys.modules["snd"] = pkg
    out = {}
    for n in ("protocol", "frame_capacity", "fountain", "qr"):
        spec = importlib.util.spec_from_file_location(f"snd.{n}", root / f"{n}.py")
        m = importlib.util.module_from_spec(spec); sys.modules[f"snd.{n}"] = m
        spec.loader.exec_module(m); out[n] = m
    return out


class FakeRegion:
    """Hands out one prepared RGB frame per grab, looping, so the engine's own
    seq-dedup and 15%-loss handling get exercised."""
    def __init__(self, frames):
        self._frames = frames
        self._i = 0

    def grab(self):
        if not self._frames:
            return None
        f = self._frames[self._i % len(self._frames)]
        self._i += 1
        return f


def build_frames(sender, payload, frame_bytes=1465, ecc="L", loss_pct=15):
    sp, qr = sender["protocol"], sender["qr"]
    bl = sender["frame_capacity"].block_length(frame_bytes)
    enc = sender["fountain"].LTEncoder(payload, bl, 4242)
    header = dict(session_id=4242, seq=0, k=enc.k, block_len=bl,
                  total_len=len(payload), payload_fnv=sp.fnv1a(payload), flags=0)
    version = None
    imgs = []
    for seq in range(enc.k * 3):
        if (seq * 7919) % 100 < loss_pct:
            continue
        wire = sp.pack_frame(sp.FrameHeader(**{**header, "seq": seq}), enc.encode(seq))
        code = qr.create_frame_qr(wire, ecc, version)
        version = code.version
        w, h, rgb = qr.rasterize_qr_grid([list(code.matrix)], 4)
        imgs.append(np.frombuffer(rgb, np.uint8).reshape(h, w, 3))
    return imgs, enc.k


def incompressible(n):
    out, seed = bytearray(), b"engine"
    while len(out) < n:
        seed = hashlib.sha256(seed).digest(); out += seed
    return bytes(out[:n])


def test_receives_a_file():
    sender = _sender()
    original = incompressible(80 * 1024)
    packed = sender["protocol"].pack_file("photo.bin", "application/octet-stream", original)
    frames, k = build_frames(sender, packed.container)
    print(f"  Sender: k={k}, {len(frames)} Frames (nach 15% Verlust)")

    engine = ReceiverEngine(FakeRegion(frames))
    engine.start()
    deadline = time.perf_counter() + 20
    while time.perf_counter() < deadline:
        if engine.snapshot().complete:
            break
        time.sleep(0.05)
    snap = engine.snapshot()
    engine.stop()

    check(snap.complete, "transfer completed")
    check(snap.file is not None, "file unpacked")
    check(snap.file.name == "photo.bin", "name survived")
    check(snap.sha256_ok, "sha256 verified")
    check(snap.file.data == original, "every byte recovered")
    check(snap.px_per_module > 3, f"px/module measured ({snap.px_per_module:.1f})")
    check(snap.k == k, "k reported")
    print(f"  Empfangen: {snap.frames_collected} Frames gesammelt, "
          f"px/Modul {snap.px_per_module:.1f}, SHA-256 ok")


def test_stream_restart_resets():
    """A new session id (sender restarted) must reset the decoder, not mix."""
    sender = _sender()
    a = sender["protocol"].pack_file("a.bin", "application/octet-stream", incompressible(20*1024))
    b = sender["protocol"].pack_file("b.bin", "application/octet-stream", incompressible(20*1024))
    fa, _ = build_frames(sender, a.container, loss_pct=0)
    fb, _ = build_frames(sender, b.container, loss_pct=0)
    # Feed a few of A, then all of B. The engine must finish B cleanly.
    engine = ReceiverEngine(FakeRegion(fa[:5] + fb))
    engine.start()
    deadline = time.perf_counter() + 20
    while time.perf_counter() < deadline and not engine.snapshot().complete:
        time.sleep(0.05)
    snap = engine.snapshot()
    engine.stop()
    check(snap.complete and snap.file.name == "b.bin",
          f"second stream completed cleanly (got {snap.file.name if snap.file else None})")
    print("  Stream-Neustart: Decoder auf den zweiten Strom zurueckgesetzt")


if __name__ == "__main__":
    for name, fn in sorted((k, v) for k, v in globals().items()
                           if k.startswith("test_") and callable(v)):
        fn()
        print(f"  {name} ok")
    print(f"\n{checks} checks passed")
