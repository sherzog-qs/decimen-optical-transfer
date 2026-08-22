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
from decimen.engine import STREAM_QUIET_SECONDS, ReceiverEngine

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


def build_matrices(sender, payload, frame_bytes=1465, ecc="L"):
    """The QR matrices of a stream, unrasterised — so a caller can tile codes
    from two different streams into a single image."""
    sp, qr = sender["protocol"], sender["qr"]
    bl = sender["frame_capacity"].block_length(frame_bytes)
    enc = sender["fountain"].LTEncoder(payload, bl, 4242)
    header = dict(session_id=4242, seq=0, k=enc.k, block_len=bl,
                  total_len=len(payload), payload_fnv=sp.fnv1a(payload), flags=0)
    out, version = [], None
    for seq in range(enc.k * 2):
        wire = sp.pack_frame(sp.FrameHeader(**{**header, "seq": seq}), enc.encode(seq))
        code = qr.create_frame_qr(wire, ecc, version)
        version = code.version
        out.append(list(code.matrix))
    return out


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


def _two_files(sender, n=20 * 1024):
    sp = sender["protocol"]
    return (sp.pack_file("a.bin", "application/octet-stream", incompressible(n)),
            sp.pack_file("b.bin", "application/octet-stream", incompressible(n + 1)))


def _await(engine, seconds=25):
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline and not engine.snapshot().complete:
        time.sleep(0.05)
    return engine.snapshot()


def test_stream_restart_hands_over():
    """The sender restarts: the old stream stops, the new one must take over.

    Not instantly — the receiver follows one stream and only lets go once it has
    gone quiet, which is what tells a restart apart from a second sender in the
    region. So the handover costs STREAM_QUIET_SECONDS and must not cost more.
    """
    sender = _sender()
    a, b = _two_files(sender)
    fa, ka = build_frames(sender, a.container, loss_pct=0)
    fb, _ = build_frames(sender, b.container, loss_pct=0)

    # Only half of what A needs, looped: A is unmistakably the incumbent and
    # can never finish, so the test measures the handover and nothing else.
    region = FakeRegion(fa[:ka // 2])
    engine = ReceiverEngine(region)
    engine.start()
    time.sleep(0.5)                      # A is established as the incumbent
    check(not engine.snapshot().complete, "A not yet done when the sender restarts")
    region._frames, region._i = fb, 0    # the sender restarts on file B

    started = time.perf_counter()
    snap = _await(engine)
    took = time.perf_counter() - started
    engine.stop()
    check(snap.complete and snap.file.name == "b.bin",
          f"restarted stream completed ({snap.file.name if snap.file else None})")
    check(snap.sha256_ok, "and verified, so nothing of A leaked into it")
    check(took >= STREAM_QUIET_SECONDS, f"waited out the quiet window ({took:.1f}s)")
    print(f"  Neustart: Uebergabe nach {took:.1f}s, B sauber empfangen")


def test_two_streams_in_one_region():
    """Two senders visible at once — the regression this rule exists for.

    Resetting on every identity change made this case decode NOTHING, silently:
    with both streams in the same grab the identity flips inside one image, so
    the peel restarted on every code. One of them must now come through intact,
    and the window must be told the region is ambiguous.
    """
    sender = _sender()
    qr = sender["qr"]
    a, b = _two_files(sender, 12 * 1024)
    fa = build_matrices(sender, a.container)
    fb = build_matrices(sender, b.container)

    # Both codes in ONE image, the way two sender windows in one region look.
    frames = []
    for i in range(max(len(fa), len(fb))):
        pair = [fa[i % len(fa)], fb[i % len(fb)]]
        w, h, rgb = qr.rasterize_qr_grid(pair, 4)
        frames.append(np.frombuffer(rgb, np.uint8).reshape(h, w, 3))

    engine = ReceiverEngine(FakeRegion(frames))
    engine.start()
    snap = _await(engine)
    engine.stop()
    check(snap.complete, "one of the two streams completed instead of neither")
    check(snap.sha256_ok, "and verified — the other stream never entered the peel")
    check(snap.file.name in ("a.bin", "b.bin"), f"a whole file ({snap.file})")
    check(snap.grid_codes == 1,
          f"codes counts the followed stream, not the picture (got {snap.grid_codes})")
    check(snap.ambiguous, "the region is reported as ambiguous")
    print(f"  Doppelstrom: {snap.file.name} sauber, Bereich als mehrdeutig gemeldet")


if __name__ == "__main__":
    for name, fn in sorted((k, v) for k, v in globals().items()
                           if k.startswith("test_") and callable(v)):
        fn()
        print(f"  {name} ok")
    print(f"\n{checks} checks passed")
