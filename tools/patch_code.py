#!/usr/bin/env python3
"""Apply byte patches to the C100 app code, addressed by RAM address.

Usage: patch_code.py FIRMWARE.BIN OUT.BIN ADDR:OLDHEX:NEWHEX [...]
  e.g. patch_code.py GP_CARDVR_UPGRADE.BIN build/GP_CARDVR_UPGRADE.BIN 0xf3dc:c4f70000:38f70000

ADDR is the address as seen in Ghidra / decomp (app loaded at 0x0); bytes are
in file order (little-endian). Each patch is applied only if the current bytes
equal OLDHEX, and never inside the protected ranges below.
"""
import sys

APP_FILE_OFFSET = 0x10200  # file offset = addr + this

# Never patch these: an app that can't boot or can't update loses SD recovery.
PROTECTED = [
    (-APP_FILE_OFFSET, 0x0, 'bootloader + app header'),
    (0x24000, 0x26000, 'SD firmware upgrade code (FUN_000245f0..FUN_000259c8)'),
]

def main():
    src, out, *patches = sys.argv[1:]
    if not patches:
        sys.exit(__doc__)
    d = bytearray(open(src, 'rb').read())
    for p in patches:
        addr_s, old_s, new_s = p.split(':')
        addr, old, new = int(addr_s, 0), bytes.fromhex(old_s), bytes.fromhex(new_s)
        if len(old) != len(new):
            sys.exit(f'{p}: old and new must be the same length')
        for lo, hi, why in PROTECTED:
            if addr < hi and addr + len(new) > lo:
                sys.exit(f'{p}: refusing to patch {why}')
        off = addr + APP_FILE_OFFSET
        cur = bytes(d[off:off+len(old)])
        if cur != old:
            sys.exit(f'{p}: expected {old.hex()} at {addr:#x}, found {cur.hex()} (wrong input file?)')
        d[off:off+len(new)] = new
        print(f'{addr:#08x} (file {off:#08x}): {old.hex()} -> {new.hex()}')
    open(out, 'wb').write(d)
    print(f'wrote {out}')

if __name__ == '__main__':
    main()
