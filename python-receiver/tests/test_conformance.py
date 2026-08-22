"""Conformance for the receive half, against docs/technical/golden-vectors.md.

Golden vectors, not behavioural tests. A failure means the wire format changed,
which is a breaking change and needs a header version bump, not a re-recorded
constant.

Does NOT run in CI, by choice. Run by hand after any change to
shared/fountain.ts, shared/protocol.ts or shared/frame-capacity.ts — a drift
raises no exception, the transfer just never completes.

    uv run python tests/test_conformance.py

The end-to-end round trip needs the python-sender's LTEncoder (imported from the
sibling folder) and, optionally, the TypeScript decoder path via node.
"""

from __future__ import annotations

import gzip
import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))       # this receiver's decimen only

from decimen import protocol as p
from decimen.fountain import LTDecoder, cycle_length, frame_composition


def _load_sender():
    """Load python-sender/decimen as a separate package tree, so its modules do
    not collide with this receiver's identically-named `decimen`. The two are
    standalone copies; the test's whole job is to make them meet."""
    import importlib.util, types
    root = HERE.parent.parent / "python-sender" / "decimen"
    pkg = types.ModuleType("sender_decimen")
    pkg.__path__ = [str(root)]
    sys.modules["sender_decimen"] = pkg
    mods = {}
    for name in ("protocol", "frame_capacity", "fountain", "qr"):
        spec = importlib.util.spec_from_file_location(f"sender_decimen.{name}",
                                                      root / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[f"sender_decimen.{name}"] = m
        spec.loader.exec_module(m)
        mods[name] = m
    return mods


SENDER = _load_sender()

checks = 0


def check(cond, label):
    global checks
    assert cond, f"FAILED: {label}"
    checks += 1


# ------------------------------------------------- classification vectors

def test_canonical_frame_parses():
    """The canonical frame from golden-vectors.md, byte for byte."""
    frame = bytes.fromhex("d1c30300efbe040302011101"
                          "0600badcfe00efcdab89010203040506")
    verdict = p.classify_frame(frame)
    check(verdict.kind == "ok", f"canonical frame classifies ok, got {verdict.kind}")
    parsed = p.parse_frame(frame)
    check(parsed is not None, "canonical frame parses")
    h, block = parsed
    check(h.session_id == 0xBEEF, "sessionId")
    check(h.seq == 0x01020304, "seq")
    check(h.k == 0x0111, "k")
    check(h.block_len == 6, "blockLen")
    check(h.total_len == 0x00FEDCBA, "totalLen")
    check(h.payload_fnv == 0x89ABCDEF, "payloadFnv")
    check(block == bytes((1, 2, 3, 4, 5, 6)), "block")


def test_classification():
    """golden-vectors.md classification vectors: only bytes 0–3 decide these."""
    ok = bytes.fromhex("d1c30300efbe0403020111010600badcfe00efcdab89010203040506")
    def mut(i, v):
        b = bytearray(ok); b[i] = v; return bytes(b)

    check(p.classify_frame(b"\x00\x00").kind == "foreign", "too short is foreign")
    check(p.classify_frame(mut(0, 0x00)).kind == "foreign", "wrong magic0 is foreign")
    check(p.classify_frame(mut(1, 0x0C)).kind == "older-sender", "0x0C is v1 sender")
    check(p.classify_frame(mut(1, 0x0D)).kind == "older-sender", "0x0D is v2 sender")
    check(p.classify_frame(mut(1, 0x99)).kind == "foreign", "unknown magic1 is foreign")
    check(p.classify_frame(mut(2, 0x00)).kind == "malformed", "version 0 is malformed")
    check(p.classify_frame(mut(2, 0x02)).kind == "older-sender", "version 2 is older")
    check(p.classify_frame(mut(2, 0x04)).kind == "newer-sender", "version 4 is newer")
    check(p.classify_frame(mut(3, 0x01)).kind == "unsupported-flags",
          "unknown critical flag refused")
    check(p.classify_frame(mut(3, 0x10)).kind == "ok", "ignorable flag decodes anyway")

    v = p.FrameVerdict("older-sender", version=2)
    check("older Decimen format (v2)" in p.frame_verdict_message(v), "older wording")
    check(p.frame_verdict_message(p.FrameVerdict("foreign")) is None, "foreign is silent")


def test_self_consistency():
    """A frame is malformed when total length != 22 + blockLen, or a field is 0."""
    base = bytes.fromhex("d1c30300efbe0403020111010600badcfe00efcdab89010203040506")
    check(p.classify_frame(base[:22]).kind == "malformed", "header with no block")
    def zero(off): 
        b = bytearray(base); b[off:off+2] = b"\x00\x00"; return bytes(b)
    check(p.classify_frame(zero(10)).kind == "malformed", "k=0")
    check(p.classify_frame(zero(12)).kind == "malformed", "blockLen=0")
    check(p.classify_frame(base + b"\x00").kind == "malformed", "length != 22+blockLen")


def test_stream_identity():
    def ident(**kw):
        base = dict(session_id=1, seq=0, k=1, block_len=23, total_len=9,
                    payload_fnv=7, flags=0)
        base.update(kw)
        return p.stream_identity(p.FrameHeader(**base))
    check(ident(k=1, block_len=23) != ident(k=12, block_len=3),
          "k/blockLen must not collide")
    check(ident(seq=0) == ident(seq=999), "seq varies within a stream")
    check(ident(flags=0x10) == ident(flags=0x00), "ignorable flags do not reset")
    check(ident(flags=0x01) != ident(flags=0x00), "critical flags are part of identity")
    check(ident(payload_fnv=1) != ident(payload_fnv=2), "payloadFnv distinguishes files")


# ---------------------------------------------------------- container decode

def test_container_roundtrip():
    """unpack_file reverses the sender's pack_file, byte for byte."""
    sp = SENDER["protocol"]
    # Incompressible, so this exercises the compression="none" path. A SHA-256
    # chain is genuinely random-looking; range(256) would gzip.
    data, seed = bytearray(), b"roundtrip"
    while len(data) < 1024:
        seed = hashlib.sha256(seed).digest(); data += seed
    data = bytes(data[:1024])
    packed = sp.pack_file("report.pdf", "application/pdf", data)
    check(packed.compression == "none", "incompressible payload is not gzipped")
    got = p.unpack_file(packed.container)
    check(got.name == "report.pdf", "name survives")
    check(got.type == "application/pdf", "type survives")
    check(got.data == data, "bytes survive")
    check(got.compression == "none", "compression reported")
    check(p.verify_file(got), "sha256 verifies")

    # A compressible payload -> gzip -> gunzip round-trips
    text = b"decimen " * 2000
    packed = sp.pack_file("notes.txt", "text/plain", text)
    check(packed.compression == "gzip", "compressible payload gzips at the sender")
    got = p.unpack_file(packed.container)
    check(got.data == text, "gzip payload recovers exactly")
    check(p.verify_file(got), "sha256 of gzip payload verifies")

    # A snippet
    snip = sp.pack_snippet("hello over light")
    got = p.unpack_file(snip.container)
    check(got.is_snippet, "snippet recognised")
    check(p.snippet_text(got) == "hello over light", "snippet text")


def test_container_rejections():
    check_raises(lambda: p.unpack_file(b"XX"), "containerTruncated")
    bad = bytearray(b"XXXX" + b"\x00" * 60)
    check_raises(lambda: p.unpack_file(bytes(bad)), "containerBadMagic")


def check_raises(fn, code):
    try:
        fn()
        check(False, f"expected {code}, nothing raised")
    except p.OpticalError as e:
        check(e.code == code, f"raised {e.code}, expected {code}")


def test_gunzip_overflow_guard():
    """The gzip trailer is attacker-controlled: a small stream claiming to be
    huge must be refused, not inflated to gigabytes."""
    payload = b"A" * 100000
    comp = gzip.compress(payload, mtime=0)
    check(len(p._gunzip(comp, 100000)) == 100000, "honest gunzip works")
    check_raises(lambda: p._gunzip(comp, 50000), "inflateOverflow")


# ------------------------------------------------ end-to-end round trips

def payload_of(n):
    return bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(n))


