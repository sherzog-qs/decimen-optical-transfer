"""Point a phone at this.

The one thing no automated test can do: prove that a real camera running
decimen.app decodes a stream Python produced. Every other check in this folder
holds Python to constants or to the TypeScript decoder; this one closes the
loop through actual light.

Throwaway on purpose — no settings, no file picker, no spec display. That is
the sender's job, not this script's.

    uv run python tests/field_check.py                 # a text snippet
    uv run python tests/field_check.py report.pdf      # a file
    uv run python tests/field_check.py --seconds 5     # stop by itself

Open https://decimen.app/receive/ on the phone and hold it up.
"""

from __future__ import annotations

import argparse
import mimetypes
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from decimen import protocol as p
from decimen import qr as q
from decimen.fountain import LTEncoder
from decimen.frame_capacity import block_length, fits_in_one_stream

SNIPPET = (
    "Sent from Python over light. If you can read this, the port is wire-"
    "compatible with decimen.app: same fountain carousel, same frame header, "
    "same container, same SHA-256."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", type=pathlib.Path)
    ap.add_argument("--fps", type=float, default=20.0)
    # Deliberately the easiest settings in the sender's lists, not the fastest:
    # this script exists to answer "does a phone see it at all". 500 bytes puts
    # the snippet in a version-15 code instead of a version-27 one, and scale 6
    # makes it a big target. Raise both once it works.
    ap.add_argument("--frame-bytes", type=int, default=500)
    ap.add_argument("--ecc", default="L", choices=("L", "M", "Q", "H"))
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = until closed")
    args = ap.parse_args()

    if args.file:
        data = args.file.read_bytes()
        media = mimetypes.guess_type(args.file.name)[0] or "application/octet-stream"
        packed = p.pack_file(args.file.name, media, data)
    else:
        packed = p.pack_snippet(SNIPPET)

    if not fits_in_one_stream(len(packed.container), args.frame_bytes):
        print("payload needs a larger --frame-bytes", file=sys.stderr)
        return 1

    block_len = block_length(args.frame_bytes)
    session_id = random.randint(1, 0xFFFF)      # random per sender start
    encoder = LTEncoder(packed.container, block_len, session_id)
    header = p.FrameHeader(session_id=session_id, seq=0, k=encoder.k,
                           block_len=block_len, total_len=len(packed.container),
                           payload_fnv=p.fnv1a(packed.container), flags=0)

    print(f"session {session_id}  k={encoder.k}  blockLen={block_len}  "
          f"{packed.compression}  {packed.original_size} B")
    print(f"streaming at {args.fps} fps — point a phone at it")

    import pygame
    pygame.init()
    screen = None
    version = None                                # locked by the first frame
    seq, shown, t0 = 0, 0, time.perf_counter()
    running = True
    while running:
        frame = p.pack_frame(p.FrameHeader(**{**header.__dict__, "seq": seq}),
                             encoder.encode(seq))
        code = q.create_frame_qr(frame, args.ecc, version)
        if version is None:
            version = code.version
            print(f"QR version locked to {version}")
        width, height, rgb = q.rasterize_qr_grid([list(code.matrix)], args.scale)
        if screen is None:
            screen = pygame.display.set_mode((width, height))
            pygame.display.set_caption("decimen — python sender (field check)")
        screen.blit(pygame.image.frombuffer(rgb, (width, height), "RGB"), (0, 0))
        pygame.display.flip()
        seq += 1
        shown += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                running = False
        elapsed = time.perf_counter() - t0
        if args.seconds and elapsed >= args.seconds:
            running = False
        target = t0 + shown / args.fps
        if (wait := target - time.perf_counter()) > 0:
            time.sleep(wait)

    pygame.quit()
    print(f"{shown} frames in {time.perf_counter() - t0:.1f}s "
          f"({shown / (time.perf_counter() - t0):.1f} fps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
