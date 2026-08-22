"""What a big file costs the receiver, measured.

The decode half only — LTDecoder, assemble, unpack_file, verify_file. The
capture side is per-frame constant and irrelevant to the question; what the
ticket asks is how many copies of the file live at once, and where the curve
bends. Rendering QR codes for a 64 MB payload would take hours and measure the
sender.

    uv run python .scratch/python-receiver/assets/large-file-memory.py
"""
from __future__ import annotations

import gc
import hashlib
import pathlib
import resource
import sys
import time
import tracemalloc

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python-receiver"))

from decimen import protocol as p                      # noqa: E402
from decimen.frame_capacity import block_length, source_block_count  # noqa: E402
from decimen.fountain import LTDecoder                 # noqa: E402

FRAME_BYTES = 2953
LOSS_PCT = 15                  # the sender's default, so k stays as low as it gets
MB = 1 << 20


def incompressible(n: int) -> bytes:
    out, seed = bytearray(), b"large"
    while len(out) < n:
        seed = hashlib.sha256(seed).digest()
        out += seed
    return bytes(out[:n])


def container_for(size: int) -> bytes:
    """Pack a file the way the sender does — the receiver's own unpack is the
    thing under test, so the container has to be real."""
    return _sender_mod("protocol").pack_file(
        "big.bin", "application/octet-stream", incompressible(size)).container


def _sender_mod(name: str):
    import importlib.util
    import types
    root = ROOT / "python-sender" / "decimen"
    if "snd" not in sys.modules:
        pkg = types.ModuleType("snd"); pkg.__path__ = [str(root)]; sys.modules["snd"] = pkg
    if f"snd.{name}" not in sys.modules:
        spec = importlib.util.spec_from_file_location(f"snd.{name}", root / f"{name}.py")
        m = importlib.util.module_from_spec(spec); sys.modules[f"snd.{name}"] = m
        spec.loader.exec_module(m)
    return sys.modules[f"snd.{name}"]


def run(size: int, fountain: bool = False) -> None:
    bl = block_length(FRAME_BYTES)
    container = container_for(size)
    k = source_block_count(len(container), FRAME_BYTES)
    blocks = [container[i * bl:(i + 1) * bl].ljust(bl, b"\0") for i in range(k)]

    gc.collect()
    decode_s = worst = 0.0
    tracemalloc.start()
    t0 = time.perf_counter()
    d = LTDecoder(k, bl, 4242, len(container))
    if fountain:
        # What actually arrives: the sender's own carousel with frames dropped,
        # so degree>1 frames pile up in _by_block waiting to be peeled. This is
        # the case the ticket is about — the cheap systematic path never holds
        # a pending frame at all.
        enc = _sender_mod("fountain").LTEncoder(container, bl, 4242)
        seq = 0
        while not d.is_complete and seq < k * 6:
            if (seq * 7919) % 100 >= LOSS_PCT:
                block = enc.encode(seq)     # the SENDER's work, not the receiver's
                t = time.perf_counter()
                d.add_frame(seq, block)
                dt = time.perf_counter() - t
                decode_s += dt
                # The worst SINGLE frame matters more than the total: capture,
                # decode and peel share one thread, so a long peeling cascade is
                # a stall in the grab loop, not just CPU spent.
                worst = max(worst, dt)
            seq += 1
    else:
        t = time.perf_counter()
        for seq in range(k):
            d.add_frame(seq, blocks[seq])
        decode_s = time.perf_counter() - t
    solved_peak = tracemalloc.get_traced_memory()[1]
    assembled = d.assemble()
    file = p.unpack_file(assembled)
    ok = p.verify_file(file)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / MB
    took = time.perf_counter() - t0

    tag = "fountain" if fountain else "  direct"
    print(f"{tag} {size // MB:>4} MB  k={k:>6}  peel {solved_peak / MB:>7.1f} MB  "
          f"peak {peak / MB:>7.1f} MB  ({peak / size:>4.1f}x)  "
          f"rss {rss:>6.1f} MB  peel {decode_s:>6.1f}s of {took:>6.1f}s  "
          f"worst frame {worst * 1000:>7.1f}ms  "
          f"sha {'ok' if ok else 'FAIL'}")
    del d, blocks, container, assembled, file
    gc.collect()


if __name__ == "__main__":
    bl = block_length(FRAME_BYTES)
    print(f"frame {FRAME_BYTES} B, block {bl} B, u16 block ceiling "
          f"{65535 * bl / MB:.0f} MB\n")
    print(f"{'mode':>8} {'size':>7}  {'k':>8}  {'peel':>12}  {'peak':>12}         "
          f"{'rss':>10}  {'time':>6}")
    sizes = [int(a) for a in sys.argv[1:]] or [1, 8, 64]
    for mb in sizes:
        run(mb * MB)
    print()
    for mb in sizes:
        run(mb * MB, fountain=True)
