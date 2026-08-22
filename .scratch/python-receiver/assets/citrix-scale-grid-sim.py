"""Die realistischen Citrix-Killer: Interpolation auf krumme Größe, und
Grid-Zerfall (mehr Codes = kleinere Module bei fester Aufnahmefläche)."""
import subprocess, sys, tempfile, pathlib
sys.path.insert(0, "/Users/sh/Git/decimen-optical-transfer/python-sender")
import numpy as np, zxingcpp
from decimen import protocol as p, qr as q
from decimen.fountain import LTEncoder
from decimen.frame_capacity import block_length

FRAMES = 32


def stream(frame_bytes, ecc, codes, total_px):
    """Grid so rastern, dass die GESAMTE Fläche ~total_px breit ist — wie ein
    fester Aufnahmebereich, den man auf mehr Codes aufteilt."""
    payload = bytes(((i * 37 + (i >> 8) * 11) & 0xFF) for i in range(200 * 1024))
    bl = block_length(frame_bytes)
    enc = LTEncoder(payload, bl, 4242)
    hdr = dict(session_id=4242, seq=0, k=enc.k, block_len=bl,
               total_len=len(payload), payload_fnv=p.fnv1a(payload), flags=0)
    cols = {1:1, 2:1, 4:2, 6:2}[codes]
    ver = None
    # erst Version bestimmen
    probe = q.create_frame_qr(p.pack_frame(p.FrameHeader(**hdr), enc.encode(0)), ecc, None)
    ver = probe.version
    cell_mods = (ver*4+17) + 8
    scale = max(1, total_px // (cell_mods * cols))
    imgs, srcs = [], []
    seq = 0
    for _ in range(FRAMES):
        mats, s = [], []
        for _c in range(codes):
            wire = p.pack_frame(p.FrameHeader(**{**hdr, "seq": seq}), enc.encode(seq))
            mats.append(list(q.create_frame_qr(wire, ecc, ver).matrix)); s.append(wire); seq += 1
        w, h, rgb = q.rasterize_qr_grid(mats, scale)
        a = np.frombuffer(rgb, np.uint8).reshape(h, w, 3)
        ph, pw = h+(h&1), w+(w&1)
        if (ph,pw)!=(h,w):
            pad = np.full((ph,pw,3),255,np.uint8); pad[:h,:w]=a; a=pad
        imgs.append(a); srcs.append(set(s))
    return imgs, srcs, ver, scale


def rt(imgs, crf, interp_to=None):
    h,w = imgs[0].shape[:2]
    with tempfile.TemporaryDirectory() as td:
        raw = pathlib.Path(td)/"i.rgb"; raw.write_bytes(b"".join(im.tobytes() for im in imgs))
        # Interpolation auf eine krumme Zwischengröße und zurück = Citrix, das
        # die Sitzung auf eine andere Fenstergröße skaliert.
        if interp_to:
            iw = int(w*interp_to) | 1        # ungerade Zwischengröße erzwingen
            vf = f"scale={iw}:-2:flags=bilinear,scale={w}:{h}:flags=bilinear,format=yuv420p"
        else:
            vf = "format=yuv420p"
        subprocess.run(["ffmpeg","-v","error","-f","rawvideo","-pix_fmt","rgb24",
            "-s",f"{w}x{h}","-r","20","-i",str(raw),"-vf",vf,"-c:v","libx264",
            "-preset","fast","-crf",str(crf),"-f","h264",str(pathlib.Path(td)/"v.h264")],
            capture_output=True)
        out = subprocess.run(["ffmpeg","-v","error","-i",str(pathlib.Path(td)/"v.h264"),
            "-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True)
        buf=np.frombuffer(out.stdout,np.uint8); n=len(buf)//(w*h*3)
        return buf[:n*w*h*3].reshape(n,h,w,3)


def rate(frames, srcs):
    got=tot=0
    for i,fr in enumerate(frames):
        if i>=len(srcs): break
        tot+=len(srcs[i])
        res=zxingcpp.read_barcodes(np.ascontiguousarray(fr),formats=zxingcpp.BarcodeFormat.QRCode)
        got+=len({bytes(r.bytes) for r in res} & srcs[i])
    return got/max(1,tot)

print("Harte Bedingung: CRF42 + Downscale 0.6x (starke Sitzungsverkleinerung),")
print("feste 740px-Fläche. Modul-px je Code ist der entscheidende Faktor.")
print(f"{'Bytes':>5} {'ECC':>3} {'grid':>4} {'ver':>4} {'px/mod':>6}  {'CRF38':>6} {'CRF42+0.6x':>11} {'CRF46+0.5x':>11}")
for fb, ecc, codes in [(500,"L",1),(1000,"L",1),(1000,"H",1),(1465,"L",1),
                       (2953,"L",1),(500,"L",4),(1000,"L",4),(1000,"H",4),(500,"H",6)]:
    imgs,srcs,ver,sc = stream(fb,ecc,codes,740)
    a = rate(rt(imgs,38),srcs)
    b = rate(rt(imgs,42,0.6),srcs)
    c = rate(rt(imgs,46,0.5),srcs)
    print(f"{fb:>5} {ecc:>3} {codes:>4} v{ver:<3} {sc:>5}px  {a*100:5.0f}% {b*100:10.0f}% {c*100:10.0f}%")
