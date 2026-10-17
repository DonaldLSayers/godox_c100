#!/usr/bin/env python3
"""Preview every camera preset (palettes.py presets()) on photos, the way the
camera would.

Each photo is resized to the camera's output size (640 wide, aspect kept) and
run through the sim_palette.py replica of the hook: nearest colour in the
preset's match palette (luma weight WY, the camera's lookup-table
quantisation LUT), painted with the preset's film colour, with its
three-letter tag top right. Writes, under OUTDIR:
  swatches.png                every preset: match colours above, film colours below
  <photo>/<tag>.png           one full-size result per preset
  <photo>/sheet.png           original + all presets, one row per match palette

Usage: uv run --with numpy,pillow tools/palette_preview.py OUTDIR PHOTO...
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from palettes import FILMS, LUT, WY, presets, yuv_to_hex
from sim_palette import add_tag, match, prepare


def rgb(c):
    h = yuv_to_hex(c)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 8 + 6 * len(text), 20], fill=(0, 0, 0))
    d.text((5, 4), text, fill=(255, 255, 255))


def swatches(pre, path):
    """Per preset: match colours (top row), film colours (bottom row)."""
    S, gap, left = 22, 2, 70
    img = Image.new('RGB', (left + 32 * (S + gap), len(pre) * (2 * S + 12) + 8), 'white')
    d = ImageDraw.Draw(img)
    for j, (tag, P, D) in enumerate(pre):
        y = 6 + j * (2 * S + 12)
        d.text((8, y + S - 6), tag, fill=(0, 0, 0))
        for i, (p, q) in enumerate(zip(P, D)):
            x = left + i * (S + gap)
            d.rectangle([x, y, x + S - 1, y + S - 1], fill=rgb(p))
            d.rectangle([x, y + S, x + S - 1, y + 2 * S - 1], fill=rgb(q))
    img.save(path)


def render(src, tag, P, D):
    """Camera output for one preset, tag included."""
    blocks = add_tag(match(src, P, wy=WY, lut=LUT), tag, D)
    out = np.array(D, dtype=np.uint8)[blocks].repeat(2, axis=0).repeat(2, axis=1)
    return Image.fromarray(out, 'YCbCr').convert('RGB')


def sheet(tiles, path, cols):
    w, h = tiles[0][0].size
    img = Image.new('RGB', (cols * w, (len(tiles) + cols - 1) // cols * h), 'white')
    for i, (t, text) in enumerate(tiles):
        t = t.copy()
        label(t, text)
        img.paste(t, ((i % cols) * w, (i // cols) * h))
    img.save(path)


def main():
    out, photos = sys.argv[1], sys.argv[2:]
    pre = presets()
    os.makedirs(out, exist_ok=True)
    swatches(pre, os.path.join(out, 'swatches.png'))
    for p in photos:
        name = os.path.splitext(os.path.basename(p))[0]
        os.makedirs(os.path.join(out, name), exist_ok=True)
        src = prepare(p, 640)
        tiles = []
        for tag, P, D in pre:
            t = render(src, tag, P, D)
            t.save(os.path.join(out, name, f'{tag}.png'))
            tiles.append((t, f'{tag} ({FILMS[tag[1:]]})'))
        # the original at the start of each row, then that palette's 4 films
        rows = [tiles[i:i + len(FILMS)] for i in range(0, len(tiles), len(FILMS))]
        sheet([t for row in rows for t in [(src, 'original (camera size)')] + row],
              os.path.join(out, name, 'sheet.png'), cols=len(FILMS) + 1)
        print(name, src.size)


if __name__ == '__main__':
    main()
