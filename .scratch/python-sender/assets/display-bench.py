"""Wie viele frisch erzeugte QR-Frames bekommt ein Toolkit pro Sekunde auf den Schirm?

Gemessen wird, was der Sender wirklich tut: jeder Frame ist ein NEUES Bild,
das aus rohen Bytes ins Fenster muss. Kein Cache, kein Wiederverwenden.
"""
import sys, time
import segno
from PIL import Image

QUIET = 4
POOL = 8
DURATION = 20.0

def build_pool(px):
    """Echte v40-QR-Frames, auf px hochskaliert, als (rgb_bytes, ppm_bytes)."""
    out = []
    for s in range(POOL):
        data = bytes(((i * 37 + 11 + s * 101) & 0xFF) for i in range(2953))
        qr = segno.make(data, mode="byte", error="L", version=40, mask=4, boost_error=False)
        rows = [[0 if m else 255 for m in row] for row in qr.matrix]
        n = len(rows)
        img = Image.new("L", (n + 2*QUIET, n + 2*QUIET), 255)
        img.paste(Image.frombytes("L", (n, n), bytes(v for r in rows for v in r)), (QUIET, QUIET))
        img = img.resize((px, px), Image.NEAREST).convert("RGB")
        rgb = img.tobytes()
        ppm = b"P6\n%d %d\n255\n" % (px, px) + rgb
        out.append((rgb, ppm))
    return out

def bench_tk(pool, px):
    import tkinter as tk
    root = tk.Tk(); root.title(f"tk {px}px"); root.geometry(f"{px}x{px}")
    canvas = tk.Canvas(root, width=px, height=px, highlightthickness=0, bg="white")
    canvas.pack()
    photo = tk.PhotoImage(width=px, height=px)
    item = canvas.create_image(0, 0, anchor="nw", image=photo)
    root.update()
    frames = 0; t0 = time.perf_counter()
    while time.perf_counter() - t0 < DURATION:
        _, ppm = pool[frames % POOL]
        photo.configure(data=ppm, format="ppm")
        canvas.itemconfig(item, image=photo)
        root.update()
        frames += 1
    dt = time.perf_counter() - t0
    root.destroy()
    return frames / dt

def bench_pygame(pool, px):
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((px, px))
    pygame.display.set_caption(f"pygame {px}px")
    frames = 0; t0 = time.perf_counter()
    while time.perf_counter() - t0 < DURATION:
        rgb, _ = pool[frames % POOL]
        surf = pygame.image.frombuffer(rgb, (px, px), "RGB")
        screen.blit(surf, (0, 0))
        pygame.display.flip()
        pygame.event.pump()
        frames += 1
    dt = time.perf_counter() - t0
    pygame.quit()
    return frames / dt

backend = sys.argv[1]
for px in (740, 1480):
    pool = build_pool(px)
    fps = (bench_tk if backend == "tk" else bench_pygame)(pool, px)
    label = "1 Code @4×" if px == 740 else "4er-Grid @4× / 1 Code @8×"
    print(f"{backend:7} {px}×{px} px  ({label:24})  {fps:7.1f} fps")
