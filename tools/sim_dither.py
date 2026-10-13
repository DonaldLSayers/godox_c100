#!/usr/bin/env python3
"""Simulate on-camera palette + ordered (Bayer) dithering on a photo.

Works the way firmware code would: on YUV 4:2:2 data (one U/V pair shared by
two horizontal pixels), mapping brightness (Y) onto a ramp of palette colours.

Usage: sim_dither.py IN.jpg OUT.png PALETTE DITHER [BLOCK]
  PALETTE: gameboy | gray4 | bw
  DITHER:  none | bayer
  BLOCK:   pixel size in camera pixels (1 = full 320x240, 2 = 160x120 look)
Needs ffmpeg for JPEG/PNG conversion.
"""
import os, subprocess, sys, tempfile

PALETTES = {  # dark -> light, RGB
    'gameboy': [(0x0f, 0x38, 0x0f), (0x30, 0x62, 0x30), (0x8b, 0xac, 0x0f), (0x9b, 0xbc, 0x0f)],
    'gray4':   [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)],
    'bw':      [(0, 0, 0), (255, 255, 255)],
}

BAYER4 = [[0, 8, 2, 10],
          [12, 4, 14, 6],
          [3, 11, 1, 9],
          [15, 7, 13, 5]]

def rgb_to_yuv(r, g, b):  # JPEG/JFIF full-range YCbCr
    y = 0.299 * r + 0.587 * g + 0.114 * b
    u = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    v = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return tuple(max(0, min(255, round(c))) for c in (y, u, v))

def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *args], check=True)

def main():
    src, dst, pal_name, dither = sys.argv[1:5]
    block = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    pal = [rgb_to_yuv(*c) for c in PALETTES[pal_name]]
    n = len(pal)

    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                            'stream=width,height', '-of', 'csv=p=0', src],
                           capture_output=True, text=True, check=True).stdout.strip()
    w, h = map(int, probe.split(','))
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, 'in.yuv')
        ffmpeg('-i', src, '-f', 'rawvideo', '-pix_fmt', 'yuvj422p', raw)
        data = bytearray(open(raw, 'rb').read())
        Y = data[:w * h]
        U = data[w * h:w * h + w * h // 2]
        V = data[w * h + w * h // 2:]

        for y in range(h):
            for x in range(w):
                bx, by = x // block, y // block
                # brightness of the block's top-left pixel (cheap, like firmware)
                lum = Y[(by * block) * w + bx * block]
                level = lum * (n - 1) / 255
                if dither == 'bayer':
                    level += (BAYER4[by & 3][bx & 3] + 0.5) / 16 - 0.5
                idx = max(0, min(n - 1, round(level)))
                py, pu, pv = pal[idx]
                Y[y * w + x] = py
                if x % 2 == 0:  # U/V shared by the horizontal pixel pair
                    U[y * (w // 2) + x // 2] = pu
                    V[y * (w // 2) + x // 2] = pv

        out = os.path.join(tmp, 'out.yuv')
        open(out, 'wb').write(Y + U + V)
        ffmpeg('-f', 'rawvideo', '-pix_fmt', 'yuvj422p', '-s', f'{w}x{h}', '-i', out, dst)

if __name__ == '__main__':
    main()
