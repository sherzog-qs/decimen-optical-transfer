"""Conformance against docs/technical/golden-vectors.md.

These are golden vectors, not behavioural tests. If one fails you have changed
the wire format. That may be fine — but it is a breaking change and needs a
version bump on the frame header, not a re-recorded constant.

This test does NOT run in CI (a deliberate choice: the pipeline stays
untouched). Run it by hand after any change to shared/fountain.ts,
shared/protocol.ts or shared/frame-capacity.ts:

    uv run python tests/test_conformance.py

Needs segno. The optional QR decode check additionally wants zxing-cpp and
pillow, and skips itself when they are missing.
"""

from __future__ import annotations

import gzip
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from decimen import frame_capacity as cap
from decimen import protocol as p
from decimen import qr as q
from decimen.fountain import LTEncoder, cycle_length, frame_composition

checks = 0


def check(condition, label):
    global checks
    assert condition, f"FAILED: {label}"
    checks += 1


def payload_of(byte_length: int) -> bytes:
    """testPayload() from tests/fountain.test.ts."""
    return bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(byte_length))


def frame_of(n: int) -> bytes:
    """The QR reference input from qr-reference-fingerprints.txt."""
    data = bytearray((i * 37 + 11) & 0xFF for i in range(n))
    data[0:4] = bytes((0xD1, 0xC3, 3, 0x00))
    return bytes(data)


# ---------------------------------------------------- the canonical frame

def test_canonical_frame():
    """golden-vectors.md, "Canonical frame". Every field distinct, so a
    swapped offset cannot pass by accident."""
    frame = p.pack_frame(
        p.FrameHeader(session_id=0xBEEF, seq=0x01020304, k=0x0111, block_len=6,
                      total_len=0x00FEDCBA, payload_fnv=0x89ABCDEF, flags=0x00),
        bytes((1, 2, 3, 4, 5, 6)),
    )
    check(frame.hex() == "d1c30300efbe040302011101"
                         "0600badcfe00efcdab89010203040506",
          f"canonical frame is {frame.hex()}")
    check(len(frame) == p.HEADER_LEN + 6, "frame length is header + blockLen")


def test_stream_identity():
    """The identity must not be a naive concatenation."""
    def ident(**kw):
        base = dict(session_id=1, seq=0, k=1, block_len=23, total_len=9,
                    payload_fnv=7, flags=0)
        base.update(kw)
        return p.stream_identity(p.FrameHeader(**base))

    check(ident(k=1, block_len=23) != ident(k=12, block_len=3),
          "k/blockLen must not collide across the separator")
    check(ident(seq=0) == ident(seq=999),
          "seq is the one field that varies within a stream")
    check(ident(flags=0x10) == ident(flags=0x00),
          "ignorable flag bits must not reset the decoder")
    check(ident(flags=0x01) != ident(flags=0x00),
          "critical flag bits are part of the identity")


# ------------------------------------------------------ fountain carousel

GOLDEN_STREAMS = [
    (1, 64, 1, 0xF6A115C5),
    (23, 64, 7, 0x4A5D3EAA),
    (179, 2933, 4242, 0x54F78D05),
    (716, 1445, 65535, 0x75B73B85),
]


def test_stream_fingerprints():
    """One hash covers frame_seed, splitmix32, the repair draw, the block
    padding and the XOR order together."""
    for k, block_len, session_id, expected in GOLDEN_STREAMS:
        enc = LTEncoder(payload_of(k * block_len - 7), block_len, session_id)
        check(enc.k == k, f"k={k} derived from the payload")
        stream = b"".join(enc.encode(seq) for seq in range(64))
        check(p.fnv1a(stream) == expected,
              f"stream k={k}/{block_len}/{session_id} is 0x{p.fnv1a(stream):08x}")


def test_carousel_structure():
    for k in (1, 17, 179, 4096):
        check(cycle_length(k) == 2 * k, f"cycle length k={k}")
        for pos in {0, k >> 1, k - 1}:
            check(frame_composition(k, 9, pos) == [pos], f"sweep k={k} pos={pos}")
            check(frame_composition(k, 9, pos + 6 * cycle_length(k)) == [pos],
                  f"sweep restarts every cycle, k={k} pos={pos}")
        for seq in (k, k + 1, 2 * k - 1):
            idx = frame_composition(k, 9, seq)
            check(min(k, 4) <= len(idx) <= min(k, 24), f"repair degree k={k} seq={seq}")
            check(len(set(idx)) == len(idx), f"repair blocks distinct k={k} seq={seq}")
            check(all(0 <= b < k for b in idx), f"repair blocks in range k={k} seq={seq}")


