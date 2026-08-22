"""The capture-and-decode engine — one background thread, per the architecture
in the map's "Decode-Architektur".

Grabs the region as fast as decode allows, finds every QR in each frame (grids
need no counting — zxing returns them all), parses, checks stream identity
BEFORE feeding the decoder (a frame from another stream would corrupt the peel
silently), and rebuilds the file. The pygame loop only reads `snapshot()`.

No process pool: 129 decodes/s single-threaded is past any real Citrix rate
(measured). An image-hash prefilter is optional, default off — it only helps
pixel-exact, where every capture is identical; over Citrix compression noise
defeats an exact hash.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import zxingcpp

from . import protocol as p
from . import send_settings_hint as hint
from .fountain import LTDecoder


@dataclass
class Snapshot:
    """A consistent read of engine state for the UI. Copied under the lock so
    the display never sees a half-updated decoder."""
    frames_collected: int = 0
    frames_needed: int = 0          # ~k * 1.15, the completion target
    k: int = 0
    block_len: int = 0
    grid_codes: int = 0
    px_per_module: float = 0.0
    catch_rate: float = 0.0         # useful new frames per second
    compression: str = "—"
    ecc: str = "L"                  # as zxing read it off the code itself
    complete: bool = False
    verdict_message: str | None = None
    last_frame: np.ndarray | None = None   # the raw region, for the preview
    file: "p.OpticalFile | None" = None
    sha256_ok: bool = False


class ReceiverEngine:
    def __init__(self, region, prefilter: bool = False):
        self._region = region
        self._prefilter = prefilter
        self._lock = threading.Lock()
        self._snap = Snapshot()
        self._decoder: LTDecoder | None = None
        self._identity: str | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._catch_window: list[float] = []
        self._last_hash: bytes | None = None

    def set_region(self, region) -> None:
        """Re-drag mid-transfer: the decoder keeps going, only the source moves."""
        with self._lock:
            self._region = region

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def snapshot(self) -> Snapshot:
        with self._lock:
            s = self._snap
            # shallow copy is enough — fields are scalars plus two references
            return Snapshot(**s.__dict__)

    # ------------------------------------------------------------- the loop

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                region = self._region
            frame = region.grab()
            if frame is None:                     # permission lost / black
                time.sleep(0.05)
                continue

            if self._prefilter:
                h = hashlib.blake2b(frame[::8, ::8, 0].tobytes(), digest_size=8).digest()
                if h == self._last_hash:
                    self._store_preview(frame)
                    continue
                self._last_hash = h

            self._process(frame)
            self._store_preview(frame)

    def _process(self, frame: np.ndarray) -> None:
        results = zxingcpp.read_barcodes(
            np.ascontiguousarray(frame), formats=zxingcpp.BarcodeFormat.QRCode)
        now = time.perf_counter()
        useful = 0
        codes_seen = 0
        px_per_module = 0.0
        ecc = ""
        for r in results:
            codes_seen += 1
            wire = bytes(r.bytes)
            parsed = p.parse_frame(wire)
            if parsed is None:
                verdict = p.classify_frame(wire)
                msg = p.frame_verdict_message(verdict)
                if msg:
                    with self._lock:
                        self._snap.verdict_message = msg
                continue
            header, block = parsed
            useful += self._accept(header, block)
            px_per_module = max(px_per_module, self._px_per_module(r, len(results)))
            ecc = r.ec_level or ecc

        # Catch rate over a 1s window of USEFUL frames (new, non-redundant).
        for _ in range(useful):
            self._catch_window.append(now)
        while self._catch_window and now - self._catch_window[0] > 1.0:
            self._catch_window.pop(0)

        with self._lock:
            d = self._decoder
            if d is not None:
                self._snap.frames_collected = d.frames_new - d.frames_redundant
                self._snap.frames_needed = max(1, round(d.k * 1.15))
                self._snap.k = d.k
                self._snap.block_len = d.block_len
                self._snap.catch_rate = float(len(self._catch_window))
                self._snap.grid_codes = codes_seen or self._snap.grid_codes
                if px_per_module:
                    self._snap.px_per_module = px_per_module
                if ecc:
                    self._snap.ecc = ecc
                if d.is_complete and not self._snap.complete:
                    self._finish(d)

    def _accept(self, header: "p.FrameHeader", block: bytes) -> int:
        """Feed one frame, resetting the decoder on a stream change. Returns 1
        if it was a useful new frame, else 0."""
        identity = p.stream_identity(header)
        with self._lock:
            if identity != self._identity:
                self._identity = identity
                self._decoder = LTDecoder(header.k, header.block_len,
                                          header.session_id, header.total_len)
                self._snap.complete = False
                self._snap.file = None
                self._snap.verdict_message = None
            d = self._decoder
            before_new = d.frames_new
            before_redundant = d.frames_redundant
            d.add_frame(header.seq, block)
            return int(d.frames_new > before_new
                       and d.frames_redundant == before_redundant)

    def _finish(self, d: LTDecoder) -> None:
        """Called under the lock when the decoder completes."""
        container = d.assemble()
        self._snap.complete = True
        try:
            file = p.unpack_file(container)
        except p.OpticalError as exc:
            self._snap.verdict_message = f"Container error: {exc.code}"
            return
        self._snap.file = file
        self._snap.compression = file.compression
        self._snap.sha256_ok = p.verify_file(file)
        if not self._snap.sha256_ok:
            self._snap.verdict_message = "Checksum failed — the file is not offered."

    @staticmethod
    def _px_per_module(result, code_count: int) -> float:
        """Pixels per QR module — the robustness number from Ticket
        'Citrix-Robustheit'. Bounding-box width over the module count, where the
        module count follows from the QR version, and the version follows from
        the wire byte length the code carries (blockLen + header). Only feeds
        the recommendation, which needs the trend, not an exact value.
        """
        pos = result.position
        xs = (pos.top_left.x, pos.top_right.x, pos.bottom_left.x, pos.bottom_right.x)
        width_px = max(xs) - min(xs)
        return width_px / hint.modules_for(len(bytes(result.bytes)),
                                           result.ec_level or "L")

    def _store_preview(self, frame: np.ndarray) -> None:
        with self._lock:
            self._snap.last_frame = frame
