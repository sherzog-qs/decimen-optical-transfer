"""The sender's transmit tuning, in one place — mirrors shared/send-settings.ts.

The dropdowns render from these lists, so a value the user can pick is always
a value the protocol was measured at.
"""

from __future__ import annotations

# What the RECEIVER's no-signal hint tells the user to turn the sender down to.
# Kept here so that advice can never name a setting the sender does not offer.
# The hint itself lives on the receiving page and has no sender-side equivalent:
# a screen-to-camera link has no back-channel, so a sender cannot know whether
# anything is arriving.
NO_SIGNAL_HINT_FRAME_BYTES = 1465
NO_SIGNAL_HINT_TX_FPS = 24

# Default 60: full rate for high-refresh senders. The 60 Hz caveat is real — a
# frame needs at least two refresh cycles on screen or captures catch the
# transition, and on a 60 Hz display every 60 fps frame gets exactly one.
DEFAULT_TX_FPS = 60
DEFAULT_FRAME_BYTES = 2953

# 55 sits just under the 60 Hz ceiling: on 120 Hz displays it gets a clean two
# refresh cycles per frame, and on 60 Hz screens the deliberate 5 fps slip means
# frame boundaries drift through the scanout instead of riding it.
TX_FPS_OPTIONS = [10, 15, 20, NO_SIGNAL_HINT_TX_FPS, 30, 55, DEFAULT_TX_FPS]
FRAME_BYTES_OPTIONS = [500, 1000, NO_SIGNAL_HINT_FRAME_BYTES, 1850, 2331, DEFAULT_FRAME_BYTES]

ECC_OPTIONS = ["L", "M", "Q", "H"]
DEFAULT_ECC = "L"

# The largest payload a version-40 byte-mode QR holds at each level — fixed by
# the QR spec, and measured against segno rather than quoted from memory. It is
# why frame size and error correction are not independent: 2953 bytes only fit
# at L, and asking for more than a code can carry is not an error the fountain
# can absorb. The web sender catches the generator throwing (send/main.ts:708);
# this side keeps the pairing visible instead.
MAX_FRAME_BYTES_BY_ECC = {"L": 2953, "M": 2331, "Q": 1663, "H": 1273}


def frame_bytes_for(ecc: str) -> list[int]:
    """The offered frame sizes that actually fit at this level."""
    cap = MAX_FRAME_BYTES_BY_ECC[ecc]
    return [value for value in FRAME_BYTES_OPTIONS if value <= cap]

# Counts that fill their rectangle — see grid_dims(). The sender offers these
# four; the rasteriser accepts any count that tiles.
GRID_OPTIONS = [("1 code", 1), ("2 codes (1x2)", 2), ("4 codes (2x2)", 4), ("6 codes (2x3)", 6)]
DEFAULT_GRID = 1

DISPLAY_SIZE_MIN, DISPLAY_SIZE_MAX, DISPLAY_SIZE_STEP = 300, 1200, 50
DEFAULT_DISPLAY_SIZE = 900
