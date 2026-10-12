#!/usr/bin/env python3
"""List/extract the resource table in a GeneralPlus CARDVR firmware image.

Usage: gp_res.py FIRMWARE.BIN [OUTDIR]
"""
import os, struct, sys

RES_BASE = 0x170000  # 'GP' resource table, entries are sector (512 B) offsets
ENTRY = 0x18         # 20-byte name+ext, then u32 sector index
EXTS = ('GPZP', 'WAV', 'JPG', 'TTF', 'PAK', 'XML')

def parse(d):
    assert d[RES_BASE:RES_BASE+2] == b'GP', 'no resource table at 0x170000'
    ents, off = [], RES_BASE + 0x18
    while d[off] and chr(d[off]).isalnum():
        raw = d[off:off+0x14].rstrip(b'\0').decode('latin1')
        sec = struct.unpack_from('<I', d, off+0x14)[0]
        ext = next((e for e in EXTS if raw.endswith(e)), '')
        ents.append((raw[:len(raw)-len(ext)], ext.lower(), RES_BASE + sec*512))
        off += ENTRY
    out = []
    for i, (name, ext, start) in enumerate(ents):
        end = ents[i+1][2] if i+1 < len(ents) else len(d)
        out.append((name, ext, start, end))
    return out

def main():
    d = open(sys.argv[1], 'rb').read()
    outdir = sys.argv[2] if len(sys.argv) > 2 else None
    if outdir: os.makedirs(outdir, exist_ok=True)
    for name, ext, start, end in parse(d):
        blob = d[start:end]
        if ext == 'wav':  # trim padding using the RIFF size field
            blob = blob[:8 + struct.unpack_from('<I', blob, 4)[0]]
        print(f'{name+"."+ext:24s} {start:#08x}-{end:#08x}  {len(blob):7d} B  {blob[:4]!r}')
        if outdir:
            open(os.path.join(outdir, f'{name}.{ext}'), 'wb').write(blob)

if __name__ == '__main__':
    main()
