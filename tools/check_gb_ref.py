#!/usr/bin/env python3
"""Check sim_gb.py against PIXELBOY's gbcam.c HARDWARE-style maths (ported to numpy
here: exposure, MAC-GBD code, 50 % horizontal edge, gb-photo threshold matrix),
on every plain photo in site/editor/photos: 0 differing GB pixels expected.

Usage: uv run --with numpy,pillow tools/check_gb_ref.py
"""
import glob, os, sys
import numpy as np
from PIL import Image
import gb
from sim_gb import shades

PAT = [v for row in gb.PATTERN for v in row]


def ref_matrix():
    """gbcam_build_matrix: [pos][interval], gb-photo's 16-step base values."""
    def base(a, b):
        step = (((b << 8) - (a << 8)) >> 4) if a < b else 0
        return [((a << 8) + i * step) >> 8 for i in range(16)]
    B = [base(gb.RANGE[k], gb.RANGE[k + 1]) for k in range(3)]
    return np.array([[B[k][PAT[i]] for k in range(3)] for i in range(16)])


def ref_shades(avg):
    """avg: (112, 128) mean luma -> shades, 0 = darkest (gbcam.c numbers black 3)."""
    td = lambda a, b: np.trunc(a / b).astype(int)
    avg = np.array(gb.curve_table())[avg]
    p = np.clip(128 + td((avg * gb.GAIN_Q8 >> 8) - 128, 8), 0, 255) - 128
    pad = np.pad(p, ((0, 0), (1, 1)), mode='edge')
    lap = 2 * p - pad[:, :-2] - pad[:, 2:]
    v = np.clip(td(p * 100 + lap * 50, 100), -128, 127) + 128
    t = ref_matrix()[(np.arange(112)[:, None] & 3) * 4 + (np.arange(128)[None, :] & 3)]
    return 3 - np.where(v < t[..., 0], 3, np.where(v < t[..., 1], 2, np.where(v < t[..., 2], 1, 0)))


bad = 0
for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), '..', 'site', 'editor', 'photos', '*.jpg'))):
    luma = np.asarray(Image.open(f).convert('L').resize((512, 448), Image.BILINEAR))
    avg = luma.astype(int).reshape(112, 4, 128, 4).sum(axis=(1, 3)) >> 4
    n = int((shades(luma) != ref_shades(avg)).sum())
    bad += n
    print(f'{os.path.basename(f):16} differing GB pixels: {n}')
sys.exit(1 if bad else 0)
