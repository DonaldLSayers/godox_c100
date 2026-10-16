#!/usr/bin/env python3
"""Sort the camera's photos and videos into one folder per palette.

Reads the two-letter palette tag the camera draws top right (see palettes.py)
and moves each file in DIR to DIR/<tag>/, e.g. images/IMG_0400.jpg ->
images/eg/IMG_0400.jpg. Only files directly in DIR are looked at, so new ones
can be dumped there and the script rerun. Files whose tag can't be read
confidently go to DIR/unknown/.

The tag is matched, not OCR'd: for every palette, compare the tag's cells in
the image against the cells that palette's tag would have (letters in its
lightest colour, outline in its darkest). The closest one wins.

  uv run --with numpy,pillow tools/sort_images.py [DIR] [--dry-run] [--resort]
  DIR       default: images/
  --dry-run print what would move, move nothing
  --resort  also re-check files already in palette subfolders
Videos (.mov) need ffmpeg: one frame is taken from half a second in.
"""
import argparse, io, os, shutil, subprocess, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from palettes import TAG, TAG_COLS, TAG_RIGHT, TAG_ROWS, TAG_SCALE, TAG_TOP, expanded, tag_cells, tag_colours

EXTS = {'.jpg', '.jpeg', '.mov', '.mp4'}
CELL = 2 * TAG_SCALE   # image pixels per tag cell (a block is 2x2 pixels)
MAX_SCORE = 40         # mean Y+U+V distance above this: tag not found
MIN_MARGIN = 1.3       # runner-up must score at least this much worse


def templates():
    """{tag: (cells, yuv per cell)} for every palette."""
    out = {}
    for name, cols in expanded().items():
        dark, light = tag_colours(cols)
        cells = np.array(tag_cells(name))
        want = np.zeros(cells.shape + (3,))
        want[cells == 1] = cols[dark][0]
        want[cells == 2] = cols[light][0]
        out[TAG[name].lower()] = (cells > 0, want)
    return out


def load(path):
    if os.path.splitext(path)[1].lower() in ('.mov', '.mp4'):
        png = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', path, '-frames:v', '1',
                              '-f', 'image2pipe', '-vcodec', 'png', '-'],
                             capture_output=True, check=True).stdout
        img = Image.open(io.BytesIO(png))
    else:
        img = Image.open(path)
    return np.asarray(img.convert('RGB').convert('YCbCr'), dtype=float)


def tag_region(yuv):
    """Mean Y,U,V of the centre of each tag cell (the edges bleed in the JPEG)."""
    w = yuv.shape[1]
    x0 = w - 2 * TAG_RIGHT - TAG_COLS * CELL
    y0 = 2 * TAG_TOP
    c = CELL // 4
    out = np.zeros((TAG_ROWS, TAG_COLS, 3))
    for r in range(TAG_ROWS):
        for k in range(TAG_COLS):
            y, x = y0 + r * CELL, x0 + k * CELL
            out[r, k] = yuv[y + c:y + CELL - c, x + c:x + CELL - c].reshape(-1, 3).mean(0)
    return out


def classify(path, tmpl):
    """(tag or None, scores sorted best first)."""
    got = tag_region(load(path))
    scores = sorted((np.abs(got[mask] - want[mask]).sum(1).mean(), tag)
                    for tag, (mask, want) in tmpl.items())
    (best, tag), (second, _) = scores[0], scores[1]
    ok = best <= MAX_SCORE and second >= MIN_MARGIN * best
    return (tag if ok else None), scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir', nargs='?', default=os.path.join(os.path.dirname(__file__), '..', 'images'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--resort', action='store_true')
    args = ap.parse_args()
    root = os.path.normpath(args.dir)
    tmpl = templates()

    files = [os.path.join(root, f) for f in os.listdir(root)]
    if args.resort:
        for sub in list(tmpl) + ['unknown']:
            d = os.path.join(root, sub)
            if os.path.isdir(d):
                files += [os.path.join(d, f) for f in os.listdir(d)]
    files = sorted(f for f in files if os.path.isfile(f) and os.path.splitext(f)[1].lower() in EXTS)

    counts = {}
    for path in files:
        try:
            tag, scores = classify(path, tmpl)
        except Exception as e:   # unreadable file, ffmpeg missing, ...
            tag, scores = None, []
            print(f'{os.path.basename(path)}: {e}', file=sys.stderr)
        dest_dir = os.path.join(root, tag or 'unknown')
        counts[tag or 'unknown'] = counts.get(tag or 'unknown', 0) + 1
        best = ', '.join(f'{t} {s:.0f}' for s, t in scores[:3])
        if os.path.dirname(path) == dest_dir:
            continue
        print(f'{os.path.relpath(path, root):24} -> {tag or "unknown":8} ({best})')
        if not args.dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(path))
            if os.path.exists(dest):
                print(f'  {dest} already exists, skipped', file=sys.stderr)
                continue
            shutil.move(path, dest)
    print('\n' + '  '.join(f'{t}: {n}' for t, n in sorted(counts.items(), key=lambda x: -x[1])))


if __name__ == '__main__':
    main()