def test_every_frame_is_full_length():
    """The sender pins the QR version off the first frame, so a short tail
    frame would silently produce an undecodable code for the rest."""
    block_len = 1445
    enc = LTEncoder(payload_of(block_len * 5 + 1), block_len, 3)
    check(enc.k == 6, "k covers the short tail block")
    for seq in range(200):
        check(len(enc.encode(seq)) == block_len, f"frame {seq} is blockLen bytes")


# ------------------------------------------------------------- container

def test_container_layout():
    """Byte-exact, at the offsets the container declares. Small payload, so
    gzip never enters and the whole container is comparable."""
    data = bytes(range(200))
    packed = p.pack_file("report.pdf", "application/pdf", data)
    c = packed.container
    check(c[0:4] == b"DCF2", "container magic")
    check(c[4] == 0, "gzip flag clear below the 768-byte floor")
    check(int.from_bytes(c[5:7], "little") == 10, "name length")
    check(int.from_bytes(c[7:9], "little") == 15, "type length")
    check(int.from_bytes(c[9:13], "little") == 200, "original length")
    check(int.from_bytes(c[13:17], "little") == 200, "transmitted length")
    check(c[17:49] == hashlib.sha256(data).digest(), "sha256 of the ORIGINAL bytes")
    check(c[49:59] == b"report.pdf", "name bytes")
    check(c[59:74] == b"application/pdf", "type bytes")
    check(c[74:] == data, "payload verbatim")
    check(len(c) == p.FILE_HEADER_LEN + 10 + 15 + 200, "no padding anywhere")
    check(packed.compression == "none", "compression reported as none")


def test_gzip_decision():
    """Both thresholds are wire-visible through the flag byte and the
    transmitted length, so they must not drift."""
    compressible = b"A" * 5000
    packed = p.pack_file("a.txt", "text/plain", compressible)
    check(packed.compression == "gzip", "a run of 5000 identical bytes gzips")
    check(packed.container[4] == 1, "gzip flag set")
    body = packed.container[p.FILE_HEADER_LEN + 5 + 10:]
    check(gzip.decompress(body) == compressible, "gzip payload round-trips")
    check(int.from_bytes(packed.container[9:13], "little") == 5000,
          "original length is the uncompressed size")

    check(p.pack_file("a.txt", "text/plain", b"A" * 767).compression == "none",
          "767 bytes is below the 768-byte floor")

    # Genuinely incompressible: an arithmetic sequence is not — gzip finds the
    # structure and saves more than the 64-byte margin.
    noise = b""
    seed = b"decimen"
    while len(noise) < 4096:
        seed = hashlib.sha256(seed).digest()
        noise += seed
    noise = noise[:4096]
    packed = p.pack_file("a.bin", "application/octet-stream", noise)
    check(packed.compression == "none", "gzip that does not save 64 bytes is dropped")
    check(packed.container[4] == 0, "gzip flag clear")

    packed = p.pack_file("a.jpg", "image/jpeg", b"A" * 5000)
    check(packed.compression == "none", "image/jpeg is never gzipped")


def test_is_precompressed_type():
    for media in ("video/mp4", "video/quicktime", "image/jpeg", "image/png",
                  "image/webp", "audio/mpeg", "audio/mp4",
                  "application/zip", "application/gzip", "application/zstd",
                  "application/x-7z-compressed", "application/epub+zip",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  "application/vnd.oasis.opendocument.text",
                  "IMAGE/JPEG", "image/jpeg; charset=binary"):
        check(p.is_precompressed_type(media), f"{media} is precompressed")

    for media in ("text/plain", "application/pdf", "application/json",
                  "image/bmp", "image/svg+xml", "image/tiff", "image/x-icon",
                  "audio/wav", "audio/x-aiff", "audio/l16",
                  "application/vnd.decimen.snippet", "", "application/octet-stream"):
        check(not p.is_precompressed_type(media), f"{media} is worth gzipping")


def test_safe_file_name():
    check(p.safe_file_name("/etc/passwd") == "passwd", "posix path stripped")
    check(p.safe_file_name("C:\\Windows\\evil.exe") == "evil.exe", "windows path stripped")
    check(p.safe_file_name("..") == "transfer.bin", "relative name replaced")
    check(p.safe_file_name(".") == "transfer.bin", "dot replaced")
    check(p.safe_file_name("") == "transfer.bin", "empty replaced")
    check(p.safe_file_name("a\u0000b.txt") == "ab.txt", "NUL stripped")
    check(p.safe_file_name("a\nb.txt") == "ab.txt", "newline stripped")
    check(p.safe_file_name("  spaced.txt  ") == "spaced.txt", "trimmed")
    check(p.safe_file_name("\ufeffbom.txt") == "bom.txt", "U+FEFF trimmed like JS")


