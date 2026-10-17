#!/usr/bin/env python3
"""Film simulations on the presets' match palettes (palettes.py MATCH), on plain photos.

Palette first, then film: each 2x2 block gets its nearest palette colour (as
the camera does), and is painted with film(that colour). On the camera that's
a 32-colour display table per film; the matching table doesn't change.

  uv run --with numpy,pillow tools/film_sheet.py OUTDIR PHOTO... [--films NAME...]

Writes, under OUTDIR:
  <film>.png      one row per photo: original | film alone | EG+ | R6+ |
                  EG+ -> film | R6+ -> film
  palettes.png    one row per photo: original | EG | EG+ | R6 | R6+
                  (the current camera palettes next to the candidates, no film)
Films are read from film_luts/*/*.png; --films picks some by exact name
(without .png), default FILMS below.
"""
import argparse, glob, os
import numpy as np
from PIL import Image
from film import apply_hex, apply_img, load
from palette_sheet import grid, tile
from palettes import LUT, MATCH, WY, expanded, hex_to_yuv, yuv_to_hex
from sim_palette import match, prepare

ROOT = os.path.join(os.path.dirname(__file__), '..', 'film_luts')
FILMS = ['polaroid_690', 'fuji_velvia_100_generic', 'fuji_provia_100_generic', 'agfa_vista_200']
CANDIDATES = {name: [yuv_to_hex(c) for c in MATCH[k]] for name, k in (('eg+', 'E'), ('r6+', '6'))}


def paint(src, match_hex, show_hex):
    """Nearest colour in match_hex per 2x2 block (as the camera), painted
    with the same-index colour of show_hex."""
    blocks = match(src, [hex_to_yuv(h) for h in match_hex], wy=WY, lut=LUT)
    out = np.array([hex_to_yuv(h) for h in show_hex], dtype=np.uint8)[blocks]
    out = out.repeat(2, axis=0).repeat(2, axis=1)
    return Image.fromarray(out, 'YCbCr').convert('RGB')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('photos', nargs='+')
    ap.add_argument('--films', nargs='+', default=FILMS)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    films = {os.path.splitext(os.path.basename(f))[0]: f
             for f in sorted(glob.glob(os.path.join(ROOT, '*', '*.png')))}
    missing = set(args.films) - set(films)
    assert not missing, f'no such film: {sorted(missing)}'

    srcs = [prepare(p, 640) for p in args.photos]
    cam = {n: [yuv_to_hex(c) for c, _ in cols] for n, cols in expanded().items()}
    plain = {name: [tile(paint(s, hx, hx), name, hx) for s in srcs] for name, hx in CANDIDATES.items()}
    originals = [tile(s, os.path.basename(p), []) for s, p in zip(srcs, args.photos)]

    old = {'eg': 'endesga32', 'r6': 'riso6'}
    rows = []
    for i, src in enumerate(srcs):
        row = [originals[i]]
        for short, full in old.items():
            row += [tile(paint(src, cam[full], cam[full]), full, cam[full]), plain[short + '+'][i]]
        rows.append(row)
    grid(rows, os.path.join(args.out, 'palettes.png'))
    print('palettes')

    for name in args.films:
        cube = load(films[name])
        show = {p: apply_hex(cube, hx) for p, hx in CANDIDATES.items()}
        rows = []
        for i, src in enumerate(srcs):
            rows.append([originals[i], tile(apply_img(cube, src), name, [])]
                        + [plain[p][i] for p in CANDIDATES]
                        + [tile(paint(src, hx, show[p]), f'{p} -> {name}', show[p])
                           for p, hx in CANDIDATES.items()])
        grid(rows, os.path.join(args.out, f'{name}.png'))
        print(name)


if __name__ == '__main__':
    main()
