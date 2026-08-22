"""Cross-language round trip: the TypeScript ENCODER produces frames, this
Python receiver rebuilds the file.

The Python-to-Python round trip in test_conformance proves the two Python
halves agree. This proves the Python receiver agrees with the *TypeScript*
sender — the encounter that matters, since a phone or the web app runs that
encoder.

Needs node and `npm install` in the repo root. A development dependency;
running the receiver never needs node.

    uv run python tests/ts_roundtrip.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
REPO = HERE.parent.parent

from decimen import protocol as p
from decimen.fountain import LTDecoder


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        gen = subprocess.run(
            ["node", "--import", "tsx", str(HERE / "ts-encode.mjs"),
             str(td / "frames.bin"), str(td / "meta.json")],
            cwd=REPO, capture_output=True, text=True)
        if gen.returncode != 0:
            print(gen.stdout); print(gen.stderr, file=sys.stderr)
            return 1
        meta = json.loads((td / "meta.json").read_text())
        dump = (td / "frames.bin").read_bytes()

    flen = meta["frameLen"]
    print(f"  TypeScript-Encoder: k={meta['k']}, {meta['sent']} Frames gesendet, "
          f"{meta['dropped']} verworfen")

    dec = None
    parsed = rejected = 0
    for off in range(0, len(dump) - flen + 1, flen):
        got = p.parse_frame(dump[off:off + flen])
        if got is None:
            rejected += 1
            continue
        parsed += 1
        h, block = got
        if dec is None:
            dec = LTDecoder(h.k, h.block_len, h.session_id, h.total_len)
        dec.add_frame(h.seq, block)
        if dec.is_complete:
            break

    recovered = dec.assemble() if dec and dec.is_complete else b""
    container_ok = dec is not None and dec.is_complete
    # The recovered bytes are the CONTAINER; unpack it to get the file.
    ok = True
    file = None
    if container_ok:
        file = p.unpack_file(recovered)

    for label, cond in (
        ("jeder Frame akzeptiert", rejected == 0),
        ("Container vollstaendig", container_ok),
        ("Datei entpackt", file is not None),
        ("Name ueberlebt", file and file.name == "report.bin"),
        ("Groesse stimmt", file and len(file.data) == meta["size"]),
        ("SHA-256 stimmt", file and hashlib.sha256(file.data).hexdigest() == meta["sha256"]),
        ("SHA-256 verifiziert", file and p.verify_file(file)),
    ):
        print(f"  {'ok  ' if cond else 'FEHL'} {label}")
        ok &= bool(cond)

    print("\n" + ("Der Python-Empfaenger liest, was TypeScript sendet."
                  if ok else "ABWEICHUNG"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
