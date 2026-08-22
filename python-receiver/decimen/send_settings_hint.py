"""Turn a measured px/module into a concrete sender recommendation.

Two directions, one number. Robustness tracks px/module, target >=6 (the
Citrix-Robustheit ticket), and the receiver is the only side that can see it.

  recommend()  reception is bad     -> spend module size to get back over 6
  headroom()   reception is healthy -> spend the margin above 6 on throughput

Never Citrix settings; the user has little say over those.

The geometry mirrors the sender (python-sender/decimen/pool.py): it picks an
integer module scale that fits the display width and blits 1:1, so px/module IS
that scale, and the window grows to whatever height the grid needs. The
consequence drives the whole upward ladder: a grid adds ROWS before COLUMNS, so
1->2 codes doubles the payload at unchanged module size and only costs window
height, while 2->4 adds a column and halves it.
"""

from __future__ import annotations

import math

from .frame_capacity import block_length
from .protocol import HEADER_LEN

TARGET_PX = 6.0
# Going up aims higher than the rescue threshold on purpose. 6 is where the
# Citrix-Robustheit ticket saw codes still survive, measured against an H.264
# stand-in and flagged as needing real HDX to confirm — so advice that lands
# exactly on it bets the transfer on an unconfirmed edge. Recommendations keep
# a margin; the rescue line still uses the bare threshold.
UPGRADE_PX = 8.0
QUIET_ZONE_MODULES = 4              # mirrors qr.QUIET_ZONE_MODULES
FRAME_BYTES_OPTIONS = (500, 1000, 1850, 2331, 2953)
GRID_OPTIONS = (1, 2, 4, 6)

# Byte-mode capacity for versions 1..40 at each error-correction level, in
# bytes. Generated against segno (assets/qr-capacity.py), not quoted from
# memory — px/module is the number this whole file turns on, and it follows
# from the version, which follows from these.
CAPACITY = {
    "L": (17, 32, 53, 78, 106, 134, 154, 192, 230, 271, 321, 367, 425, 458, 520, 586, 644, 718, 792, 858, 929, 1003, 1091, 1171, 1273, 1367, 1465, 1528, 1628, 1732, 1840, 1952, 2068, 2188, 2303, 2431, 2563, 2699, 2809, 2953),
    "M": (14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362, 412, 450, 504, 560, 624, 666, 711, 779, 857, 911, 997, 1059, 1125, 1190, 1264, 1370, 1452, 1538, 1628, 1722, 1809, 1911, 1989, 2099, 2213, 2331),
    "Q": (11, 20, 32, 46, 60, 74, 86, 108, 130, 151, 177, 203, 241, 258, 292, 322, 364, 394, 442, 482, 509, 565, 611, 661, 715, 751, 805, 868, 908, 982, 1030, 1112, 1168, 1228, 1283, 1351, 1423, 1499, 1579, 1663),
    "H": (7, 14, 24, 34, 44, 58, 64, 84, 98, 119, 137, 155, 177, 194, 220, 250, 280, 310, 338, 382, 403, 439, 461, 511, 535, 593, 625, 658, 698, 742, 790, 842, 898, 958, 983, 1051, 1093, 1139, 1219, 1273),
}


def modules_for(wire_bytes: int, ecc: str = "L") -> int:
    """Module count of the smallest QR version that holds this many bytes.

    The level comes from the code itself — zxing reports it — because the same
    payload at H needs a far bigger symbol than at L, and guessing L would
    overstate px/module by more than the threshold it is compared against.
    """
    caps = CAPACITY.get(ecc, CAPACITY["L"])
    for version, cap in enumerate(caps, start=1):
        if cap >= wire_bytes:
            return 4 * version + 17
    return 4 * 40 + 17


def grid_dims(codes: int) -> tuple[int, int]:
    """Mirrors qr.grid_dims — as square as possible, taller before wider."""
    cols = max(1, math.isqrt(codes))
    return cols, -(-codes // cols)


def _cell(frame_bytes: int, ecc: str) -> int:
    return modules_for(frame_bytes, ecc) + 2 * QUIET_ZONE_MODULES


def recommend(px_per_module: float, grid_codes: int) -> str:
    if px_per_module <= 0:
        return "Nothing decoding. Point the region at the QR stream, or drag it tighter."

    parts = [f"Low catch at {px_per_module:.1f} px/module (aim for {TARGET_PX:.0f}+)."]
    if grid_codes and grid_codes > 1:
        parts.append(f"On the sender, drop the layout from {grid_codes} codes to 1 — "
                     "grids shrink each code and cost the most over compression.")
    else:
        parts.append("On the sender, lower bytes/frame (e.g. 1000 or 500) — "
                     "fatter modules survive compression best.")
    return " ".join(parts)


def headroom(px_per_module: float, block_len: int, grid_codes: int,
             ecc: str = "L") -> str | None:
    """The sender setting that would carry more, with modules still over target.

    None when the stream is already the best this margin affords. The width the
    codes occupy is recovered from the measurement itself, so it holds whether
    the region sees the sender's own pixels or a Citrix rescaling of them.
    """
    if px_per_module < UPGRADE_PX or block_len <= 0 or grid_codes < 1:
        return None
    now_bytes = block_len + HEADER_LEN
    now_cols, now_rows = grid_dims(grid_codes)
    width_px = px_per_module * _cell(now_bytes, ecc) * now_cols
    now_payload = grid_codes * block_len

    best = None
    for frame_bytes in FRAME_BYTES_OPTIONS:
        if frame_bytes > CAPACITY.get(ecc, CAPACITY["L"])[-1]:
            continue            # a code at this level cannot carry that frame
        for codes in GRID_OPTIONS:
            cols, rows = grid_dims(codes)
            px = width_px // (_cell(frame_bytes, ecc) * cols)
            if px < UPGRADE_PX:
                continue
            payload = codes * block_length(frame_bytes)
            # More payload wins; on a tie take the shorter window.
            if best is None or (payload, -rows) > (best[0], -best[2]):
                best = (payload, frame_bytes, rows, codes, px)
    if best is None or best[0] <= now_payload:
        return None

    payload, frame_bytes, rows, codes, px = best
    gain = payload / now_payload
    line = (f"Room to spare at {px_per_module:.1f} px/module. "
            f"On the sender, --bytes {frame_bytes} --codes {codes} carries "
            f"{gain:.1f}x as much and still leaves {px:.0f} px/module.")
    if rows > now_rows:
        line += (f" The window gets {rows / now_rows:.0f}x taller — "
                 "re-drag the region over all of it.")
    return line