def test_snippet():
    packed = p.pack_snippet("hello")
    c = packed.container
    name_len = int.from_bytes(c[5:7], "little")
    type_len = int.from_bytes(c[7:9], "little")
    check(c[49:49 + name_len] == b"snippet.txt", "snippet file name")
    check(c[49 + name_len:49 + name_len + type_len] == p.SNIPPET_MEDIA_TYPE.encode(),
          "snippet media type")
    check(c[49 + name_len + type_len:] == b"hello", "snippet payload")


# -------------------------------------------------------- capacity maths

def test_capacity():
    check(cap.block_length(2953) == 2931, "block length is frame minus header")
    check(cap.source_block_count(2931 * 3, 2953) == 3, "exact fit")
    check(cap.source_block_count(2931 * 3 + 1, 2953) == 4, "remainder needs a block")
    check(cap.MAX_SOURCE_BLOCKS == 0xFFFF, "k is a u16")
    check(cap.fits_in_one_stream(1 << 20, 2953), "1 MB fits at the default")
    check(not cap.fits_in_one_stream(64 << 20, 500), "64 MB does not fit at 500 B")
    check(cap.smallest_sufficient_frame_size(
        64 << 20, [500, 1000, 1465, 1850, 2331, 2953]) == 1465,
        "names an offered setting, not the arithmetic minimum")
    check(cap.smallest_sufficient_frame_size(64 << 20, [500]) is None,
          "no option large enough returns None")


# ---------------------------------------------------------- QR generation

def test_qr_geometry_and_fingerprints():
    table = pathlib.Path(__file__).with_name("qr-reference-fingerprints.txt")
    rows = [l.split() for l in table.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]
    check(len(rows) == 20, "20 reference cases")

    for label, version, size, fnv, comparable in rows:
        n, ecc = int(label[:-1]), label[-1]
        version, size, fnv = int(version), int(size), int(fnv, 16)
        data = frame_of(n)

        auto = q.create_frame_qr(data, ecc, None)
        locked = q.create_frame_qr(data, ecc, version)
        check(auto.version == version, f"{label} picks v{version} unprompted")
        check(len(locked.matrix) == size, f"{label} is {size} modules")
        check(auto.error == ecc, f"{label} keeps ECC {ecc} (boost_error must be off)")

        if comparable == "ja":
            bits = [1 if m else 0 for row in locked.matrix for m in row]
            packed = bytearray()
            for i in range(0, len(bits), 8):
                v = 0
                for j, bit in enumerate(bits[i:i + 8]):
                    v |= bit << (7 - j)
                packed.append(v)
            check(p.fnv1a(bytes(packed)) == fnv, f"{label} matrix fingerprint")


def test_qr_decodes_to_source():
    """Optional: needs zxing-cpp and pillow. Proves the pad-codeword
    difference against npm qrcode is invisible on the wire."""
    try:
        import zxingcpp
        from PIL import Image
    except ImportError:
        print("  (QR decode probe skipped - zxing-cpp/pillow missing)")
        return

    for n, ecc in ((2953, "L"), (500, "L"), (200, "H")):
        data = frame_of(n)
        code = q.create_frame_qr(data, ecc, None)
        width, height, rgb = q.rasterize_qr_grid([list(code.matrix)], scale=3)
        img = Image.frombytes("RGB", (width, height), rgb).convert("L")
        found = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode,
                                       binarizer=zxingcpp.Binarizer.FixedThreshold)
        check(bool(found) and bytes(found[0].bytes) == data,
              f"{n}B/{ecc} decodes back to the source bytes")


def test_grid_dims():
    check(q.grid_dims(1) == (1, 1), "1 code")
    check(q.grid_dims(2) == (1, 2), "2 codes stack, taller before wider")
    check(q.grid_dims(4) == (2, 2), "4 codes")
    check(q.grid_dims(6) == (2, 3), "6 codes")
    check(q.grid_dims(9) == (3, 3), "9 codes")
    # Anything that fills its rectangle is accepted, not just the four the
    # sender offers: 3 is 1x3, 8 is 2x4. The refusals are the counts that
    # would leave a cell empty.
    check(q.grid_dims(3) == (1, 3), "3 codes stack")
    check(q.grid_dims(8) == (2, 4), "8 codes")
    for bad in (0, 5, 7, 10, 11, 13, 14):
        try:
            q.grid_dims(bad)
            raise AssertionError(f"FAILED: grid of {bad} must be refused")
        except ValueError:
            check(True, f"grid of {bad} refused")


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        fn()
        print(f"  {name:36} ok")
    print(f"\n{checks} checks passed across {len(tests)} groups")
