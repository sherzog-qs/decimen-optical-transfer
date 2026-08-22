"""Frame protocol and file container — the sender half of shared/protocol.ts.

Port notes for anyone comparing the two side by side:

* Every hash and PRNG here is 32-bit integer arithmetic. JavaScript's `| 0`
  becomes `_i32`, `>>> 0` becomes `_u32`, `>>>` becomes `_shr`, and
  `Math.imul` becomes `_imul`. Nothing may be "simplified" into Python's
  arbitrary-precision ints: sender and receiver derive every frame
  independently and never compare notes, so a drift here is a silent total
  failure in the field, not an exception.
* The receiver half — parseFrame, classifyFrame, unpackFile, gunzip — is
  deliberately absent. This is a sender.

The bytes this module must produce are specified in
docs/technical/golden-vectors.md.
"""

from __future__ import annotations

import gzip as _gzip
import hashlib
import re
from dataclasses import dataclass

# ------------------------------------------------------------------ 32-bit ops

_M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """Math.imul — 32-bit multiply, result as a signed int32."""
    r = (a * b) & _M32
    return r - 0x100000000 if r & 0x80000000 else r


def _i32(x: int) -> int:
    """JavaScript `x | 0`."""
    x &= _M32
    return x - 0x100000000 if x & 0x80000000 else x


def _u32(x: int) -> int:
    """JavaScript `x >>> 0`."""
    return x & _M32


def _shr(x: int, n: int) -> int:
    """JavaScript `x >>> n` — shifts the unsigned 32-bit pattern."""
    return (x & _M32) >> n


def fnv1a(data: bytes) -> int:
    h = 0x811C9DC5
    for byte in data:
        h ^= byte
        h = _imul(h, 0x01000193)
    return _u32(h)


def splitmix32(seed: int):
    """Deterministic across engines — integer ops only. Returns a callable."""
    s = _i32(seed)

    def rnd() -> int:
        nonlocal s
        s = _i32(s + 0x9E3779B9)
        t = s ^ _shr(s, 16)
        t = _imul(t, 0x21F0AAAD)
        t = _i32(t ^ _shr(t, 15))
        t = _imul(t, 0x735A2D97)
        t = _i32(t ^ _shr(t, 15))
        return _u32(t)

    return rnd


# ------------------------------------------------------------- frame header

HEADER_LEN = 22
MAGIC0 = 0xD1
MAGIC1 = 0xC3
WIRE_VERSION = 3
CRITICAL_FLAGS = 0x0F
FLAG_ENCRYPTED = 0x01

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_FILE_LABEL = f"{MAX_FILE_BYTES // 1024 // 1024} MB"


@dataclass(frozen=True)
class FrameHeader:
    session_id: int
    seq: int
    k: int
    block_len: int
    total_len: int
    payload_fnv: int
    flags: int = 0


def pack_frame(h: FrameHeader, block: bytes) -> bytes:
    """22-byte header, little-endian throughout, then the block."""
    return b"".join((
        bytes((MAGIC0, MAGIC1, WIRE_VERSION, h.flags)),
        h.session_id.to_bytes(2, "little"),
        h.seq.to_bytes(4, "little"),
        h.k.to_bytes(2, "little"),
        h.block_len.to_bytes(2, "little"),
        h.total_len.to_bytes(4, "little"),
        h.payload_fnv.to_bytes(4, "little"),
        block,
    ))


def stream_identity(h: FrameHeader) -> str:
    """Fields that must hold constant within one transfer.

    The ignorable flag bits (0xF0) are excluded on purpose: a mid-stream flip
    must not reset the decoder and throw away recovered blocks. The separator
    matters — a naive concatenation would collide {k=1, blockLen=23} with
    {k=12, blockLen=3}.
    """
    critical = h.flags & CRITICAL_FLAGS
    return f"{h.session_id}:{h.k}:{h.block_len}:{h.total_len}:{h.payload_fnv}:{critical}"


# --------------------------------------------------------------- container

FILE_HEADER_LEN = 49
FILE_MAGIC = b"DCF2"

SNIPPET_MEDIA_TYPE = "application/vnd.decimen.snippet"
SNIPPET_FILE_NAME = "snippet.txt"
MAX_SNIPPET_BYTES = 4 * 1024 * 1024

# String.prototype.trim's whitespace set. Python's str.strip() is close but not
# identical — it does not strip U+FEFF — and this feeds a wire field.
_JS_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_CONTROL = re.compile("[\u0000-\u001f\u007f]")


