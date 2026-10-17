#!/usr/bin/env python3
"""Run the built video cave in an ARM emulator and check it against the sim.

Like emu_cave.py (whose strip packing and comparison it reuses), but for the
video hook (tools/patches/video_cave.s, build with VIDFX=1): each call of
FUN_00018d14 gets one 64-row strip in the photo strip layout. Checks that
  1. the first strip of a recording (>= 500 ms since the last one) picks a
     palette and fills the table, and every 2x2 block is exactly the palette
     colour sim_palette.py picks, with the palette tag on the first strip of
     every frame (a new timestamp argument) and nowhere else;
  2. the next strip, 8 ms later, reuses the table (no second allocation);
  3. a strip after a 1 s gap starts a new recording with a different palette;
  4. with VIDTIMING=1, the top 4 rows x < 256 are the timing bar (all black
     here: the emulated clock does not advance during the hook);
  5. the hook restores r0-r12/lr and resumes at 0x18d18 with r3 = venc[0].

Usage: uv run --with unicorn,numpy,pillow tools/emu_video.py PHOTO.jpg [--timing]
  (--timing for a VIDTIMING=1 build)
"""
import struct, sys
import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
from emu_cave import FW, APP, CACHE_INV, CACHE_CLEAN, MALLOC, TICK, W, ROWS, pack, symbols, unpack
from palettes import LUT, WY, presets
from sim_palette import add_tag, match, prepare
from emu_cave import differing

RESUME = 0x18d18
VENC, STRIP, HEAP, STACK = 0x131490, 0x3e9a00, 0x800000, 0xf00000   # STRIP: a pool buffer, untagged
STRIDE = W * 3 // 2
SAVED = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
         UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12,
         UC_ARM_REG_LR]


def machine():
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0, 0x1000000)
    uc.mem_write(0, open(FW, 'rb').read()[APP:APP + 0x200000])
    venc = bytearray(0x200)
    struct.pack_into('<I', venc, 0, 1)
    venc[0x101] = 0x23
    struct.pack_into('<I', venc, 8, STRIP | 0x30000000)
    struct.pack_into('<I', venc, 0xdc, W)
    uc.mem_write(VENC, bytes(venc))
    calls = []

    def on_code(uc, addr, size, _):
        if addr in (CACHE_INV, CACHE_CLEAN, MALLOC):
            calls.append({CACHE_INV: 'inv', CACHE_CLEAN: 'clean', MALLOC: 'malloc'}[addr])
            if addr == MALLOC:
                uc.reg_write(UC_ARM_REG_R0, HEAP)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr == RESUME:
            uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, on_code)
    return uc, calls


def run_strip(uc, entry, tick, ts=0x1004):
    uc.mem_write(TICK, struct.pack('<I', tick))
    regs = {r: 0x1000 + 4 * i for i, r in enumerate(SAVED)}
    regs[UC_ARM_REG_R0] = VENC
    regs[UC_ARM_REG_R1] = ts
    for r, v in regs.items():
        uc.reg_write(r, v)
    uc.reg_write(UC_ARM_REG_SP, STACK)
    uc.emu_start(entry, 0xffffffff, count=200_000_000)
    assert uc.reg_read(UC_ARM_REG_PC) == RESUME, 'did not resume at 0x18d18'
    assert all(uc.reg_read(r) == v for r, v in regs.items()), 'registers not restored'
    assert uc.reg_read(UC_ARM_REG_R3) == 1, 'r3 != venc[0]'


def main():
    photo, timing = sys.argv[1], '--timing' in sys.argv[2:]
    psym, vsym = symbols(), symbols('build/obj/video_cave.o')
    pre = presets()
    src = prepare(photo, W)
    uc, calls = machine()
    uc.mem_write(0x132160 + 0xf1, bytes([len(pre)]))   # mode byte = rnd: a new preset per recording
    worst, last_idx = 0, None
    #        label           tick  timestamp  photo row  tag expected
    steps = (('new recording', 1000, 0x100, 0, True), ('next strip', 1008, 0x100, 64, False),
             ('next frame', 1016, 0x121, 200, True), ('next strip', 1024, 0x121, 264, False),
             ('new recording', 2100, 0x500, 0, True), ('next strip', 2108, 0x500, 300, False))
    for label, tick, ts, top, tagged in steps:
        crop = src.crop((0, top, W, top + ROWS))
        uc.mem_write(STRIP, pack(np.asarray(crop.convert('YCbCr'))))
        calls.clear()
        run_strip(uc, vsym['vhook'], tick, ts)
        idx = struct.unpack('<I', uc.mem_read(psym['VARS'] + 8, 4))[0]
        tag, P, D = pre[idx]
        Y, UV = unpack(bytes(uc.mem_read(STRIP, STRIDE * ROWS)))
        ref = match(crop, P, wy=WY, lut=LUT)
        if tagged:
            add_tag(ref, tag, D)
        bar = np.zeros(ref.shape, bool)
        if timing:
            bar[:2, :128] = True
            assert (Y[:4, :256] == 16).all() and (UV[:2, :128] == 128).all(), 'timing bar wrong'
        diff = differing(Y, UV, np.array(D)[ref])[~bar].mean() * 100
        worst = max(worst, diff)
        if label == 'new recording':
            assert last_idx is None or idx != last_idx, 'new recording kept the preset'
        else:
            assert idx == last_idx and 'malloc' not in calls, 'table rebuilt mid-recording'
        last_idx = idx
        print(f'tick {tick:5} {label:13}: preset {idx} {tag} ({len(P)} colours), '
              f'{"tag, " if tagged else ""}blocks differing from sim {diff:.2f}%, calls {calls}'
              f'{", timing bar ok" if timing else ""}')
    print('max difference', worst)


if __name__ == '__main__':
    main()
