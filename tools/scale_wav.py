#!/usr/bin/env python3
"""Scale a 16-bit PCM WAV's samples to PCT percent, keeping its header and size.

  scale_wav.py IN.wav OUT.wav PCT

Each sample becomes trunc(sample * PCT / 100) toward zero, in integers (the
site's editor, firmware.js scaleWav, does the same).
"""
import struct, sys

src, dst, pct = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = bytearray(open(src, 'rb').read())
assert d[:4] == b'RIFF' and d[8:12] == b'WAVE'
off = 12
while off + 8 <= len(d):
    cid, size = bytes(d[off:off + 4]), struct.unpack_from('<I', d, off + 4)[0]
    if cid == b'fmt ':
        assert struct.unpack_from('<HH', d, off + 8) == (1, 1) and struct.unpack_from('<H', d, off + 22)[0] == 16, 'mono 16-bit PCM only'
    if cid == b'data':
        n = min(size, len(d) - off - 8) // 2
        for i in range(n):
            (s,) = struct.unpack_from('<h', d, off + 8 + 2 * i)
            struct.pack_into('<h', d, off + 8 + 2 * i, (abs(s) * pct // 100) * (1 if s >= 0 else -1))
        break
    off += 8 + size + (size & 1)
open(dst, 'wb').write(d)
