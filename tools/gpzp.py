#!/usr/bin/env python3
"""Decode/encode GeneralPlus GPZP UI images (as used by the Godox C100).

Format (reverse-engineered from the C100 firmware):
  bytes 0..3  : magic 'GPZP'
  bytes 4..   : raw DEFLATE (fixed Huffman, BTYPE=1 -- the camera rejects
                dynamic Huffman) of RGB565 pixels, 2 bytes/pixel, little-endian.
The pixel value 0x8C71 is the transparency key (shown transparent in the PNG);
the C100's LCD is 320x240, so full-screen assets are 320x240.

Usage:
  gpzp.py decode IN.gpzp OUT.png [WIDTH]     # WIDTH auto-detected if omitted
  gpzp.py encode IN.png  OUT.gpzp            # width/height taken from the PNG
  gpzp.py decode-all FIRMWARE.BIN OUTDIR     # every GPZP in the image -> PNGs

encode needs ffmpeg (to read the PNG); decode is pure stdlib.
"""
import os, struct, subprocess, sys, zlib

KEY = 0x8C71                                  # RGB565 transparency key

def rgb565_to_rgb(v):
    r, g, b = (v >> 11) & 0x1f, (v >> 5) & 0x3f, v & 0x1f
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31

def rgb_to_rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

# ---- PNG write (stdlib) -----------------------------------------------------
def write_png(path, w, h, rgba):
    def chunk(typ, data):
        return (struct.pack('>I', len(data)) + typ + data +
                struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))
    raw = bytearray()
    for y in range(h):
        raw.append(0)                         # filter: none
        raw += rgba[y * w * 4:(y + 1) * w * 4]
    out = b'\x89PNG\r\n\x1a\n'
    out += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    out += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    out += chunk(b'IEND', b'')
    open(path, 'wb').write(out)

# ---- RGB565 <-> RGBA --------------------------------------------------------
def rgb565_to_rgba(data, w, h):
    out = bytearray(w * h * 4)
    o = 0
    for i in range(0, w * h * 2, 2):
        v = data[i] | (data[i + 1] << 8)
        if v == KEY:
            out[o:o + 4] = b'\0\0\0\0'
        else:
            r, g, b = rgb565_to_rgb(v)
            out[o], out[o + 1], out[o + 2], out[o + 3] = r, g, b, 255
        o += 4
    return bytes(out)

def rgba_to_rgb565(rgba, w, h):
    out = bytearray(w * h * 2)
    o = 0
    for i in range(0, w * h * 4, 4):
        r, g, b, a = rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3]
        v = KEY if a < 128 else rgb_to_rgb565(r, g, b)
        out[o], out[o + 1] = v & 0xff, (v >> 8) & 0xff
        o += 2
    return bytes(out)

# Widths confirmed by eye (the C100 LCD is 320x240). Others are auto-detected,
# which is reliable for distinct images but only a guess for tiny repeating bars.
KNOWN_WIDTHS = {
    'BACKGROUND': 320,
    'TFT_WIFI_SYM': 320,
    'SELECTBAR_LONG': 296,
}

# ---- width auto-detection ---------------------------------------------------
# The true row stride is where vertically-adjacent pixels match best *and*
# shifting by one column (shearing) clearly makes it worse -- a sharp dip.
def _vdiff(data, px16, stride):
    s = n = 0
    step = max(1, (len(px16) - stride) // 3000)
    for i in range(0, len(px16) - stride, step):
        s += abs(px16[i] - px16[i + stride]); n += 1
    return s / max(1, n)

def guess_width(data, px):
    px16 = [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]
    best = None
    for w in range(16, 641):
        if px % w:
            continue
        a, am, ap = _vdiff(data, px16, w), _vdiff(data, px16, w - 1), _vdiff(data, px16, w + 1)
        if a < am and a < ap:                 # local dip = likely true stride
            depth = (min(am, ap) - a) / (a + 1)
            if best is None or depth > best[0]:
                best = (depth, w)
    # fall back to the most square-ish divisor if no dip stands out
    if best is None:
        divs = [w for w in range(16, 641) if px % w == 0]
        return min(divs, key=lambda w: abs(w - px // w)) if divs else px
    return best[1]

# ---- top level --------------------------------------------------------------
def decode(path, out_png, width=None):
    d = open(path, 'rb').read()
    assert d[:4] == b'GPZP', f'{path}: not a GPZP file'
    data = zlib.decompressobj(-15).decompress(d[4:])
    px = len(data) // 2
    name = os.path.splitext(os.path.basename(path))[0].upper()
    w = width or KNOWN_WIDTHS.get(name) or guess_width(data, px)
    h = px // w
    write_png(out_png, w, h, rgb565_to_rgba(data, w, h))
    print(f'{os.path.basename(path)} -> {out_png}  {w}x{h}')
    return w, h

def read_png_rgba(path):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path],
                           capture_output=True, text=True, check=True).stdout.strip()
    w, h = map(int, probe.split(','))
    rgba = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'rawvideo',
                           '-pix_fmt', 'rgba', '-'], capture_output=True, check=True).stdout
    return w, h, rgba

def encode(in_png, out_gpzp):
    w, h, rgba = read_png_rgba(in_png)
    if w % 2:
        sys.exit('width must be even (UYVY pairs two pixels)')
    uyvy = rgba_to_rgb565(rgba, w, h)
    co = zlib.compressobj(9, zlib.DEFLATED, -15, 9, zlib.Z_FIXED)  # fixed Huffman
    comp = co.compress(uyvy) + co.flush()
    open(out_gpzp, 'wb').write(b'GPZP' + comp)
    print(f'{in_png} -> {out_gpzp}  {w}x{h}  {len(comp) + 4} B compressed')

def decode_all(firmware, outdir):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gp_res import parse
    d = open(firmware, 'rb').read()
    os.makedirs(outdir, exist_ok=True)
    for name, ext, start, end in parse(d):
        if ext != 'gpzp':
            continue
        blob = d[start:end]
        if blob[:4] != b'GPZP':
            continue
        tmp = os.path.join(outdir, name + '.gpzp')
        open(tmp, 'wb').write(blob)
        try:
            decode(tmp, os.path.join(outdir, name + '.png'))
        except Exception as e:
            print(f'{name}: FAILED ({e})')
        os.remove(tmp)

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == 'decode':
        decode(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else None)
    elif cmd == 'encode':
        encode(sys.argv[2], sys.argv[3])
    elif cmd == 'decode-all':
        decode_all(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
