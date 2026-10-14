#!/usr/bin/env python3
"""Preview every palette in palettes.py on photos, the way the camera would.

Each photo is resized to the camera's output size (640 wide, aspect kept) and
run through the sim_palette.py replica of the hook with the expanded palettes
and luma weight WY. Writes, under OUTDIR:
  swatches.png                every palette, base colours big, mixes small
  <photo>/<palette>.png       one full-size result per palette (all colours)
  <photo>/<palette>_10.png    big palettes reduced to NCOL, as the camera would
  <photo>/sheet.png           original + all palettes, labelled
  <photo>/sheet_full_vs_10.png  big palettes: all colours vs reduced to NCOL

Usage: uv run --with numpy,pillow tools/palette_preview.py OUTDIR PHOTO.jpg...
"""
import os, sys
from PIL import Image, ImageDraw
from palettes import NCOL, WY, expanded, yuv_to_hex
from sim_palette import prepare, render


def rgb(c):
    h = yuv_to_hex(c)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 8 + 6 * len(text), 20], fill=(0, 0, 0))
    d.text((5, 4), text, fill=(255, 255, 255))


def swatches(full, ten, path):
    """Big swatches = base colours, small = mixes; a bar under a colour of a
    big palette marks the NCOL picked for the camera."""
    S, gap, left, per = 44, 4, 120, 16
    lines = {name: (len(cols) + per - 1) // per for name, cols in full.items()}
    img = Image.new('RGB', (left + per * (S + gap), sum(lines.values()) * (S + 22) + 10 * len(full) + 10),
                    'white')
    d = ImageDraw.Draw(img)
    y0 = 10
    for name, cols in full.items():
        picked = {c for c, _ in ten[name]}
        d.text((8, y0 + S // 2 - 6), name, fill=(0, 0, 0))
        for i, (c, par) in enumerate(cols):
            x, y = left + (i % per) * (S + gap), y0 + (i // per) * (S + 22)
            inset = 0 if par is None else 9       # mixes drawn smaller
            d.rectangle([x + inset, y + inset, x + S - inset, y + S - inset], fill=rgb(c),
                        outline=(200, 200, 200))
            if len(cols) > len(ten[name]) and c in picked:
                d.rectangle([x, y + S + 2, x + S, y + S + 5], fill=(0, 0, 0))
            d.text((x + 2, y + S + 7), yuv_to_hex(c), fill=(0, 0, 0) if par is None else (120, 120, 120))
        y0 += lines[name] * (S + 22) + 10
    img.save(path)


def sheet(tiles, path, cols=3):
    w, h = tiles[0][0].size
    img = Image.new('RGB', (cols * w, (len(tiles) + cols - 1) // cols * h), 'white')
    for i, (t, text) in enumerate(tiles):
        t = t.copy()
        label(t, text)
        img.paste(t, ((i % cols) * w, (i // cols) * h))
    img.save(path)


def main():
    out, photos = sys.argv[1], sys.argv[2:]
    full, ten = expanded(full=True), expanded()
    os.makedirs(out, exist_ok=True)
    swatches(full, ten, os.path.join(out, 'swatches.png'))
    for p in photos:
        name = os.path.splitext(os.path.basename(p))[0]
        os.makedirs(os.path.join(out, name), exist_ok=True)
        src = prepare(p, 640)
        orig = (src, 'original (camera size)')
        tiles, big = [orig], [orig]
        for pname, cols in full.items():
            t = render(src, [c for c, _ in cols], wy=WY)
            t.save(os.path.join(out, name, f'{pname}.png'))
            tiles.append((t, f'{pname} ({len(cols)})'))
            if len(cols) > NCOL:
                t10 = render(src, [c for c, _ in ten[pname]], wy=WY)
                t10.save(os.path.join(out, name, f'{pname}_{NCOL}.png'))
                big += [(t, f'{pname} ({len(cols)})'), (t10, f'{pname} reduced to {NCOL}')]
        sheet(tiles, os.path.join(out, name, 'sheet.png'))
        sheet(big[1:], os.path.join(out, name, f'sheet_full_vs_{NCOL}.png'), cols=2)
        print(name, src.size)


if __name__ == '__main__':
    main()
