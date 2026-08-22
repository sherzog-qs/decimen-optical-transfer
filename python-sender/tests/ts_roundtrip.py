"""Round-trip against the TypeScript decoder — the one test where the two
implementations actually meet.

Every other check in this folder holds Python to recorded constants. Those
catch drift within one implementation; only this one catches the case where
Python and TypeScript are each self-consistent and disagree with each other.

Needs node and `npm install` in the repo root. That is a development
dependency, not a runtime one: running the sender never needs node.

    uv run python tests/ts_roundtrip.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from decimen import protocol as p
from decimen.fountain import LTEncoder
from decimen.frame_capacity import block_length

REPO = pathlib.Path(__file__).resolve().parents[2]
FRAME_BYTES = 2953
DROP_PERCENT = 15          # deterministic, like tests/transfer.test.ts


def incompressible(n: int) -> bytes:
    out, seed = b"", b"decimen-roundtrip"
    while len(out) < n:
        seed = hashlib.sha256(seed).digest()
        out += seed
    return out[:n]


def main() -> int:
    original = incompressible(300 * 1024)
    packed = p.pack_file("report.bin", "application/octet-stream", original)
    assert packed.compression == "none", "incompressible payload must not gzip"

    block_len = block_length(FRAME_BYTES)
    encoder = LTEncoder(packed.container, block_len, session_id=4242)
    header = p.FrameHeader(
        session_id=4242, seq=0, k=encoder.k, block_len=block_len,
        total_len=len(packed.container), payload_fnv=p.fnv1a(packed.container),
        flags=0,
    )

    frames, dropped = bytearray(), 0
    for seq in range(encoder.k * 3):
        if (seq * 7919) % 100 < DROP_PERCENT:      # the camera missed this one
            dropped += 1
            continue
        frames += p.pack_frame(
            p.FrameHeader(**{**header.__dict__, "seq": seq}), encoder.encode(seq)
        )

    sent = len(frames) // FRAME_BYTES
    print(f"  Container {len(packed.container)} B, k={encoder.k}, blockLen={block_len}")
    print(f"  {sent} Frames gesendet, {dropped} verworfen ({DROP_PERCENT}% Verlust)")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "frames.bin").write_bytes(frames)
        (tmp / "meta.json").write_text(json.dumps({"frameLen": FRAME_BYTES}))
        proc = subprocess.run(
            ["node", "--import", "tsx",
             str(pathlib.Path(__file__).with_name("ts-roundtrip.mjs")),
             str(tmp / "frames.bin"), str(tmp / "meta.json"), str(tmp / "out.bin")],
            cwd=REPO, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return 1
        report = json.loads(proc.stdout.strip().splitlines()[-1])
        recovered = (tmp / "out.bin").read_bytes() if report.get("complete") else b""

    print(f"  TypeScript-Decoder: {report['parsed']} Frames akzeptiert, "
          f"{report['rejected']} abgelehnt")

    ok = True
    for label, condition in (
        ("jeder Frame wurde akzeptiert", report["rejected"] == 0),
        ("die Datei wurde vollstaendig", report["complete"]),
        ("Dateiname ueberlebt", report.get("name") == "report.bin"),
        ("Medientyp ueberlebt", report.get("type") == "application/octet-stream"),
        ("Laenge stimmt", report.get("bytes") == len(original)),
        ("Kompression als none gemeldet", report.get("compression") == "none"),
        ("jedes Byte identisch", recovered == original),
        ("SHA-256 stimmt", hashlib.sha256(recovered).digest()
                            == hashlib.sha256(original).digest()),
        ("Overhead unter 1.3x", report["parsed"] <= encoder.k * 1.3),
    ):
        print(f"  {'ok  ' if condition else 'FEHL'} {label}")
        ok &= bool(condition)

    print("\n" + ("Der TypeScript-Empfaenger liest, was Python sendet."
                  if ok else "ABWEICHUNG"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
