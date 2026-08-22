"""The fountain decoder — the receive half of shared/fountain.ts.

frame_seed, splitmix32 and frame_composition are byte-identical to the sender's
copy (see the map's standalone note). They must be: the decoder derives each
frame's block set the same way the sender did, and never compares notes with
it. What is new here is LTDecoder — the peeling cascade the sender does not
have.

Not ported, same as the sender: dlog/solitonCdf/frameIndices (the v1 stream,
unemitted since wire v2).
"""

from __future__ import annotations

from .protocol import _i32, _imul, _shr, splitmix32

REPAIR_DEGREE_MIN = 4
REPAIR_DEGREE_MAX = 24


def cycle_length(k: int) -> int:
    return 2 * k


def frame_seed(session_id: int, seq: int) -> int:
    h = _i32(_imul(session_id + 1, 0x9E3779B1) ^ _i32(seq + 0x85EBCA6B))
    h = _imul(h ^ _shr(h, 13), 0xC2B2AE35)
    return _i32(h ^ _shr(h, 16))


def repair_indices(k: int, session_id: int, seq: int) -> list[int]:
    rnd = splitmix32(frame_seed(session_id, seq))
    d = min(k, REPAIR_DEGREE_MIN + rnd() % (REPAIR_DEGREE_MAX - REPAIR_DEGREE_MIN + 1))
    seen: dict[int, None] = {}
    while len(seen) < d:
        seen[rnd() % k] = None
    return list(seen)


def frame_composition(k: int, session_id: int, seq: int) -> list[int]:
    pos = seq % cycle_length(k)
    return [pos] if pos < k else repair_indices(k, session_id, seq)


def _xor_into(dst: bytearray, src: bytes) -> None:
    for i in range(len(dst)):
        dst[i] ^= src[i]


class LTDecoder:
    """Fixed k/blockLen/sessionId/totalLen — a frame from any other stream must
    never be added (it would corrupt the peel silently). The caller checks
    stream identity before add_frame, not inside it.
    """

    def __init__(self, k: int, block_len: int, session_id: int, total_len: int):
        self.k = k
        self.block_len = block_len
        self.session_id = session_id
        self.total_len = total_len
        self._solved: list[bytes | None] = [None] * k
        self._by_block: dict[int, set] = {}   # block -> set of pending frames
        self._seen: set[int] = set()
        self.solved_count = 0
        self.frames_new = 0
        self.frames_dup = 0
        # Frames with a new seq that carried nothing new — every block already
        # solved. A progress bar fed raw frames_new inflates by this fraction on
        # a lossy multi-code run (measured 96% shown vs ~50% real at 30% catch).
        self.frames_redundant = 0

    @property
    def is_complete(self) -> bool:
        return self.solved_count >= self.k

    def add_frame(self, seq: int, block: bytes) -> None:
        if seq in self._seen:
            self.frames_dup += 1
            return
        self._seen.add(seq)
        self.frames_new += 1
        if self.is_complete:
            return

        idx = set(frame_composition(self.k, self.session_id, seq))
        words = bytearray(self.block_len)
        words[:len(block[:self.block_len])] = block[:self.block_len]
        for b in list(idx):
            s = self._solved[b]
            if s is not None:
                _xor_into(words, s)
                idx.discard(b)
        if not idx:
            self.frames_redundant += 1
            return
        if len(idx) == 1:
            self._resolve(next(iter(idx)), bytes(words))
            return
        pf = _Pending(idx, words)
        for b in idx:
            self._by_block.setdefault(b, set()).add(pf)

    def _resolve(self, b0: int, w0: bytes) -> None:
        """Peel: solve a block, reduce every frame waiting on it, repeat.

        Back-loads by design — blocks solved hockey-stick near the end while
        frame arrival is linear. Progress UX shows frames collected, not blocks
        solved, or the bar looks stalled then teleports.
        """
        queue: list[tuple[int, bytes]] = [(b0, w0)]
        while queue:
            b, w = queue.pop()
            if self._solved[b] is not None:
                continue
            self._solved[b] = w
            self.solved_count += 1
            waiting = self._by_block.pop(b, None)
            if not waiting:
                continue
            for pf in waiting:
                _xor_into(pf.words, w)
                pf.idx.discard(b)
                if len(pf.idx) == 1:
                    r = next(iter(pf.idx))
                    got = self._by_block.get(r)
                    if got:
                        got.discard(pf)
                    if self._solved[r] is None:
                        queue.append((r, bytes(pf.words)))

    def assemble(self) -> bytes | None:
        if not self.is_complete:
            return None
        out = bytearray(self.total_len)
        for b in range(self.k):
            start = b * self.block_len
            length = min(self.block_len, self.total_len - start)
            if length > 0:
                out[start:start + length] = self._solved[b][:length]
        return bytes(out)


class _Pending:
    __slots__ = ("idx", "words")

    def __init__(self, idx: set, words: bytearray):
        self.idx = idx
        self.words = words
