#!/usr/bin/env python3
"""Choose which NCOL colours of a big palette the camera should keep.

Backward elimination on real photos: start from the whole palette and keep
dropping the colour whose loss raises the total match error least, until NCOL
are left. Error = the camera's weighted distance (WY*dY + dU + dV) from each
2x2 block (with its Bayer offset) to its nearest remaining colour. The result
is a subset that looks like the full palette on photos, rather than the most
extreme colours. Paste the printed dict into PICK in palettes.py.

Usage: uv run --with numpy,pillow tools/palette_pick.py PHOTO.jpg...
"""
import sys
import numpy as np
from palettes import BASE, NCOL, WY, hex_to_yuv
from sim_palette import BAYER, prepare


def samples(paths, per=5000, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for p in paths:
        ycc = np.asarray(prepare(p, 640).convert('YCbCr'), dtype=np.int32)
        h, w = ycc.shape[0] // 2 * 2, ycc.shape[1] // 2 * 2
        blk = ycc[:h, :w].reshape(h // 2, 2, w // 2, 2, 3).sum(axis=(1, 3)) // 4
        bh, bw = blk.shape[:2]
        blk[..., 0] = np.clip(blk[..., 0] + (BAYER[np.arange(bh)[:, None] & 3,
                                                   np.arange(bw)[None, :] & 3] - 8) * 4, 0, 255)
        flat = blk.reshape(-1, 3)
        out.append(flat[rng.choice(len(flat), min(per, len(flat)), replace=False)])
    return np.concatenate(out)


def pick(hexes, S, n=NCOL):
    P = np.array([hex_to_yuv(h) for h in hexes])
    D = (WY * np.abs(S[:, None, 0] - P[None, :, 0]) + np.abs(S[:, None, 1] - P[None, :, 1])
         + np.abs(S[:, None, 2] - P[None, :, 2]))
    keep = list(range(len(hexes)))
    while len(keep) > n:
        cost = [D[:, [k for k in keep if k != c]].min(axis=1).sum() for c in keep]
        keep.remove(keep[int(np.argmin(cost))])
    return [hexes[k] for k in keep]


def main():
    S = samples(sys.argv[1:])
    print('PICK = {')
    for name, hexes in BASE.items():
        if len(hexes) > NCOL:
            print(f"    {name!r}: {pick(hexes, S)!r},")
    print('}')


if __name__ == '__main__':
    main()
