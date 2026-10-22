#!/usr/bin/env python3
"""Off-camera replica of gb_cave.s (Game Boy Camera mode), integer-exact.

  sim_gb.py IN.jpg OUT.png [--grey]

Per GB pixel (a 4x4 block of the 512x448 output): mean luma Y -> tone curve (identity,
or BW's S-curve with GB_CURVE=1) -> exposure
(Y * gain >> 8) -> p = (that - 128) / 8 toward zero (the MAC-GBD code less
128) -> horizontal edge, (2p + (2p - left - right)) / 2 toward zero -> compare
128 + that with the 3 thresholds of its position (gb.py) -> shade 0..3 (0 =
darkest). The maths of PIXELBOY's gbcam.c (HARDWARE style, 50 % horizontal
edge).
"""
import argparse
import numpy as np
from PIL import Image
import gb


def shades(luma):
    """luma: (H, W) uint8, H and W multiples of 4 (512x448 is the Game Boy's own shape) -> (H/4, W/4) shades 0..3."""
    gh, gw = luma.shape[0] // gb.BLK, luma.shape[1] // gb.BLK
    avg = luma.astype(int).reshape(gh, gb.BLK, gw, gb.BLK).sum(axis=(1, 3)) >> 4
    avg = np.array(gb.curve_table())[avg]          # the tone curve (GB_CURVE=1: BW's S-curve)
    p = np.trunc(((avg * gb.GAIN_Q8 >> 8) - 128) / 8).astype(int)
    pad = np.pad(p, ((0, 0), (1, 1)), mode='edge')
    code = 128 + np.trunc((128 * p + gb.SHARP * (2 * p - pad[:, :-2] - pad[:, 2:])) / 128).astype(int)
    pos = (np.arange(gh)[:, None] & 3) * 4 + (np.arange(gw)[None, :] & 3)
    return sum((code >= np.array(t)[pos]).astype(int) for t in gb.thresholds())


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('src'); a.add_argument('dst')
    a.add_argument('--grey', action='store_true')
    o = a.parse_args()
    luma = np.asarray(Image.open(o.src).convert('L').resize((gb.GW * gb.BLK, gb.GH * gb.BLK), Image.BILINEAR))
    s = shades(luma)
    pal = np.array([(v, v, v) for v in (0, 85, 170, 255)] if o.grey else gb.PALETTE, np.uint8)
    Image.fromarray(pal[s]).resize((gb.GW * gb.BLK, gb.GH * gb.BLK), Image.NEAREST).save(o.dst)
    print('shade histogram', np.bincount(s.ravel(), minlength=4) / s.size)
