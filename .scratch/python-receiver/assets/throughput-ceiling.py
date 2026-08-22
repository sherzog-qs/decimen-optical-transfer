"""Where the 120 kB/s ceiling actually sits.

Times the receiver's own decode call (zxingcpp.read_barcodes over the grabbed
RGB array) on frames rendered exactly as the sender renders them, scaled to a
1200 px capture — the sender's maximum display size. Payload rate is
codes x block_len x decodes/s; the transfer can never beat that, and the
display refresh caps it again on top.

    uv run python .scratch/python-receiver/assets/throughput-ceiling.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import time
import types

import numpy as np
import pygame
import zxingcpp

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python-receiver"))
from decimen import protocol as p            # noqa: E402

CAPTURE_PX = 1200          # the sender's DISPLAY_SIZE_MAX


def _sender():
    root = ROOT / "python-sender" / "decimen"
    pkg = types.ModuleType("snd"); pkg.__path__ = [str(root)]; sys.modules["snd"] = pkg
    out = {}
    for n in ("protocol", "frame_capacity", "fountain", "qr"):
        spec = importlib.util.spec_from_file_location(f"snd.{n}", root / f"{n}.py")
        m = importlib.util.module_from_spec(spec); sys.modules[f"snd.{n}"] = m
        spec.loader.exec_module(m); out[n] = m
    return out


def render(snd, frame_bytes: int, codes: int):
    """One screen frame the way the sender draws it, scaled to CAPTURE_PX."""
    sp, qr = snd["protocol"], snd["qr"]
    bl = snd["frame_capacity"].block_length(frame_bytes)
    payload = bytes(range(256)) * (bl * 4 // 256 + 1)
    enc = snd["fountain"].LTEncoder(payload, bl, 4242)
    mats, version = [], None
    for seq in range(codes):
        h = sp.FrameHeader(session_id=4242, seq=seq, k=enc.k, block_len=bl,
                           total_len=len(payload), payload_fnv=sp.fnv1a(payload), flags=0)
        code = qr.create_frame_qr(sp.pack_frame(h, enc.encode(seq)), "L", version)
        version = code.version
        mats.append(list(code.matrix))
    # Exactly what pool.py does: an integer module scale that fits the display
    # width, then blitted 1:1 — no resampling anywhere. px/module IS the scale,
    # and the window grows to whatever height the grid needs.
    cols, rows = qr.grid_dims(codes)
    modules = len(mats[0])
    cell = modules + 2 * qr.QUIET_ZONE_MODULES
    scale = max(1, CAPTURE_PX // (cell * cols))
    w, hgt, rgb = qr.rasterize_qr_grid(mats, scale)
    return np.frombuffer(rgb, np.uint8).reshape(hgt, w, 3), bl, (w, hgt), scale


def bench(frame: np.ndarray, expect: int, seconds: float = 1.5) -> float:
    zxingcpp.read_barcodes(np.ascontiguousarray(frame),
                           formats=zxingcpp.BarcodeFormat.QRCode)   # warm up
    n, t0 = 0, time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        got = zxingcpp.read_barcodes(np.ascontiguousarray(frame),
                                     formats=zxingcpp.BarcodeFormat.QRCode)
        assert len(got) == expect, f"read {len(got)} of {expect} codes"
        n += 1
    return n / (time.perf_counter() - t0)


if __name__ == "__main__":
    snd = _sender()
    print(f"capture {CAPTURE_PX} px, header {p.HEADER_LEN} B\n")
    print(f"{'bytes':>6} {'codes':>6} {'px/mod':>7} {'window':>11} "
          f"{'decodes/s':>10} {'kB/s@60':>8}")
    for frame_bytes in (1000, 1850, 2953):
        for codes in (1, 2, 4, 6):
            frame, bl, (w, h), px = render(snd, frame_bytes, codes)
            try:
                rate = bench(frame, codes)
                # 60 fps is the sender's ceiling, so the wire rate the screen
                # can actually carry is codes x block x min(60, decodes/s).
                out = f"{rate:>10.0f} {codes * bl * min(60, rate) / 1000:>8.0f}"
            except AssertionError as exc:
                out = f"{'—':>10} {str(exc)[:8]:>8}"
            print(f"{frame_bytes:>6} {codes:>6} {px:>7} {f'{w}x{h}':>11} {out}")
