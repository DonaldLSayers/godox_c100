#!/usr/bin/env python3
"""Run the built photo cave in an ARM emulator and check it against the sim.

Loads build/GP_CARDVR_UPGRADE.BIN, stubs the firmware calls the cave makes
(cache maintenance, pvPortMalloc), then:
  1. runs idx_stub (the per-photo entry) with a given tick count, which picks
     the palette and fills the lookup table;
  2. packs 640x64 slices of a photo into strips in the camera's YUV 4:2:0
     layout (see docs/2026-10-13-image-processing.md) and runs the strip hook
     on two of them;
  3. unpacks each strip and checks that every 2x2 block is exactly the palette
     colour sim_palette.py picks (same palette, WY and table), including the
     palette tag on the photo's first strip and not on the second.

Usage: uv run --with unicorn,numpy,pillow tools/emu_cave.py PHOTO.jpg [TICKS...]
"""
import struct, subprocess, sys
import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP
from palettes import LUT, WY, expanded
from sim_palette import add_tag, match, prepare

FW = 'build/GP_CARDVR_UPGRADE.BIN'
APP = 0x10200                       # file offset of RAM address 0
RESUME, RESUME187 = 0x1544c, 0x187c8
CACHE_INV, CACHE_CLEAN, MALLOC = 0x401ac, 0x401b8, 0x5374c
PHOTO, STRIP_BYTES, TICK = 0x1317ac, 0x13155c, 0x126b80
STRIP_A, HEAP, STACK = 0x400000, 0x800000, 0xf00000
W, ROWS = 640, 64


def symbols(obj='build/obj/photo_cave.o'):
    out = subprocess.run(['/opt/homebrew/opt/llvm/bin/llvm-nm', obj], capture_output=True, text=True,
                         check=True).stdout
    return {parts[2]: int(parts[0], 16) for parts in map(str.split, out.splitlines()) if len(parts) == 3}


def machine():
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0, 0x1000000)
    uc.mem_write(0, open(FW, 'rb').read()[APP:APP + 0x200000])
    calls = []

    def on_code(uc, addr, size, _):
        if addr in (CACHE_INV, CACHE_CLEAN, MALLOC):
            calls.append((addr, uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
            if addr == MALLOC:
                uc.reg_write(UC_ARM_REG_R0, HEAP)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr in (RESUME, RESUME187):
            uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, on_code)
    return uc, calls


def run(uc, entry, r0=0, r1=0):
    uc.reg_write(UC_ARM_REG_SP, STACK)
    uc.reg_write(UC_ARM_REG_R0, r0)
    uc.reg_write(UC_ARM_REG_R1, r1)
    uc.emu_start(entry, 0xffffffff, count=200_000_000)
    return uc.reg_read(UC_ARM_REG_PC)


def pack(ycc):
    """640x64 YCbCr (H, W, 3) -> one strip: per 2-row band, even row = luma +
    first half of the chroma pairs, odd row = second half + luma."""
    third, stride = W // 2, W * 3 // 2
    blk = (ycc.astype(int).reshape(ROWS // 2, 2, W // 2, 2, 3).sum(axis=(1, 3)) // 4).astype(np.uint8)  # as sim
    out = bytearray()
    for b in range(ROWS // 2):
        uv = blk[b, :, 1:].reshape(-1)                 # U,V per pair, W/2 pairs
        half = len(uv) // 2
        out += bytes(ycc[2 * b, :, 0]) + bytes(uv[:half])
        out += bytes(uv[half:]) + bytes(ycc[2 * b + 1, :, 0])
    assert len(out) == stride * ROWS
    return bytes(out)


def unpack(buf):
    third, stride = W // 2, W * 3 // 2
    Y = np.zeros((ROWS, W), np.uint8)
    UV = np.zeros((ROWS // 2, W // 2, 2), np.uint8)
    for b in range(ROWS // 2):
        even = np.frombuffer(buf, np.uint8, stride, 2 * b * stride)
        odd = np.frombuffer(buf, np.uint8, stride, (2 * b + 1) * stride)
        Y[2 * b], Y[2 * b + 1] = even[:2 * third], odd[third:]
        UV[b] = np.concatenate([even[2 * third:], odd[:third]]).reshape(-1, 2)
    return Y, UV


def main():
    photo, ticks = sys.argv[1], [int(t) for t in sys.argv[2:]] or [0, 1, 2, 3, 4, 5, 6, 7, 7, 300]
    sym = symbols()
    names, pals = zip(*expanded().items())
    src = prepare(photo, W)
    uc, calls = machine()
    kinds = {CACHE_INV: 'inv', CACHE_CLEAN: 'clean', MALLOC: 'malloc'}
    worst = 0
    for t in ticks:
        uc.mem_write(TICK, struct.pack('<I', t))
        calls.clear()
        assert run(uc, sym['idx_stub']) == RESUME187
        idx = struct.unpack('<I', uc.mem_read(sym['VARS'] + 8, 4))[0]
        P = [c for c, _ in pals[idx]]
        lookup = {c: i for i, c in enumerate(P)}
        diffs = []
        for strip, top in enumerate((0, 200)):       # the photo's 1st and 2nd strip
            crop = src.crop((0, top, W, top + ROWS))
            uc.mem_write(STRIP_A, pack(np.asarray(crop.convert('YCbCr'))))
            uc.mem_write(PHOTO + 0x18, struct.pack('<I', STRIP_A))
            uc.mem_write(STRIP_BYTES, struct.pack('<I', W * 32 * 3 // 2))
            assert run(uc, sym['hook'], r0=0x300000, r1=STRIP_A) == RESUME
            Y, UV = unpack(bytes(uc.mem_read(STRIP_A, W * 3 // 2 * ROWS)))
            # every 2x2 block must be exactly one palette colour, the one the sim picks
            ref = match(crop, P, wy=WY, lut=LUT)
            if strip == 0:
                add_tag(ref, names[idx], pals[idx])
            got = np.full(ref.shape, -1)
            for b in range(ROWS // 2):
                for c in range(W // 2):
                    ys = {Y[2 * b + dy, 2 * c + dx] for dy in (0, 1) for dx in (0, 1)}
                    if len(ys) == 1:
                        got[b, c] = lookup.get((ys.pop(), *UV[b, c]), -1)
            diffs.append((got != ref).mean() * 100)
        worst = max(worst, *diffs)
        print(f'tick {t:4}: palette {idx} {names[idx]} ({len(P)} colours), blocks differing from sim: '
              f'strip 1 (tag) {diffs[0]:.2f}%, strip 2 {diffs[1]:.2f}%, '
              f'calls: {[kinds[a] for a, _, _ in calls]}')
    print('max difference', worst)


if __name__ == '__main__':
    main()
