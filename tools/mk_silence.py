#!/usr/bin/env python3
"""Make a silent copy of a WAV: same RIFF header and byte length, data zeroed.

Usage: mk_silence.py IN.wav OUT.wav
Keeps the exact fmt (so patch_res.py accepts it) and the exact size.
"""
import struct, sys

def main():
    src, dst = sys.argv[1:3]
    d = bytearray(open(src, 'rb').read())
    assert d[:4] == b'RIFF' and d[8:12] == b'WAVE', 'not a RIFF/WAVE file'
    off = 12
    while off + 8 <= len(d):
        cid = bytes(d[off:off+4])
        size = struct.unpack_from('<I', d, off+4)[0]
        if cid == b'data':
            for i in range(off+8, min(off+8+size, len(d))):
                d[i] = 0
            break
        off += 8 + size + (size & 1)
    open(dst, 'wb').write(d)
    print(f'{dst}: {len(d)} B, data zeroed (silent)')

if __name__ == '__main__':
    main()
