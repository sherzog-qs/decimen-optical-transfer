"""QR generation and rasterisation — send/qr-frame.ts plus shared/qr-raster.ts.

The mask pattern is pinned (any declared mask is valid to a decoder): this
skips the spec's 8-way mask evaluation and speeds generation. It also means
every code carries the same byte length at the same ECC with the same mask, so
once the first code locks the version, every later create_frame_qr lands on
identical geometry — which tiling and grid rasterisation require.

segno and the npm `qrcode` the web sender uses agree on version, geometry and
the decoded bytes for every case in tests/qr-reference-fingerprints.txt. They
do NOT produce identical module matrices when the payload leaves slack in the
symbol: the pad codewords of the unused capacity differ. A decoder reads the
byte-mode character count and stops before them, so this is invisible on the
wire and to a camera.

Deviation from the TypeScript, on purpose: rasterize_qr_grid returns packed RGB
bytes rather than the RGBA-as-u32 buffer ImageData wants. Nothing here feeds an
ImageData; it feeds a native window.
"""

from __future__ import annotations

import math

import segno

QUIET_ZONE_MODULES = 4
PINNED_MASK_PATTERN = 4

_WHITE = b"\xff\xff\xff"
_BLACK = b"\x00\x00\x00"


def create_frame_qr(data: bytes, ecc: str, version: int | None):
    """One frame's wire bytes as a QR symbol.

    Pass `version=None` for the first code of a stream; it locks to that code's
    version, and every later call must pass the locked value.

    boost_error=False is not optional. segno's default raises the error
    correction level whenever the pinned version leaves room — L becomes H on a
    small payload — and the protocol pins L deliberately: in-frame ECC and the
    fountain solve different problems, corruption versus erasure.
    """
    return segno.make(data, mode="byte", error=ecc, version=version,
                      mask=PINNED_MASK_PATTERN, boost_error=False)


def grid_dims(count: int) -> tuple[int, int]:
    """As square as possible, taller before wider.

    The count must fill the rectangle exactly — 1, 2, 4, 6, 9 — a part-empty
    grid would silently waste the channel.
    """
    cols = int(math.isqrt(count))
    rows = -(-count // max(1, cols)) if cols else 0
    if count < 1 or cols * rows != count:
        raise ValueError(
            f"grid needs a count that fills its rows (1, 2, 4, 6, 9...), got {count}"
        )
    return cols, rows


def rasterize_qr_grid(matrices, scale: int = 1) -> tuple[int, int, bytes]:
    """Same-version matrices tiled into a grid, each keeping its quiet zone.

    Returns (width, height, rgb_bytes) with an integer upscale baked in, ready
    for pygame.image.frombuffer. A grid of one is a single code.
    """
    cols, rows = grid_dims(len(matrices))
    modules = len(matrices[0])
    for m in matrices:
        if len(m) != modules:
            raise ValueError("grid cells must all be the same QR version")

    cell = modules + 2 * QUIET_ZONE_MODULES
    width, height = cols * cell * scale, rows * cell * scale
    row_bytes = width * 3
    out = bytearray(_WHITE * (width * height))

    for i, matrix in enumerate(matrices):
        ox = (i % cols) * cell + QUIET_ZONE_MODULES
        oy = (i // cols) * cell + QUIET_ZONE_MODULES
        for y, module_row in enumerate(matrix):
            # Build one module row at native scale, then repeat it `scale` times.
            top = (oy + y) * scale
            line = bytearray()
            for dark in module_row:
                line += (_BLACK if dark else _WHITE) * scale
            start = (ox * scale) * 3
            for dy in range(scale):
                off = (top + dy) * row_bytes + start
                out[off:off + len(line)] = line
    return width, height, bytes(out)
