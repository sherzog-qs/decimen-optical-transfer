"""Frames produced ahead of time, on every core.

Encoding is 92 % of the per-frame cost (see the map's "Kodieren ueber einen
Prozess-Pool verteilen?"), so the sender hands it to a process pool and keeps
a small buffer of finished rasters ready. Measured on 16 cores: 62 frames/s
single-threaded, 682 with twelve workers.

Two decisions in here came from that measurement rather than from taste:

* **Twelve workers, not sixteen.** Sixteen is measurably *worse* — the four
  efficiency cores drag the group down. A tuned constant with a known ceiling;
  on other hardware it wants re-measuring.
* **Workers return the finished RGB raster, not the module matrix.** The raster
  is 1.6 MB against the matrix's 3.9 KB, and it is still the right way round:
  rasterising in the main process would cost roughly two thirds of a core at
  full rate, next to tkinter and pygame. The big pipe is cheaper than the small
  one here.

Each restart builds a fresh pool — 83 ms, measured — because the workers hold
the container and the stream's settings in their initialiser. Dropping the old
FrameSource drops its futures with it; there is no separate generation counter
because the render loop is single-threaded and a discarded source is
unreachable.
"""

from __future__ import annotations

import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor

from . import protocol as p
from . import qr as q
from .fountain import LTEncoder

# Measured optimum on a 12P/4E machine. See the module docstring.
# ponytail: tuned constant, re-measure on other hardware
MAX_WORKERS = 12
# Prefetched rasters sit in memory. A 6-code grid at 1200 px is 6.5 MB a
# frame, so a fixed frame count would quietly cost 150 MB — budget bytes and
# derive the depth. The cap is what twelve workers can stay ahead of anyway.
MAX_PREFETCH_FRAMES = 24
PREFETCH_BUDGET_BYTES = 48 * 1024 * 1024

_worker = {}


def _init(container: bytes, block_len: int, session_id: int, header: dict,
          ecc: str, version: int, codes: int, scale: int) -> None:
    _worker.update(
        encoder=LTEncoder(container, block_len, session_id),
        header=header, ecc=ecc, version=version, codes=codes, scale=scale,
    )


def _render(index: int):
    """One displayed frame: `codes` consecutive seqs, tiled and rasterised."""
    w = _worker
    matrices = []
    for offset in range(w["codes"]):
        seq = index * w["codes"] + offset
        frame = p.pack_frame(p.FrameHeader(**{**w["header"], "seq": seq}),
                             w["encoder"].encode(seq))
        matrices.append(list(q.create_frame_qr(frame, w["ecc"], w["version"]).matrix))
    return q.rasterize_qr_grid(matrices, w["scale"])


class FrameSource:
    """Finished rasters for one stream, in order, produced ahead of demand.

    The first frame is rendered here in the calling process: the QR version is
    locked by it, and the workers need that version — and the scale derived
    from it — before they can start.
    """

    def __init__(self, container: bytes, block_len: int, session_id: int,
                 header: p.FrameHeader, ecc: str, codes: int, display_px: int):
        self.codes = codes
        header_dict = dict(header.__dict__)

        probe_encoder = LTEncoder(container, block_len, session_id)
        matrices = []
        version = None
        for offset in range(codes):
            frame = p.pack_frame(p.FrameHeader(**{**header_dict, "seq": offset}),
                                 probe_encoder.encode(offset))
            code = q.create_frame_qr(frame, ecc, version)
            version = code.version
            matrices.append(list(code.matrix))

        self.version = version
        self.modules = len(matrices[0])
        cols, _rows = q.grid_dims(codes)
        cell = self.modules + 2 * q.QUIET_ZONE_MODULES
        self.scale = max(1, display_px // (cell * cols))
        self._first = q.rasterize_qr_grid(matrices, self.scale)

        self._pool = ProcessPoolExecutor(
            max_workers=min(MAX_WORKERS, os.cpu_count() or 4),
            initializer=_init,
            initargs=(container, block_len, session_id, header_dict, ecc,
                      version, codes, self.scale),
        )
        self._next_index = 1
        self._pending = deque()
        raster_bytes = max(1, len(self._first[2]))
        depth = max(4, min(MAX_PREFETCH_FRAMES, PREFETCH_BUDGET_BYTES // raster_bytes))
        for _ in range(depth):
            self._submit()

    def _submit(self) -> None:
        self._pending.append(self._pool.submit(_render, self._next_index))
        self._next_index += 1

    def next(self):
        """(width, height, rgb) for the next displayed frame."""
        if self._first is not None:
            first, self._first = self._first, None
            return first
        future = self._pending.popleft()
        self._submit()
        return future.result()

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
