#!/usr/bin/env python3
"""Game Boy Camera mode: the numbers shared by sim_gb.py and gb_cave.s.

  gb.py asm   prints gb.inc (the thresholds and the shade colours as data)

A GB pixel is a 4x4 block of the 512x448 output (128x112 GB pixels, 8:7). The
look is gbcam.c's HARDWARE style (PIXELBOY: the M64282FP + MAC-GBD model) with
a fixed gain and the horizontal edge mode at 50 %.
"""
import os

PATTERN = [[0x00, 0x0C, 0x03, 0x0F], [0x08, 0x04, 0x0B, 0x07],
           [0x02, 0x0E, 0x01, 0x0D], [0x0A, 0x06, 0x09, 0x05]]
RANGE = (0x89, 0x92, 0xA2, 0xD2)        # contrast 7, "high light" (gb-photo, as in gbcam_dither.c)
SHARP_PCT = int(os.environ.get('GB_SHARP', 50))   # edge sharpening, 0-100: 50 = the sensor's 50 % (build.sh)
SHARP = (SHARP_PCT * 64 + 25) // 50     # in 1/64: the weight of the edge term (64 = 50 %), as the editor's sharpFix
GAIN_Q8 = 1024                          # fixed exposure, 4.0x (256 = 1.0): the best fixed gain on the
                                        # sample photos; gbcam.c's auto-exposure settles at 2.2-4.3x, start 3.5x
PALETTE = [(0x25, 0x25, 0x25), (0x4b, 0x56, 0x4d), (0x9a, 0xa5, 0x7c), (0xe0, 0xe9, 0xc4)]   # dark to light
SIZE = ((1232, 1080), (512, 448))       # (crop, output): 8:7, the GB pixel is 4x4 output pixels. The crop keeps the
                                        # sensor's full 1080-line height, like the other aspects: a 1078-line one
                                        # made every switch to and from it take seconds
GW, GH, BLK = 128, 112, 4
ASPECT = 5                             # the aspect setting the Game Boy mode selects: not one the arrow keys reach (0-4)
DATA_BYTES = 3 * 16 + 4 * 4 + 4 * 4    # TH0-2, GB_Y, GB_C
CURVE_ADDR = 0xbbb00                    # the 256-byte tone curve, the end of the video cave (video_cave.s)
S_CURVE = [(0, 0), (80, 64), (128, 128), (176, 191), (255, 255)]   # BW's: palettes.py BW_MATCH -> BW_LEVELS


def thresholds():
    """T[k][pos], pos = (gy & 3) * 4 + (gx & 3): gb-photo's dither_gen_base_values, a + (b - a) * v / 16."""
    return [[RANGE[k] + (RANGE[k + 1] - RANGE[k]) * v // 16 for row in PATTERN for v in row]
            for k in range(3)]


def yuv(c):
    """JFIF Y, U, V as the camera's buffers hold them (palettes.py hex_to_yuv, firmware.js rgbToYuv)."""
    r, g, b = c
    clamp = lambda x: max(0, min(255, round(x)))
    return (clamp(.299 * r + .587 * g + .114 * b), clamp(128 - .168736 * r - .331264 * g + .5 * b),
            clamp(128 + .5 * r - .418688 * g - .081312 * b))


def curve_table(on=None):
    """The tone curve applied to a block's mean luma before the exposure: the identity, or the
    S-curve (BW's: more contrast), piecewise linear through S_CURVE, rounded half to even; then the
    contrast and brightness the user chose."""
    if on is None:
        on = os.environ.get('GB_CURVE') == '1'
    out = list(range(256))
    if on:
        out = []
        for x in range(256):
            (x0, y0), (x1, y1) = next(seg for seg in zip(S_CURVE, S_CURVE[1:]) if x <= seg[1][0])
            out.append(round(y0 + (y1 - y0) * (x - x0) / (x1 - x0)))
    # GB_CONTRAST (percent, -50..50) scales around mid-grey, GB_BRIGHTNESS (-50..50) shifts, in whole
    # numbers so the editor's JavaScript gets the same table; the editor (firmware.js toneCurve) does the same.
    con, bri = int(os.environ.get('GB_CONTRAST', 0)), int(os.environ.get('GB_BRIGHTNESS', 0))
    return [min(255, max(0, ((t - 128) * (100 + con) + 12800 + 100 * bri + 50) // 100)) for t in out]


def palette():
    """GB_PALETTE (the site's editor, 4 hex colours, dark to light) or the default."""
    env = os.environ.get('GB_PALETTE')
    if not env:
        return PALETTE
    hexes = env.split(',')
    assert len(hexes) == 4, 'GB_PALETTE: 4 colours, e.g. 252525,4b564d,9aa57c,e0e9c4'
    return [tuple(int(h.strip().lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)) for h in hexes]


def asm():
    print(f'    .equ    GB_GAIN_Q8, {GAIN_Q8}')
    print(f'    .equ    GB_SHARP, {SHARP}')
    (cw, ch), (w, h) = SIZE
    print(f'    .equ    GB_W, {w}\n    .equ    GB_H, {h}\n    .equ    GB_CW, {cw}\n    .equ    GB_CH, {ch}\n    .equ    GB_ASPECT, {ASPECT}')
    print(f'    .equ    GB_CURVE_ADDR, {CURVE_ADDR:#x}')
    print('    .macro  GB_CURVE_DATA                 @ the tone curve: luma -> luma, 256 bytes')
    t = curve_table()
    for i in range(0, 256, 16):
        print('    .byte ' + ', '.join(map(str, t[i:i + 16])))
    print('    .endm')
    print('    .macro  GB_DATA')
    print('    .align  2')
    for k, t in enumerate(thresholds()):
        print(f'TH{k}:  .byte ' + ', '.join(map(str, t)))
    print('GB_Y:  .word ' + ', '.join(f'0x{yuv(c)[0] * 0x01010101:08x}' for c in palette()))
    print('GB_C:  .word ' + ', '.join('0x%08x' % (u | v << 8 | u << 16 | v << 24)
                                      for _, u, v in map(yuv, palette())))
    print('    .endm')


if __name__ == '__main__':
    import sys
    asm() if sys.argv[1:] == ['asm'] else print(__doc__)
