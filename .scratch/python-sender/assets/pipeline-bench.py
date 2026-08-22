"""Die ganze Kette pro Frame: segno kodieren -> rastern -> anzeigen."""
import time
import segno, pygame
from PIL import Image

QUIET, DURATION = 4, 15.0
HEADER = 22

def frame(seq, n=2953):
    return bytes(((i * 37 + 11 + seq * 101) & 0xFF) for i in range(n))

def raster(qr, px):
    n = qr.symbol_size(border=0)[0]
    src = Image.frombytes("L", (n, n), bytes(0 if m else 255 for row in qr.matrix for m in row))
    img = Image.new("L", (n + 2*QUIET, n + 2*QUIET), 255)
    img.paste(src, (QUIET, QUIET))
    return img.resize((px, px), Image.NEAREST).convert("RGB").tobytes()

def run(codes, px_total):
    px = px_total // (2 if codes == 4 else 1)
    pygame.init()
    screen = pygame.display.set_mode((px_total, px_total))
    pygame.display.set_caption(f"{codes} Code(s) @ {px_total}px")
    seq = 0; frames = 0
    t_enc = t_ras = t_disp = 0.0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < DURATION:
        for i in range(codes):
            a = time.perf_counter()
            qr = segno.make(frame(seq), mode="byte", error="L", version=40, mask=4, boost_error=False)
            b = time.perf_counter()
            rgb = raster(qr, px)
            c = time.perf_counter()
            surf = pygame.image.frombuffer(rgb, (px, px), "RGB")
            screen.blit(surf, ((i % 2) * px, (i // 2) * px))
            d = time.perf_counter()
            t_enc += b - a; t_ras += c - b; t_disp += d - c
            seq += 1
        pygame.display.flip(); pygame.event.pump()
        frames += 1
    dt = time.perf_counter() - t0
    pygame.quit()
    fps = frames / dt
    goodput = fps * codes * (2953 - HEADER) / 1024 / 1.15
    total = t_enc + t_ras + t_disp
    print(f"{codes} Code(s) @ {px_total}px: {fps:5.1f} fps  ->  {goodput:6.1f} KB/s Nutzdurchsatz")
    print(f"        Zeitanteile: kodieren {t_enc/total*100:4.1f}%  rastern {t_ras/total*100:4.1f}%  anzeigen {t_disp/total*100:4.1f}%")

run(1, 740)
run(4, 1480)
