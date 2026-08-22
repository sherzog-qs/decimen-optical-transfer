"""Frame protocol and file container — the receive half of shared/protocol.ts.

The shared 32-bit primitives (_imul/_i32/_u32/_shr, fnv1a, splitmix32) are
byte-identical to python-sender/decimen/protocol.py — copied, not imported,
because this folder is standalone (see the map). The conformance test holds
both copies to the same vectors so they cannot drift.

What is here and not in the sender: parse_frame, classify_frame,
frame_verdict_message, stream_identity, unpack_file, verify_file, gunzip. What
is NOT: pack_frame, pack_file — this is a receiver.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass

# ------------------------------------------------------------------ 32-bit ops

_M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    r = (a * b) & _M32
    return r - 0x100000000 if r & 0x80000000 else r


def _i32(x: int) -> int:
    x &= _M32
    return x - 0x100000000 if x & 0x80000000 else x


def _u32(x: int) -> int:
    return x & _M32


def _shr(x: int, n: int) -> int:
    return (x & _M32) >> n


def fnv1a(data: bytes) -> int:
    h = 0x811C9DC5
    for byte in data:
        h ^= byte
        h = _imul(h, 0x01000193)
    return _u32(h)


def splitmix32(seed: int):
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
SUPPORTED_FLAGS = 0x00
# Byte-1 values of the pre-versioning formats -> their version number.
LEGACY_MAGIC1 = {0x0C: 1, 0x0D: 2}

MAX_FILE_BYTES = 64 * 1024 * 1024
FILE_HEADER_LEN = 49
FILE_MAGIC = b"DCF2"


@dataclass(frozen=True)
class FrameHeader:
    session_id: int
    seq: int
    k: int
    block_len: int
    total_len: int
    payload_fnv: int
    flags: int


@dataclass(frozen=True)
class FrameVerdict:
    """Why a frame did or did not parse. `foreign` is the silent case: the
    receiver decodes every QR in view, and narrating stray ones is noise."""
    kind: str                        # ok|foreign|older-sender|newer-sender|
                                     # unsupported-flags|malformed
    version: int = 0
    flags: int = 0


def classify_frame(data: bytes) -> FrameVerdict:
    """Single owner of 'is this ours, and can we decode it?'.

    parse_frame delegates here so the yes/no and the reason for a no cannot
    drift apart — the failure mode versioning exists to prevent.
    """
    if len(data) < 4 or data[0] != MAGIC0:
        return FrameVerdict("foreign")
    if data[1] != MAGIC1:
        legacy = LEGACY_MAGIC1.get(data[1])
        return (FrameVerdict("foreign") if legacy is None
                else FrameVerdict("older-sender", version=legacy))

    version = data[2]
    if version == 0:
        return FrameVerdict("malformed")
    if version != WIRE_VERSION:
        return FrameVerdict("newer-sender" if version > WIRE_VERSION else "older-sender",
                            version=version)

    unknown_critical = data[3] & CRITICAL_FLAGS & ~SUPPORTED_FLAGS
    if unknown_critical != 0:
        return FrameVerdict("unsupported-flags", flags=unknown_critical)

    if len(data) <= HEADER_LEN:
        return FrameVerdict("malformed")
    k = int.from_bytes(data[10:12], "little")
    block_len = int.from_bytes(data[12:14], "little")
    total_len = int.from_bytes(data[14:18], "little")
    if k == 0 or block_len == 0 or total_len == 0:
        return FrameVerdict("malformed")
    if len(data) != HEADER_LEN + block_len:
        return FrameVerdict("malformed")
    return FrameVerdict("ok")


def frame_verdict_message(verdict: FrameVerdict) -> str | None:
    """The English reference wording, or None when there is nothing to say."""
    if verdict.kind == "older-sender":
        return (f"That screen is sending an older Decimen format "
                f"(v{verdict.version}). Update the sending device.")
    if verdict.kind == "newer-sender":
        return (f"That screen is sending a newer Decimen format "
                f"(v{verdict.version}). Update this app to receive it.")
    if verdict.kind == "unsupported-flags":
        return ("That stream uses a Decimen feature this version cannot read. "
                "Update this app to receive it.")
    return None


def parse_frame(data: bytes):
    """(FrameHeader, block bytes) or None if the frame is not ok."""
    if classify_frame(data).kind != "ok":
        return None
    header = FrameHeader(
        flags=data[3],
        session_id=int.from_bytes(data[4:6], "little"),
        seq=int.from_bytes(data[6:10], "little"),
        k=int.from_bytes(data[10:12], "little"),
        block_len=int.from_bytes(data[12:14], "little"),
        total_len=int.from_bytes(data[14:18], "little"),
        payload_fnv=int.from_bytes(data[18:22], "little"),
    )
    return header, data[HEADER_LEN:]


def stream_identity(h: FrameHeader) -> str:
    """Everything that must hold constant for a decoder to keep accepting
    frames. `seq` is absent — the one field that varies within a stream. The
    receiver resets on ANY disagreement, not just a new session id: 16-bit ids
    collide across restarts, and a mismatched frame corrupts the decoder
    silently, surfacing only as a checksum failure after the whole run.
    """
    return (f"{h.session_id}:{h.k}:{h.block_len}:{h.total_len}:"
            f"{h.payload_fnv}:{h.flags & CRITICAL_FLAGS}")


# --------------------------------------------------------------- container

# String.prototype.trim's whitespace set — mirrors the sender's table so a name
# strips identically on both ends. Escapes, not literals: control characters in
# source are both invalid and invisible.
_JS_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_CONTROL = re.compile("[\u0000-\u001f\u007f]")

SNIPPET_MEDIA_TYPE = "application/vnd.decimen.snippet"


def safe_file_name(name: str) -> str:
    """Applied on both ends; here it is the part that matters, because the name
    arrived over the optical channel and is whatever the other screen chose."""
    base = re.split(r"[\\/]", name)[-1]
    cleaned = _CONTROL.sub("", base).strip(_JS_WHITESPACE)
    return "transfer.bin" if cleaned in ("", ".", "..") else cleaned


class OpticalError(Exception):
    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class OpticalFile:
    name: str
    type: str
    sha256: bytes
    data: bytes
    compression: str
    transmitted_size: int

    @property
    def is_snippet(self) -> bool:
        return self.type == SNIPPET_MEDIA_TYPE


def _gunzip(data: bytes, max_bytes: int) -> bytes:
    """Inflate with a hard output ceiling. The gzip trailer's declared size is
    attacker-controlled — it arrived over the optical channel — so it is a
    hint, never a bound. Count bytes off the stream and abort past max_bytes."""
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)   # 16 => gzip wrapper
    out = bytearray()
    for start in range(0, len(data), 65536):
        out += dec.decompress(data[start:start + 65536], max_bytes - len(out) + 1)
        if len(out) > max_bytes:
            raise OpticalError("inflateOverflow")
    out += dec.flush()
    if len(out) > max_bytes:
        raise OpticalError("inflateOverflow")
    return bytes(out)


def unpack_file(container: bytes) -> OpticalFile:
    if len(container) < FILE_HEADER_LEN:
        raise OpticalError("containerTruncated")
    if container[:4] != FILE_MAGIC:
        raise OpticalError("containerBadMagic")

    compression_byte = container[4]
    if compression_byte > 1:
        raise OpticalError("containerBadCompression")
    compression = "gzip" if compression_byte == 1 else "none"
    name_len = int.from_bytes(container[5:7], "little")
    type_len = int.from_bytes(container[7:9], "little")
    file_len = int.from_bytes(container[9:13], "little")
    transmitted_len = int.from_bytes(container[13:17], "little")
    data_offset = FILE_HEADER_LEN + name_len + type_len
    if (file_len == 0 or file_len > MAX_FILE_BYTES
            or transmitted_len == 0 or transmitted_len > MAX_FILE_BYTES
            or data_offset + transmitted_len != len(container)):
        raise OpticalError("containerLengthMismatch")

    transmitted = container[data_offset:]
    if compression == "gzip":
        if len(transmitted) < 18:
            raise OpticalError("gzipIncomplete")
        if int.from_bytes(transmitted[-4:], "little") != file_len:
            raise OpticalError("gzipLengthMismatch")
    data = _gunzip(transmitted, file_len) if compression == "gzip" else transmitted
    if len(data) != file_len:
        raise OpticalError("decompressedLengthMismatch")

    name = safe_file_name(container[FILE_HEADER_LEN:FILE_HEADER_LEN + name_len]
                          .decode("utf-8", "replace"))
    media = (container[FILE_HEADER_LEN + name_len:data_offset]
             .decode("utf-8", "replace") or "application/octet-stream")
    return OpticalFile(name=name, type=media, sha256=container[17:49], data=data,
                       compression=compression, transmitted_size=transmitted_len)


def verify_file(file: OpticalFile) -> bool:
    return hashlib.sha256(file.data).digest() == file.sha256


def snippet_text(file: OpticalFile) -> str:
    if not file.is_snippet:
        raise OpticalError("snippetNotText")
    try:
        return file.data.decode("utf-8")
    except UnicodeDecodeError:
        raise OpticalError("snippetBadUtf8")
