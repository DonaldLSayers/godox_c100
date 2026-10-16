#!/usr/bin/env python3
"""Comparison sheets: EG variants (grade.py) on plain photos, rendered the way
the camera would, next to EG itself.

One sheet per photo, one row per group of palettes (the first row is always
the original, endesga32 and db16). Every tile carries its spec (e.g.
eg:t200:d12r3) and a swatch strip, and the specs are the same on every
photo, so you can pick favourites across sheets.

  uv run --with numpy,pillow tools/palette_sheet.py OUTDIR PHOTO... [--pal SPEC...]
  --pal     render just these specs (one row) instead of the default rows
Writes OUTDIR/<photo>.png, and OUTDIR/swatches.png with every palette.
"""
import argparse, os
from PIL import Image, ImageDraw
from grade import BASE, lch, variant
from palettes import LUT, WY, hex_to_yuv
from sim_palette import prepare, render

ROWS = [
    # regrade: EG's tint swapped for another hue or strength
    ['eg:x0', 'eg:x2', 'eg:t200', 'eg:t300', 'eg:t60'],
    # split tones: shadows / highlights
    ['eg:t220/60', 'eg:t300/80', 'eg:t180/30', 'eg:t260/200', 'eg:t240:x1.5:sat115'],
    # thinned: fewer colours, coarser and funkier, still every family
    ['eg:d8r1', 'eg:d14r1', 'eg:d14r2', 'eg:d20r1', 'eg:d20r2'],
    # both
    ['eg:t200:d14r1', 'eg:t60:d14r2', 'eg:t220/60:d14r1', 'eg:x2:d20r1', 'eg:t300/80:sat120:d14r2'],
]
STRIP = 14   # swatch strip height under each tile


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def tile(img, text, hexes):
    """img with a label top left and a swatch strip below."""
    w, h = img.size
    out = Image.new('RGB', (w, h + STRIP), 'white')
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 8 + 6 * len(text), 18], fill=(0, 0, 0))
    d.text((5, 3), text, fill=(255, 255, 255))
    sw = w / max(len(hexes), 1)
    for i, hx in enumerate(sorted(hexes, key=lambda x: lch(x)[0])):
        d.rectangle([round(i * sw), h, round((i + 1) * sw) - 1, h + STRIP - 1], fill=rgb(hx))
    return out


def grid(rows, path):
    w, h = rows[0][0].size
    n = max(len(r) for r in rows)
    img = Image.new('RGB', (n * w + (n - 1) * 4, len(rows) * (h + 4)), 'white')
    for j, row in enumerate(rows):
        for i, t in enumerate(row):
            img.paste(t, (i * (w + 4), j * (h + 4)))
    img.save(path)


def swatches(pals, path):
    S = 22
    img = Image.new('RGB', (190 + 32 * S, len(pals) * (S + 4) + 4), 'white')
    d = ImageDraw.Draw(img)
    for j, (spec, hexes) in enumerate(pals.items()):
        y = 4 + j * (S + 4)
        d.text((6, y + 5), f'{spec} ({len(hexes)})', fill=(0, 0, 0))
        for i, hx in enumerate(sorted(hexes, key=lambda x: lch(x)[0])):
            d.rectangle([190 + i * S, y, 190 + (i + 1) * S - 2, y + S - 1], fill=rgb(hx))
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('photos', nargs='+')
    ap.add_argument('--pal', nargs='+')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    refs = {'eg': BASE['endesga32'], 'db16': BASE['db16']}
    rows = [[(s, variant(s)) for s in row] for row in ([args.pal] if args.pal else ROWS)]
    swatches({**refs, **{s: hx for row in rows for s, hx in row}}, os.path.join(args.out, 'swatches.png'))

    def draw(src, spec, hexes):
        yuv = list(dict.fromkeys(hex_to_yuv(h) for h in hexes))
        return tile(render(src, yuv, wy=WY, lut=LUT), f'{spec} ({len(hexes)})', hexes)

    for p in args.photos:
        src = prepare(p, 640)
        out = [[tile(src, 'original', [])] + [draw(src, s, hx) for s, hx in refs.items()]]
        out += [[draw(src, s, hx) for s, hx in row] for row in rows]
        path = os.path.join(args.out, os.path.splitext(os.path.basename(p))[0] + '.png')
        grid(out, path)
        print(path)


if __name__ == '__main__':
    main()
