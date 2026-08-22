# Golden vectors

Conformance data for the Decimen wire format. A non-TypeScript client — a
native iOS or Android receiver — is correct when it agrees with everything on
this page.

These vectors live in executable form in `tests/protocol.test.ts` and
`tests/transfer.test.ts`. **A diff to any byte here is a wire-format change and
gets reviewed as one** (see [versioning](versioning.md)).

## Canonical frame

Wire v3, 22-byte header, 6-byte block, all fields distinct so a swapped offset
cannot pass by accident:

| field | offset | value |
|---|---|---|
| magic0 | 0 | `0xD1` |
| magic1 | 1 | `0xC3` |
| version | 2 | `3` |
| flags | 3 | `0x00` |
| sessionId | 4 | `0xBEEF` |
| seq | 6 | `0x01020304` |
| k | 10 | `0x0111` |
| blockLen | 12 | `6` |
| totalLen | 14 | `0x00FEDCBA` |
| payloadFnv | 18 | `0x89ABCDEF` |
| block | 22 | `01 02 03 04 05 06` |

```
d1 c3 03 00 ef be 04 03 02 01 11 01 06 00 ba dc fe 00 ef cd ab 89 01 02 03 04 05 06
```

Every multi-byte field is **little-endian**. Total length is exactly
`HEADER_LEN + blockLen`; a frame whose length disagrees is `malformed`.

## Classification vectors

Only the first four bytes decide these, so they are shown alone. Each row is a
mutation of a well-formed frame. "speaks" means the receiver must show the
user a message; silent means it must not.

| case | bytes 0–3 | verdict | speaks |
|---|---|---|---|
| well-formed | `d1 c3 03 00` | `ok` | — |
| v1 sender | `d1 0c 03 00` | `older-sender` (v1) | yes |
| v2 sender | `d1 0d 03 00` | `older-sender` (v2) | yes |
| magic1 anything else | `d1 42 03 00` | `foreign` | silent |
| magic0 wrong | `d2 c3 03 00` | `foreign` | silent |
| newer version | `d1 c3 04 00` | `newer-sender` (v4) | yes |
| older version | `d1 c3 02 00` | `older-sender` (v2) | yes |
| version 0 | `d1 c3 00 00` | `malformed` | silent |
| unknown critical flag | `d1 c3 03 01` | `unsupported-flags` | yes |
| unknown ignorable flag | `d1 c3 03 10` | `ok` — parse it | silent |

Two properties a client must not "optimise" away:

1. **A lone `0xD1` never produces version advice.** Both magic bytes must match
   before any version is named. Gating on one byte gives ~1 binary QR payload
   in 256 a false "update your device", and that message latches on screen.
2. **Unknown ignorable flags (`0xF0`) decode normally** and ride through to the
   parsed header. Rejecting them makes the ignorable half of the byte a lie.

## Self-consistency

Beyond version and flags, a frame is `malformed` — and silent — when:

- total length ≠ `22 + blockLen`
- `k`, `blockLen`, or `totalLen` is zero (`k = 0` divides by zero downstream)
- fewer than 23 bytes (a header with no block)

## Stream identity

Frames belong to the same transfer when `sessionId`, `k`, `blockLen`,
`totalLen`, `payloadFnv`, and **the critical half of `flags`** all match. `seq`
is the one field that varies within a stream.

Ignorable flag bits (`0xF0`) are excluded: a mid-stream flip must not reset the
decoder and discard recovered blocks.

The identity must not be a naive concatenation — `{k: 1, blockLen: 23}` and
`{k: 12, blockLen: 3}` are different streams and must not collide.

## Fountain carousel

Which blocks a frame carries is derived from `seq` alone — sender and receiver
never compare notes, so a second implementation that disagrees here produces a
stream that simply never completes.

`cycleLength(k)` is `2 * k`. For `pos = seq % cycleLength(k)`:

- `pos < k` — **systematic**: the frame carries block `pos` alone.
- otherwise — **repair**: degree `min(k, 4 + rnd() % 21)`, then that many
  distinct `rnd() % k`, drawn in order from a splitmix32 stream seeded with the
  **absolute** `seq`, so every cycle's repair frames differ.

Both generators are 32-bit integer arithmetic throughout — no floating point,
nothing an implementation can round differently:

```
frameSeed(sessionId, seq):
  h = int32(imul(sessionId + 1, 0x9e3779b1) ^ int32(seq + 0x85ebca6b))
  h = imul(h ^ (h >>> 13), 0xc2b2ae35)
  return int32(h ^ (h >>> 16))

splitmix32(seed):                     # successive calls advance s
  s = int32(s + 0x9e3779b9)
  t = imul(s ^ (s >>> 16), 0x21f0aaad)
  t = imul(t ^ (t >>> 15), 0x735a2d97)
  return uint32(t ^ (t >>> 15))
```

`imul` is a 32-bit multiply keeping the low 32 bits; `>>>` shifts the unsigned
32-bit pattern.

Blocks are laid out padded to a multiple of four bytes — `stride = ceil(blockLen
/ 4) * 4` — the payload copied in at `b * stride` and the tail block
zero-filled. A frame XORs its blocks over the full stride and emits the first
`blockLen` bytes. **Every frame is exactly `blockLen` bytes**, including the one
covering the short tail block.

### Stream fingerprints

Each row encodes `seq` 0..63, concatenates the frames, and takes FNV-1a over
the result. The payload is `payload[i] = (i * 37 + (i >> 8) * 11) & 0xff` of
length `k * blockLen - 7`.

| k | blockLen | sessionId | fnv1a of 64 frames |
|---|---|---|---|
| 1 | 64 | 1 | `0xf6a115c5` |
| 23 | 64 | 7 | `0x4a5d3eaa` |
| 179 | 2933 | 4242 | `0x54f78d05` |
| 716 | 1445 | 65535 | `0x75b73b85` |

One hash covers `frameSeed`, `splitmix32`, the repair draw, the block padding
and the XOR order together. The `k = 23` row is the only one whose 64 frames
outrun the sweep and reach repair frames; the others pin the systematic half.

An earlier robust-soliton stream (`dlog`, `solitonCdf`, `frameIndices`) is
still pinned in `tests/fountain.test.ts` in case a future format wants it back.
**It has not been emitted since wire v2** — a second implementation does not
need it.

## Round-trip conformance

`tests/transfer.test.ts` is the end-to-end harness, and the only test that
catches a header field read from the wrong offset — per-layer tests pass
happily when `packFrame` and `parseFrame` agree with each other but not with
the wire.

It drives 300 KB of incompressible data through container → fountain → framed
wire → back, over a deterministic ~15% frame loss, and asserts:

- every frame is exactly the frame budget (2953 bytes) in size
- the receiver learns everything from the frames alone — no handshake, no
  shared state with the encoder
- the recovered container matches `payloadFnv`
- SHA-256 verifies, and every byte of the original file survives
- overhead stays under 1.3× the source block count

A native decoder is correct when it recovers that file from those frames.
