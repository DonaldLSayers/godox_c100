#!/usr/bin/env python3
"""Run the built firmware's Game Boy Camera mode in an ARM emulator and check
every pixel against sim_gb.py.

Sets the mode byte to GB_MODE (with no preset table built, so the hooks must
not need one), packs the full 64-row strips of a photo in the camera's YUV
4:2:0 strip layout, runs the photo hook and the video hook on each, unpacks
the result, and compares luma and chroma with the sim's shades painted in
gb.py's PALETTE. It runs at every aspect size (palettes.py SIZES: 704x396, 640x428,
608x456, 528x528) and at the mode's own 512x448 (the mode works at whatever size is
selected, with 4x4 blocks). Then it checks the normal mode (NORMAL_MODE) leaves both hooks'
strips exactly as they came, and reports the instructions per strip.

Usage: uv run --with unicorn,numpy,pillow tools/emu_gb.py PHOTO.jpg [LLVM-NM]
       (build first: sh tools/build.sh; GB_CURVE=1 to test the S-curve, in the
       build and here)
"""
import struct, subprocess, sys
import numpy as np
from PIL import Image
from unicorn import UC_HOOK_BLOCK, UC_HOOK_CODE
import emu_cave, gb
from palettes import SIZES
from sim_gb import shades

NM = sys.argv[2] if len(sys.argv) > 2 else 'llvm-nm'
RESUMEV, STRUCT, GB_MODE, NORMAL_MODE = 0x18d18, 0x500000, 9, 10


def symbols():
    out = ''.join(subprocess.run([NM, f'build/obj/{o}.o'], capture_output=True, text=True, check=True).stdout
                  for o in ('photo_cave', 'video_cave'))
    return {p[2]: int(p[0], 16) for p in map(str.split, out.splitlines()) if len(p) == 3}


def run_strip(uc, sym, kind, strip, width):
    uc.mem_write(emu_cave.STRIP_A, strip)
    if kind == 'photo':
        uc.mem_write(emu_cave.PHOTO + 0x18, struct.pack('<I', emu_cave.STRIP_A))
        uc.mem_write(emu_cave.STRIP_BYTES, struct.pack('<I', width * 32 * 3 // 2))
        assert emu_cave.run(uc, sym['hook'], r0=0x300000, r1=emu_cave.STRIP_A) == emu_cave.RESUME
    else:
        uc.mem_write(STRUCT, struct.pack('<I', 1))
        uc.mem_write(STRUCT + 8, struct.pack('<I', emu_cave.STRIP_A | 0x30000000))
        uc.mem_write(STRUCT + 0xdc, struct.pack('<I', width))
        uc.mem_write(STRUCT + 0x101, b'#')
        emu_cave.run(uc, sym['vhook'], r0=STRUCT)


def main():
    sym = symbols()
    photo = Image.open(sys.argv[1]).convert('RGB')
    uc, calls = emu_cave.machine()
    uc.hook_add(UC_HOOK_CODE, lambda u, a, s, _: u.emu_stop() if a == RESUMEV else None)
    steps = [0]
    uc.hook_add(UC_HOOK_BLOCK, lambda u, a, s, _: steps.__setitem__(0, steps[0] + s // 4))
    pal = np.array([gb.yuv(c) for c in gb.PALETTE], np.uint8)
    bad = {'photo': 0, 'video': 0, 'normal': 0}
    worst = 0
    for W, H in sorted({tuple(v[1]) for v in SIZES.values()} | {tuple(gb.SIZE[1])}, reverse=True):
        emu_cave.W = W
        ycc = np.asarray(photo.resize((W, H), Image.BILINEAR).convert('YCbCr'))
        want = np.repeat(np.repeat(pal[shades(ycc[..., 0])], gb.BLK, 0), gb.BLK, 1)        # (H, W, 3) Y, U, V
        uc.mem_write(emu_cave.CFG_MODE, bytes([GB_MODE]))
        n = {'photo': 0, 'video': 0}
        for top in range(0, H - H % 64, 64):
            for kind in ('photo', 'video'):
                steps[0] = 0
                run_strip(uc, sym, kind, emu_cave.pack(ycc[top:top + 64]), W)
                Y, UV = emu_cave.unpack(bytes(uc.mem_read(emu_cave.STRIP_A, W * 3 // 2 * 64)))
                w = want[top:top + 64]
                n[kind] += int((Y != w[..., 0]).sum() + (UV != w[::2, ::2, 1:]).sum())
                worst = max(worst, steps[0])
        for kind in n:
            bad[kind] += n[kind]
        # the normal mode: both hooks leave the strip exactly as it came
        uc.mem_write(emu_cave.CFG_MODE, bytes([NORMAL_MODE]))
        for kind in ('photo', 'video'):
            strip = emu_cave.pack(ycc[:64])
            run_strip(uc, sym, kind, strip, W)
            bad['normal'] += sum(a != b for a, b in zip(bytes(uc.mem_read(emu_cave.STRIP_A, len(strip))), strip))
        print(f'{W}x{H}: GB differing bytes photo {n["photo"]}, video {n["video"]}')
    print(f'differing bytes: photo {bad["photo"]}, video {bad["video"]}; normal mode (strips changed) {bad["normal"]}; '
          f'up to {worst / 1e3:.0f}k instructions per strip (~{worst / 310e3:.2f} ms at 310 MIPS)')
    sys.exit(1 if any(bad.values()) else 0)


if __name__ == '__main__':
    main()