def test_roundtrip_against_python_sender():
    """The encounter point within Python: the sender's LTEncoder produces
    frames, this LTDecoder rebuilds the file, over deterministic frame loss."""
    sp = SENDER["protocol"]
    LTEncoder = SENDER["fountain"].LTEncoder
    block_length = SENDER["frame_capacity"].block_length

    original = payload_of(300 * 1024)
    block_len = block_length(2953)
    enc = LTEncoder(original, block_len, 4242)
    dec = LTDecoder(enc.k, block_len, 4242, len(original))

    parsed_frames = 0
    header = sp.FrameHeader(session_id=4242, seq=0, k=enc.k, block_len=block_len,
                            total_len=len(original), payload_fnv=sp.fnv1a(original),
                            flags=0)
    for seq in range(enc.k * 3):
        if (seq * 7919) % 100 < 15:
            continue
        frame = sp.pack_frame(sp.FrameHeader(**{**header.__dict__, "seq": seq}),
                              enc.encode(seq))
        got = p.parse_frame(frame)
        check(got is not None, f"frame {seq} parses")
        parsed_frames += 1
        h, block = got
        dec.add_frame(h.seq, block)
        if dec.is_complete:
            break

    check(dec.is_complete, "file completed over 15% loss")
    recovered = dec.assemble()
    check(recovered == original, "every byte recovered")
    check(hashlib.sha256(recovered).digest() == hashlib.sha256(original).digest(),
          "sha256 matches")
    check(dec.frames_new <= enc.k * 1.3, "overhead under 1.3x")


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        fn()
        print(f"  {name:38} ok")
    print(f"\n{checks} checks passed across {len(tests)} groups")
