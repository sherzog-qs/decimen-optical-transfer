"""Was bringt ein Prozess-Pool beim Kodieren — und was kostet der Rueckweg?

Zwei Varianten, weil die IPC-Groesse alles entscheidet:
  A) der Arbeiter gibt die gepackte Modulmatrix zurueck (~3.9 KB/Frame)
  B) der Arbeiter gibt das fertige RGB-Raster zurueck (~1.6 MB/Frame)

Ausserdem: was kostet das Aufsetzen des Pools, denn jede Reglerdrehung
startet den Strom neu.
"""
from __future__ import annotations

import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "python-sender"))

from decimen import protocol as p
from decimen import qr as q
from decimen.fountain import LTEncoder
from decimen.frame_capacity import block_length

FRAME_BYTES = 2953
ECC = "L"
PX = 740

_state = {}


def _init(container: bytes, block_len: int, session_id: int, header: dict):
    _state["enc"] = LTEncoder(container, block_len, session_id)
    _state["header"] = header


def _matrix_job(seq: int) -> bytes:
    enc = _state["enc"]
    frame = p.pack_frame(p.FrameHeader(**{**_state["header"], "seq": seq}), enc.encode(seq))
    code = q.create_frame_qr(frame, ECC, 40)
    bits = [1 if m else 0 for row in code.matrix for m in row]
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for j, bit in enumerate(bits[i:i + 8]):
            v |= bit << (7 - j)
        out.append(v)
    return bytes(out)


def _raster_job(seq: int) -> bytes:
    enc = _state["enc"]
    frame = p.pack_frame(p.FrameHeader(**{**_state["header"], "seq": seq}), enc.encode(seq))
    code = q.create_frame_qr(frame, ECC, 40)
    scale = max(1, PX // (len(code.matrix) + 8))
    return q.rasterize_qr_grid([list(code.matrix)], scale)[2]


def main():
    block_len = block_length(FRAME_BYTES)
    payload = bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(400 * 1024))
    packed = p.pack_file("bench.bin", "application/octet-stream", payload)
    container = packed.container
    enc = LTEncoder(container, block_len, 4242)
    header = dict(session_id=4242, seq=0, k=enc.k, block_len=block_len,
                  total_len=len(container), payload_fnv=p.fnv1a(container), flags=0)
    print(f"Container {len(container)} B, k={enc.k}, blockLen={block_len}, QR v40\n")

    # Einzelthreadig als Bezugsgroesse.
    t0 = time.perf_counter(); n = 0
    while time.perf_counter() - t0 < 4.0:
        _state["enc"], _state["header"] = enc, header
        _matrix_job(n); n += 1
    base = n / (time.perf_counter() - t0)
    goodput = base * (block_len) / 1024 / 1.15
    print(f"  einthreadig          {base:6.1f} Frames/s  -> {goodput:6.1f} KB/s\n")

    for label, job in (("Matrix zurueck (3.9 KB)", _matrix_job),
                       ("Raster zurueck (1.6 MB)", _raster_job)):
        print(f"  {label}")
        for workers in (4, 8, 12, 16):
            t_start = time.perf_counter()
            with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                     initargs=(container, block_len, 4242, header)) as pool:
                list(pool.map(job, range(workers), chunksize=1))   # Pool warmlaufen
                startup = time.perf_counter() - t_start
                t0 = time.perf_counter()
                count = workers * 24
                list(pool.map(job, range(count), chunksize=2))
                dt = time.perf_counter() - t0
            rate = count / dt
            print(f"    {workers:2d} Arbeiter  {rate:6.1f} Frames/s  "
                  f"({rate / base:4.1f}x)  -> {rate * block_len / 1024 / 1.15:6.1f} KB/s"
                  f"   Aufsetzen {startup * 1000:5.0f} ms")
        print()


if __name__ == "__main__":
    main()
