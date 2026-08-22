"""The fountain carousel — the sender half of shared/fountain.ts.

fountain.ts IS the wire format. Sender and receiver derive every frame's block
subset independently and never compare notes, so a change to frame_composition,
frame_seed or splitmix32 breaks compatibility silently: the transfer simply
never completes. See docs/technical/golden-vectors.md, "Fountain carousel".

Not ported, on purpose: dlog, solitonCdf and frameIndices. They are the v1
robust-soliton stream and have not been emitted since wire v2 — the TypeScript
keeps them only because their vectors were expensive to derive. A sender does
not need them.

Also absent: the decoder. This is a sender.
"""

from __future__ import annotations

from .protocol import _i32, _imul, _shr, splitmix32

REPAIR_DEGREE_MIN = 4
REPAIR_DEGREE_MAX = 24


def cycle_length(k: int) -> int:
    """Frames per carousel cycle: one systematic sweep, then k repair frames."""
    return 2 * k


def frame_seed(session_id: int, seq: int) -> int:
    h = _i32(_imul(session_id + 1, 0x9E3779B1) ^ _i32(seq + 0x85EBCA6B))
    h = _imul(h ^ _shr(h, 13), 0xC2B2AE35)
    return _i32(h ^ _shr(h, 16))


def repair_indices(k: int, session_id: int, seq: int) -> list[int]:
    """Uniform mid-degree (4-24), NOT robust-soliton.

    After a sweep the receiver holds most blocks, so a repair frame's effective
    degree is what remains after XORing the solved ones out — soliton's heavy
    degree-1/2 mass just re-sends blocks the sweep already delivered.

    The dict is doing a job: JavaScript's Set preserves insertion order and a
    Python set does not. The XOR does not care, but a comparison against the
    recorded index list does.
    """
    rnd = splitmix32(frame_seed(session_id, seq))
    d = min(k, REPAIR_DEGREE_MIN + rnd() % (REPAIR_DEGREE_MAX - REPAIR_DEGREE_MIN + 1))
    seen: dict[int, None] = {}
    while len(seen) < d:
        seen[rnd() % k] = None
    return list(seen)


def frame_composition(k: int, session_id: int, seq: int) -> list[int]:
    """Block subset for frame `seq`: systematic in the sweep, repair after.

    There is no handshake and none is needed — the carousel repeats forever, so
    a receiver locking on anywhere in the cycle takes systematic frames whenever
    their block is still unsolved, and repair frames from ANY cycle patch the
    sweep's losses. Repair frames seed from the ABSOLUTE seq, so re-watching the
    carousel never replays the same subsets.
    """
    pos = seq % cycle_length(k)
    return [pos] if pos < k else repair_indices(k, session_id, seq)


class LTEncoder:
    """Blocks padded to a 4-byte stride, XORed per frame.

    The stride mirrors the Uint32Array the TypeScript XORs over: the tail block
    is zero-filled to the stride, and a frame emits the first `block_len` bytes
    of the XOR. Every frame is therefore exactly `block_len` bytes — the sender
    pins the QR version off the first frame, so a short tail frame would
    silently produce an undecodable code for the rest of the transfer.
    """

    def __init__(self, payload: bytes, block_len: int, session_id: int):
        self.block_len = block_len
        self.session_id = session_id
        self.k = max(1, -(-len(payload) // block_len))
        self._stride = -(-block_len // 4) * 4
        self._blocks = bytearray(self.k * self._stride)
        for b in range(self.k):
            chunk = payload[b * block_len:min((b + 1) * block_len, len(payload))]
            self._blocks[b * self._stride:b * self._stride + len(chunk)] = chunk

    def encode(self, seq: int) -> bytes:
        out = bytearray(self._stride)
        for b in frame_composition(self.k, self.session_id, seq):
            off = b * self._stride
            for i in range(self._stride):
                out[i] ^= self._blocks[off + i]
        return bytes(out[:self.block_len])
