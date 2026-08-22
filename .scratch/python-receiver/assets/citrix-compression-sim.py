"""Wie viel H.264-Kompression überlebt ein QR-Code?

Citrix' Nachschärfen greift nur bei stehendem Bild — ein Karussell bewegt sich
immer. Also wird ein echter, wechselnder Frame-Strom durch H.264 gejagt (nicht
ein Standbild), Frame für Frame wieder herausgezogen und dekodiert. Gemessen
wird die Dekodier-Erfolgsrate je Sender-Einstellung.

H.264 aus ffmpeg IST NICHT Citrix HDX — die Richtung ist verlässlich, die
Schwellen sind Näherungen. Der echte Beleg ist ein Lauf über echtes Citrix.
"""
import subprocess, sys, tempfile, pathlib
sys.path.insert(0, "/Users/sh/Git/decimen-optical-transfer/python-sender")
import numpy as np, zxingcpp
from decimen import protocol as p, qr as q
from decimen.fountain import LTEncoder
from decimen.frame_capacity import block_length

FRAMES = 48                     # ein knapper Karussell-Ausschnitt
QUIET_TILE = (255, 255, 255)


def render_stream(frame_bytes, ecc, codes, module_scale):
    """Echte, aufeinanderfolgende Sender-Frames als RGB-Bilder gleicher Größe."""
    payload = bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(200 * 1024))
    block_len = block_length(frame_bytes)
    enc = LTEncoder(payload, block_len, 4242)
    header = dict(session_id=4242, seq=0, k=enc.k, block_len=block_len,
                  total_len=len(payload), payload_fnv=p.fnv1a(payload), flags=0)
    version = None
    imgs, sources = [], []
    seq = 0
    for _ in range(FRAMES):
        mats = []
        srcs = []
        for _c in range(codes):
            wire = p.pack_frame(p.FrameHeader(**{**header, "seq": seq}), enc.encode(seq))
            code = q.create_frame_qr(wire, ecc, version)
            version = code.version
            mats.append(list(code.matrix))
            srcs.append(wire)
            seq += 1
        w, h, rgb = q.rasterize_qr_grid(mats, module_scale)
        arr = np.frombuffer(rgb, np.uint8).reshape(h, w, 3)
        # yuv420p verlangt gerade Kantenlaengen; sonst verschiebt ffmpeg das
        # Bild und die Dekodierung faellt auf 0% — ein Testartefakt, keine
        # Kompression. Weiss auffuellen, wie eine breitere Ruhezone.
        ph, pw = h + (h & 1), w + (w & 1)
        if (ph, pw) != (h, w):
            pad = np.full((ph, pw, 3), 255, np.uint8)
            pad[:h, :w] = arr
            arr = pad
        imgs.append(arr)
        sources.append(set(srcs))
    return imgs, sources, version


def h264_roundtrip(imgs, crf, scale_to=None):
    """Strom durch libx264 und zurück. scale_to interpoliert (krumme Fenstergröße)."""
    h, w = imgs[0].shape[:2]
    with tempfile.TemporaryDirectory() as td:
        raw = pathlib.Path(td) / "in.rgb"
        raw.write_bytes(b"".join(im.tobytes() for im in imgs))
        vf = f"scale={scale_to}:flags=bilinear,scale={w}:{h}:flags=bilinear" if scale_to else "null"
        enc = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", "20", "-i", str(raw),
             "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-f", "h264", str(pathlib.Path(td) / "v.h264")],
            capture_output=True)
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(pathlib.Path(td) / "v.h264"),
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True)
        buf = np.frombuffer(out.stdout, np.uint8)
        n = len(buf) // (w * h * 3)
        return buf[:n*w*h*3].reshape(n, h, w, 3)


def decode_rate(frames, sources, codes):
    got, total = 0, 0
    for i, fr in enumerate(frames):
        if i >= len(sources):
            break
        total += len(sources[i])
        res = zxingcpp.read_barcodes(np.ascontiguousarray(fr),
                                     formats=zxingcpp.BarcodeFormat.QRCode)
        found = {bytes(r.bytes) for r in res}
        got += len(found & sources[i])
    return got / max(1, total)


CASES = [
    # (Bytes/Frame, ECC, Codes, Modulskala) — Skala wie beim Sender ~scharf
    (2953, "L", 1, 4), (1465, "L", 1, 4), (1000, "L", 1, 5), (500, "L", 1, 6),
    (1000, "M", 1, 5), (1000, "Q", 1, 5), (1000, "H", 1, 5),
    (1000, "L", 4, 4),
]
print(f"{'Bytes':>5} {'ECC':>3} {'grid':>4} {'ver':>4}  " +
      "  ".join(f"CRF{c}" for c in (28, 36, 42, 46)))
for fb, ecc, codes, sc in CASES:
    imgs, sources, ver = render_stream(fb, ecc, codes, sc)
    row = f"{fb:>5} {ecc:>3} {codes:>4} v{ver:<3}"
    for crf in (28, 36, 42, 46):
        rate = decode_rate(h264_roundtrip(imgs, crf), sources, codes)
        row += f"  {rate*100:4.0f}%"
    print(row)