def safe_file_name(name: str) -> str:
    """Basename, stripped of control characters, never a relative-path name."""
    base = re.split(r"[\\/]", name)[-1]
    cleaned = _CONTROL.sub("", base).strip(_JS_WHITESPACE)
    return "transfer.bin" if cleaned in ("", ".", "..") else cleaned


PRECOMPRESSED_TYPES = frozenset({
    "application/gzip",
    "application/java-archive",
    "application/vnd.rar",
    "application/x-7z-compressed",
    "application/x-brotli",
    "application/x-bzip",
    "application/x-bzip2",
    "application/x-gzip",
    "application/x-lzma",
    "application/x-rar-compressed",
    "application/x-xz",
    "application/x-zip-compressed",
    "application/zip",
    "application/zstd",
})

_COMPRESSIBLE_IMAGES = re.compile(
    r"^image/(bmp|x-ms-bmp|svg\+xml|tiff|x-icon|vnd\.microsoft\.icon)$"
)
_COMPRESSIBLE_AUDIO = re.compile(
    r"^audio/(wav|x-wav|wave|vnd\.wave|aiff|x-aiff|basic|l16)$"
)


def is_precompressed_type(media_type: str) -> bool:
    """Would gzip be a waste of time on this?

    A list, not a heuristic, and deliberately conservative: a wrong "skip"
    costs a few percent of transfer size, a wrong "try" costs a whole buffer.
    """
    media = media_type.split(";")[0].strip().lower()
    if media.startswith("video/"):
        return True
    if media.startswith("image/"):
        return not _COMPRESSIBLE_IMAGES.match(media)
    if media.startswith("audio/"):
        return not _COMPRESSIBLE_AUDIO.match(media)
    if media.startswith("application/vnd.openxmlformats-officedocument."):
        return True
    if media.startswith("application/vnd.oasis.opendocument."):
        return True
    if media.endswith("+zip"):
        return True
    return media in PRECOMPRESSED_TYPES


@dataclass(frozen=True)
class PackedOpticalFile:
    container: bytes
    compression: str          # "none" | "gzip"
    original_size: int
    transmitted_size: int


class OpticalError(Exception):
    """Coded failure, mirroring shared/optical-error.ts."""

    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


def pack_file(name: str, media_type: str, data: bytes) -> PackedOpticalFile:
    """The container the fountain carries: metadata, optional gzip, SHA-256.

    gzip is attempted only above 768 bytes and only for formats it can help,
    and kept only when it saves more than 64 bytes — the same two thresholds
    shared/protocol.ts uses. Both are wire-visible through the flag byte and
    the transmitted length, so they must not drift.
    """
    if len(data) == 0:
        raise OpticalError("fileEmpty")
    if len(data) > MAX_FILE_BYTES:
        raise OpticalError("fileOverLimit", limit=MAX_FILE_LABEL)

    name_bytes = safe_file_name(name).encode("utf-8")
    type_bytes = (media_type or "application/octet-stream").encode("utf-8")
    if len(name_bytes) > 0xFFFF or len(type_bytes) > 0xFFFF:
        raise OpticalError("fileNameTooLong")

    sha256 = hashlib.sha256(data).digest()
    try_gzip = len(data) >= 768 and not is_precompressed_type(media_type)
    # mtime=0: the default stamps the current time into the gzip header, which
    # would make the container differ run to run for identical input.
    compressed = _gzip.compress(data, mtime=0) if try_gzip else None
    use_gzip = compressed is not None and len(compressed) + 64 < len(data)
    transmitted = compressed if use_gzip else data

    return PackedOpticalFile(
        container=b"".join((
            FILE_MAGIC,
            bytes((1 if use_gzip else 0,)),
            len(name_bytes).to_bytes(2, "little"),
            len(type_bytes).to_bytes(2, "little"),
            len(data).to_bytes(4, "little"),
            len(transmitted).to_bytes(4, "little"),
            sha256,
            name_bytes,
            type_bytes,
            transmitted,
        )),
        compression="gzip" if use_gzip else "none",
        original_size=len(data),
        transmitted_size=len(transmitted),
    )


def pack_snippet(text: str) -> PackedOpticalFile:
    """A text snippet rides the same container a file does."""
    if text.strip() == "":
        raise OpticalError("snippetEmpty")
    data = text.encode("utf-8")
    if len(data) > MAX_SNIPPET_BYTES:
        raise OpticalError("snippetOverLimit")
    return pack_file(SNIPPET_FILE_NAME, SNIPPET_MEDIA_TYPE, data)
