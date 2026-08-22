"""Reproduziert der Python-Nachbau die vier goldenen Stromhashes aus
tests/fountain.test.ts? Wenn ja, ist die Vektorquelle tauglich."""

M32 = 0xFFFFFFFF

def imul(a, b):                      # Math.imul: int32-Multiplikation
    r = (a * b) & M32
    return r - 0x100000000 if r & 0x80000000 else r

def i32(x):                          # JS  | 0
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x

def u32(x):                          # JS  >>> 0
    return x & M32

def shr(x, n):                       # JS  >>>
    return (x & M32) >> n

def fnv1a(data):
    h = 0x811C9DC5
    for byte in data:
        h ^= byte
        h = u32(imul(h, 0x01000193))
    return u32(h)

def frame_seed(session_id, seq):
    h = i32(imul(session_id + 1, 0x9E3779B1) ^ i32(seq + 0x85EBCA6B))
    h = imul(h ^ shr(h, 13), 0xC2B2AE35)
    return i32(h ^ shr(h, 16))

def splitmix32(seed):
    s = i32(seed)
    def rnd():
        nonlocal s
        s = i32(s + 0x9E3779B9)
        t = s ^ shr(s, 16)
        t = imul(t, 0x21F0AAAD)
        t = i32(t ^ shr(t, 15))
        t = imul(t, 0x735A2D97)
        t = i32(t ^ shr(t, 15))
        return u32(t)
    return rnd

REPAIR_MIN, REPAIR_MAX = 4, 24

def repair_indices(k, session_id, seq):
    rnd = splitmix32(frame_seed(session_id, seq))
    d = min(k, REPAIR_MIN + rnd() % (REPAIR_MAX - REPAIR_MIN + 1))
    seen = {}                        # dict: bewahrt Einfügereihenfolge wie JS Set
    while len(seen) < d:
        seen[rnd() % k] = None
    return list(seen)

def frame_composition(k, session_id, seq):
    pos = seq % (2 * k)
    return [pos] if pos < k else repair_indices(k, session_id, seq)

class LTEncoder:
    def __init__(self, payload, block_len, session_id):
        self.block_len = block_len
        self.session_id = session_id
        self.k = max(1, -(-len(payload) // block_len))
        self.stride = -(-block_len // 4) * 4      # words*4, wie Uint32Array
        self.buf = bytearray(self.k * self.stride)
        for b in range(self.k):
            chunk = payload[b*block_len:min((b+1)*block_len, len(payload))]
            self.buf[b*self.stride:b*self.stride+len(chunk)] = chunk

    def encode(self, seq):
        out = bytearray(self.stride)
        for b in frame_composition(self.k, self.session_id, seq):
            off = b * self.stride
            for i in range(self.stride):
                out[i] ^= self.buf[off + i]
        return bytes(out[:self.block_len])

def test_payload(n):
    return bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(n))

GOLDEN = [
    (1,   64,   1,     "k=1 fnv=0xf6a115c5"),
    (23,  64,   7,     "k=23 fnv=0x4a5d3eaa"),
    (179, 2933, 4242,  "k=179 fnv=0x54f78d05"),
    (716, 1445, 65535, "k=716 fnv=0x75b73b85"),
]

ok = True
for k, block_len, session_id, expected in GOLDEN:
    enc = LTEncoder(test_payload(k * block_len - 7), block_len, session_id)
    stream = bytearray()
    for seq in range(64):
        stream += enc.encode(seq)
    actual = f"k={enc.k} fnv=0x{fnv1a(stream):08x}"
    good = actual == expected
    ok &= good
    print(f"  {actual:24} erwartet {expected:24} {'OK' if good else 'ABWEICHUNG'}")

# Strukturregeln des Karussells (tests/fountain.test.ts:306)
for k in (1, 17, 179, 4096):
    for pos in {0, k >> 1, k - 1}:
        assert frame_composition(k, 9, pos) == [pos]
        assert frame_composition(k, 9, pos + 6 * 2 * k) == [pos]
    for seq in (k, k + 1, 2*k - 1):
        idx = frame_composition(k, 9, seq)
        assert min(k, 4) <= len(idx) <= min(k, 24)
        assert len(set(idx)) == len(idx)
        assert all(0 <= b < k for b in idx)
print("  Strukturregeln des Karussells: OK")
print("\nERGEBNIS:", "Python reproduziert den Strom bit-genau" if ok else "ABWEICHUNG")
