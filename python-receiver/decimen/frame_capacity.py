"""How much payload fits in a stream at a given frame size.

The frame header numbers source blocks in a u16, so a large payload at a small
bytes-per-frame runs out of block numbers long before it runs out of the file
size limit: at 500 bytes per frame the real ceiling is about 30 MB, not 64. The
sender has to catch that before it starts streaming, and say which setting
fixes it.

Mirrors shared/frame-capacity.ts.
"""

from __future__ import annotations

from .protocol import HEADER_LEN

MAX_SOURCE_BLOCKS = 0xFFFF


def block_length(frame_bytes: int) -> int:
    """Payload bytes per frame, once the header has taken its cut."""
    return frame_bytes - HEADER_LEN


def source_block_count(payload_bytes: int, frame_bytes: int) -> int:
    return -(-payload_bytes // block_length(frame_bytes))


def fits_in_one_stream(payload_bytes: int, frame_bytes: int) -> bool:
    return source_block_count(payload_bytes, frame_bytes) <= MAX_SOURCE_BLOCKS


def minimum_frame_bytes(payload_bytes: int) -> int:
    """The smallest bytes-per-frame that can carry this payload at all."""
    return -(-payload_bytes // MAX_SOURCE_BLOCKS) + HEADER_LEN


def smallest_sufficient_frame_size(payload_bytes: int, options) -> int | None:
    """The smallest offered setting that works.

    So the sender can name a value that is actually in the dropdown instead of
    the bare arithmetic minimum.
    """
    minimum = minimum_frame_bytes(payload_bytes)
    usable = sorted(v for v in options if v >= minimum)
    return usable[0] if usable else None
