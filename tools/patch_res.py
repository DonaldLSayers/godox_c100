#!/usr/bin/env python3
"""Replace one resource in a C100 firmware image, in place within its slot.

Usage: patch_res.py FIRMWARE.BIN RESOURCE NEWFILE OUT.BIN
  e.g. patch_res.py GP_CARDVR_UPGRADE.BIN CAMERA.wav beep.wav build/GP_CARDVR_UPGRADE.BIN

Refuses to write if the new file doesn't fit the slot or (for WAVs) the audio
format differs from the original. The resource table itself is never modified.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gp_res import parse

PAD = 0xFF  # erased-flash value, matches the factory padding

def wav_fmt(blob):
    assert blob[:4] == b'RIFF' and blob[8:12] == b'WAVE', 'not a RIFF/WAVE file'
    off = 12
    while off + 8 <= len(blob):
        cid, size = blob[off:off+4], struct.unpack_from('<I', blob, off+4)[0]
        if cid == b'fmt ':
            return struct.unpack_from('<HHIIHH', blob, off+8)
        off += 8 + size + (size & 1)
    raise ValueError('no fmt chunk')

def main():
    src, res, new, out = sys.argv[1:5]
    d = bytearray(open(src, 'rb').read())
    new_blob = open(new, 'rb').read()

    slots = {f'{n}.{e}'.upper(): (s, end) for n, e, s, end in parse(d)}
    if res.upper() not in slots:
        sys.exit(f'unknown resource {res}; have: {", ".join(sorted(slots))}')
    start, end = slots[res.upper()]
    slot = end - start

    if res.upper().endswith('.WAV'):
        old, cur = wav_fmt(d[start:end]), wav_fmt(new_blob)
        if old != cur:
            sys.exit(f'WAV format mismatch: original (fmt,ch,rate,byterate,align,bits)={old}, new={cur}')
    if len(new_blob) > slot:
        sys.exit(f'{new} is {len(new_blob)} B but slot {res} is only {slot} B')

    d[start:end] = new_blob + bytes([PAD]) * (slot - len(new_blob))

    orig = open(src, 'rb').read()
    changed = [i for i in range(len(d)) if d[i] != orig[i]]
    assert len(d) == len(orig) and all(start <= i < end for i in changed)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'wb').write(d)
    print(f'{res}: wrote {len(new_blob)}/{slot} B at {start:#08x}; '
          f'{len(changed)} bytes changed, all inside the slot -> {out}')

if __name__ == '__main__':
    main()
