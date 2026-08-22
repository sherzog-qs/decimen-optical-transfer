"""Prototyp ausprobieren: Bereich aufziehen, dann wird sofort gezeigt, was in
dem Bereich gegriffen wird (als Fenster).

    uv run python .scratch/python-receiver/assets/try_select.py

Bereich mit der Maus aufziehen (wie Cmd-Shift-4), Esc bricht ab. Danach öffnet
sich ein Fenster mit genau dem gegriffenen Ausschnitt — so siehst du, ob die
Auswahl das trifft, was du meintest. Fenster schließen beendet.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parents[3] / "python-sender"))

from select_region import select_region
from capture import ScreenRegion


def main():
    sel = select_region()
    if sel is None:
        print("abgebrochen")
        return
    x, y, w, h = sel
    print(f"Bereich in Punkten: x={x} y={y} w={w} h={h}")
    arr = ScreenRegion(x, y, w, h).grab()
    print(f"gegriffen: {arr.shape[1]}x{arr.shape[0]} physische Pixel")

    import pygame, numpy as np
    pygame.init()
    ph, pw = arr.shape[:2]
    scale = min(1.0, 900 / max(pw, ph))
    disp = (int(pw * scale), int(ph * scale))
    scr = pygame.display.set_mode(disp)
    pygame.display.set_caption("So wird der Bereich gegriffen — Fenster schliessen zum Beenden")
    surf = pygame.image.frombuffer(np.ascontiguousarray(arr).tobytes(), (pw, ph), "RGB")
    scr.blit(pygame.transform.smoothscale(surf, disp), (0, 0))
    pygame.display.flip()
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
        pygame.time.wait(30)
    pygame.quit()


if __name__ == "__main__":
    main()
