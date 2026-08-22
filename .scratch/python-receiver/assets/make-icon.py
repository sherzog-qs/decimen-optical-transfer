"""The receiver's icon: the decimen mark in the receiver's own green.

Same artwork as the sender (public/icon-512.png), recoloured so the two Docks
entries are told apart at a glance. Blue is the sender's ACCENT, green is the
receiver's LIVE — the colour its own live dot already uses, so nothing new is
invented. Each pixel is projected onto the background->mark line and re-mixed
toward the new colour, which keeps the anti-aliased edges intact.

    uv run python .scratch/python-receiver/assets/make-icon.py
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pygame

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python-receiver"))
from decimen import ui as theme            # noqa: E402

SRC = ROOT / "public" / "icon-512.png"
DST = ROOT / "python-receiver" / "decimen" / "icon.png"
BG = np.array([7, 10, 17], float)          # the logo tile, #070a11
MARK = np.array([88, 200, 255], float)     # the sender's blue, #58c8ff

pygame.init()
surf = pygame.image.load(str(SRC))
rgb = np.transpose(pygame.surfarray.array3d(surf), (1, 0, 2)).astype(float)
alpha = np.transpose(pygame.surfarray.array_alpha(surf), (1, 0))

axis = MARK - BG
t = np.clip(((rgb - BG) @ axis) / (axis @ axis), 0, 1)[..., None]
out = np.clip(BG + t * (np.array(theme.LIVE, float) - BG), 0, 255).astype(np.uint8)

dst = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
pygame.surfarray.blit_array(dst, np.transpose(out, (1, 0, 2)))
pygame.surfarray.pixels_alpha(dst)[:] = np.transpose(alpha, (1, 0))
pygame.image.save(dst, str(DST))
print(f"{DST.relative_to(ROOT)}  {surf.get_size()}  mark {theme.LIVE}")
