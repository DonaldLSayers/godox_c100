#!/usr/bin/env python3
"""Run the transparent-display (HT1621 segment LCD) code in an ARM emulator.

Loads the factory firmware, hooks the GPIO write routine (FUN_000433f4) and
decodes what goes out on CS=0x28 / WR=0x29 / DATA=0x2a back into HT1621
commands and RAM writes, so the segment map in docs/c100-firmware.md comes
from the real code rather than from the decompiler.

With a build that has the preset code on the display (LCDTAG=1, e.g.
build/GP_CARDVR_UPGRADE.BIN) it also runs that feature end to end: the
display picks and shows a preset on the SS cells, a capture uses it and picks
the next one, recording shows the preset in use, everything outside the SS
cells matches the factory refresh, and the readout state is fully stock.

Usage: uv run --with unicorn tools/emu_seg.py [FIRMWARE.BIN]
"""
import os, subprocess, struct, sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP)

FW = sys.argv[1] if len(sys.argv) > 1 else 'build_backups/v001_original.bin'
APP = 0x10200                       # file offset of RAM address 0
CS, WR, DATA = 0x28, 0x29, 0x2a
GPIO_WRITE = 0x433f4
STUBS = {0x43314, 0x4352c, 0x43468,  # GPIO direction / pull setup
         0x48990, 0x49d48,           # busy-wait delays
         0x53758}                    # printf
SHADOW, NIB = 0x1240e0, 25          # firmware's copy of the HT1621 RAM
LOGO_FLAG = 0xf187e                 # 1 = sensor preview init failed
STACK, RET = 0xf00000, 0xfffff0
MALLOC, HEAP = 0x5374c, 0x800000    # pvPortMalloc, for lut_fill's table


class Ht1621:
    """Rebuild HT1621 frames from the bit-banged pins."""
    def __init__(self):
        self.pins = {CS: 1, WR: 1, DATA: 1}
        self.bits, self.ram, self.cmds, self.writes = [], [0] * 32, [], []

    def gpio(self, pin, val):
        old = self.pins.get(pin)
        self.pins[pin] = val
        if pin == WR and old == 0 and val == 1 and self.pins[CS] == 0:
            self.bits.append(self.pins[DATA])
        elif pin == CS and old == 0 and val == 1:
            self.frame(self.bits)
            self.bits = []

    def frame(self, b):
        num = lambda bits: int(''.join(map(str, bits)), 2)
        if b[:3] == [1, 0, 0]:
            self.cmds.append(num(b[3:11]))
        elif b[:3] == [1, 0, 1]:
            addr, rest = num(b[3:9]), b[9:]
            while len(rest) >= 4:   # D0 (COM0) is sent first; store as nibble bit 3
                self.ram[addr] = num(rest[:4])
                self.writes.append((addr, self.ram[addr]))
                addr, rest = addr + 1, rest[4:]
        else:
            raise ValueError(f'unknown HT1621 frame {b}')


def machine():
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0, 0x1000000)
    uc.mem_write(0, open(FW, 'rb').read()[APP:APP + 0x200000])
    uc.mem_write(SHADOW, bytes(NIB))
    lcd = Ht1621()
    unknown = set()

    def on_code(uc, addr, size, _):
        if addr == RET:
            uc.emu_stop()
        elif addr == GPIO_WRITE:
            lcd.gpio(uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1) & 1)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr in STUBS:
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif addr == MALLOC:
            uc.reg_write(UC_ARM_REG_R0, HEAP)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    uc.hook_add(UC_HOOK_CODE, on_code)
    return uc, lcd


def call(uc, entry, *args, count=5_000_000):
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    for r, v in zip(regs, args):
        uc.reg_write(r, v & 0xffffffff)
    uc.reg_write(UC_ARM_REG_SP, STACK)
    uc.reg_write(UC_ARM_REG_LR, RET)
    uc.emu_start(entry, 0xffffffff, count=count)


def shadow(uc):
    return list(uc.mem_read(SHADOW, NIB))


def lit(ram):
    """Set of (address, COM) for every lit segment; nibble bit 3 = COM0."""
    return {(a, c) for a in range(NIB) for c in range(4) if ram[a] >> (3 - c) & 1}


def fmt(segs):
    return ' '.join(f'{a:02x}.{c}' for a, c in sorted(segs)) or '-'


if __name__ == '__main__':
    uc, lcd = machine()

    # Boot: HT1621 init as called by the display task at 0xe0dc.
    call(uc, 0x4ad68)
    print('init commands:', ' '.join(f'{c:02x}' for c in lcd.cmds))
    print('after init lit:', fmt(lit(lcd.ram)))
    assert lcd.ram[:NIB] == shadow(uc), 'shadow RAM and panel disagree'

    # Logo helper 0x4a64c(on).
    for on in (0, 1):
        call(uc, 0x4a64c, on)
        print(f'logo helper({on}): lit {fmt(lit(lcd.ram))}')

    # Mode/logo routine FUN_0004a670(arg) with the sensor-failed flag 0 and 1.
    for flag in (0, 1):
        for arg in (0, 1):
            call(uc, 0x4a64c, 1)                     # start from the boot state
            uc.mem_write(LOGO_FLAG, bytes([flag]))
            call(uc, 0x4a670, arg)
            print(f'FUN_0004a670({arg}) sensor_failed={flag}: nibble 0x16 = {lcd.ram[0x16]:x}')
    uc.mem_write(LOGO_FLAG, b'\0')

    # Aspect marker FUN_0004a7f4(hide, aspect).
    for hide in (0, 1):
        for asp in range(6):
            call(uc, 0x4a7f4, hide, asp)
            on = {s for s in lit(lcd.ram) if s[0] in (0x06, 0x15)}
            print(f'aspect({hide},{asp}): {fmt(on)}')

    # Digit routines: each digit 0..9 (10 = blank) should light the usual
    # 7-segment count, and the segments used should form one 7-segment cell.
    SEVEN = [6, 2, 5, 5, 4, 5, 6, 3, 7, 6]
    digits = {'FUN_00049ea8 (0,1,2)': (0x49ea8, (0, 1, 2, 0, 0)),
              'FUN_00049ea8 (3,4,5)': (0x49ea8, (3, 4, 5, 0, 0)),
              'FUN_0004a4ec (7,8,9)': (0x4a4ec, (0,)),
              'FUN_0004a074 (9,a,b)': (0x4a074, (9, 10, 11, 0)),
              'FUN_0004a374 (d,e,f)': (0x4a374, (0,)),
              'FUN_0004a1f0 (f,10,11)': (0x4a1f0, (0, 0)),
              'FUN_0004a074 (11,12,13)': (0x4a074, (0x11, 0x12, 0x13, 0))}
    fonts = {}
    for name, (entry, rest) in digits.items():
        counts, used, patterns = [], set(), []
        for dgt in range(11):
            uc.mem_write(SHADOW, bytes(NIB))
            call(uc, 0x4ad30)                        # clear the panel
            call(uc, entry, dgt, *rest)
            segs = lit(lcd.ram)
            counts.append(len(segs))
            used |= segs
            patterns.append(segs)
        ok = counts[:10] == SEVEN or counts[:10] == [6, 2, 5, 5, 4, 5, 6, 4, 7, 6]
        print(f'{name}: counts {counts} -> {"7-seg" if ok and counts[10] == 0 else "??"}, cell {fmt(used)}')
        fonts[name] = (used, {frozenset(p): (str(dg) if dg < 10 else "_") for dg, p in enumerate(patterns)})

    # Whole periodic refresh FUN_00021318 with the manual-exposure tables
    # (flags set so ISO/F/SS come from the tables, not the live meter).
    CFG = 0x132160
    def refresh(state, aspect, iso, f_idx, ss_idx, battery_adc=0x400):
        uc.mem_write(SHADOW, bytes(NIB)); call(uc, 0x4ad30)
        uc.mem_write(0x121706, bytes([state]))      # UI state
        uc.mem_write(0x1217be, b'\1')               # past the 5 startup ticks
        uc.mem_write(0x1217b0, b'\1')               # this tick does mode/aspect/battery
        uc.mem_write(CFG + 0xf, bytes([aspect]))
        uc.mem_write(0xe3279, b'\1'); uc.mem_write(CFG + 0xec, struct.pack('<H', iso))
        uc.mem_write(0xe3278, b'\1'); uc.mem_write(CFG + 0xeb, bytes([f_idx]))
        uc.mem_write(0x12170b, b'\1'); uc.mem_write(CFG + 0xea, bytes([ss_idx]))
        call(uc, 0x21318)
        return lit(lcd.ram)
    def read(segs):
        """Digits shown in each cell, plus the lit segments outside any cell."""
        out, rest = [], set(segs)
        for name, (cell, font) in fonts.items():
            out.append(font.get(frozenset(segs & cell), ' ' if not segs & cell else '?'))
            rest -= cell
        return ''.join(out), rest
    for state in (0, 1, 2):
        segs = refresh(state, 1, 400, 15, 11)       # ISO 400, F5.6, SS 1/25
        dg, rest = read(segs)
        print(f'refresh state={state} aspect=1 ISO400 F5.6 SS1/25: digits [{dg}] other {fmt(rest)}')
    for iso, fi, si, label in [(200, 15, 11, 'ISO200 F5.6 SS1/25'), (1600, 9, 18, 'ISO1600 F2.8 SS1/125'),
                               (100, 21, 21, 'ISO100 F11 SS1/250'), (400, 9, 27, 'ISO400 F2.8 SS1/1000'), (3200, 12, 36, 'ISO3200 F4.0 SS1/8000')]:
        dg, rest = read(refresh(2, 1, iso, fi, si))
        print(f'  state=2 {label}: digits [{dg}] other {fmt(rest)}')
    for state in (0, 2):
        for asp in (1, 2, 3, 4):
            segs = refresh(state, asp, 400, 15, 11)
            print(f'  state={state} aspect={asp}: 06.0={int((6,0) in segs)} 15.x={fmt({s for s in segs if s[0]==0x15})}')

    # Boot sequence: HT1621 init, then the periodic refresh from a cold start
    # (startup counter 0x12170c, skip flag 0x1217be, tick counter 0x1217b0 all 0).
    uc2, lcd2 = machine()
    call(uc2, 0x4ad68)
    for addr, val in [(0x121706, 2), (0x1217be, 0), (0x12170c, 0), (0x1217b0, 0), (CFG + 0xf, 1),
                      (0xe3279, 1), (0xe3278, 1), (CFG + 0xeb, 15), (0x12170b, 1), (CFG + 0xea, 11)]:
        uc2.mem_write(addr, bytes([val]))
    uc2.mem_write(CFG + 0xec, struct.pack('<H', 200))
    uc, lcd = uc2, lcd2                              # read() uses the fonts only
    print('boot: after init', fmt(lit(lcd2.ram)))
    for tick in range(1, 9):
        call(uc2, 0x21318)
        dg, rest = read(lit(lcd2.ram))
        print(f'boot: refresh {tick}: logo={"on " if (0x16, 1) in lit(lcd2.ram) else "off"} '
              f'digits [{dg}] other {fmt(rest - {(0x16, 1)})}')

    # ---- Preset code on the display (builds with LCDTAG=1) ----
    word = struct.unpack('<I', open(FW, 'rb').read()[APP + 0x21218:APP + 0x2121c])[0]
    if word >> 24 == 0xea and 0xbc400 <= (0x21218 + 8 + (word & 0xffffff) * 4) & 0xffffffff < 0xbc744:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import palettes
        nm = next(p for p in ('/opt/homebrew/opt/llvm/bin/llvm-nm', '/opt/homebrew/opt/llvm@18/bin/llvm-nm')
                  if os.path.exists(p))
        syms = {f[2]: int(f[0], 16) for f in map(str.split, subprocess.run(
            [nm, 'build/obj/photo_cave.o'], capture_output=True, text=True, check=True).stdout.splitlines())
            if len(f) == 3}
        VARS, LUT_FILL = syms['VARS'], syms['lut_fill']
        PAL_IDX, NEXT_IDX = VARS + 8, VARS + 16
        TICK, REC_FLAGS = 0x126b80, 0x132abb
        tags = [palettes.lcd_text(t) for t, _, _ in palettes.presets()]
        SS = set(range(palettes.SS_FIRST, palettes.SS_FIRST + palettes.SS_COUNT))

        def shown(segs):
            """The three characters on the SS cells."""
            text = ''
            for cell in palettes.SS_CELLS:
                on = {seg for seg, ac in cell.items() if ac in segs}
                text += next((ch for ch, ss in palettes.SEG7.items() if set(ss) == on), '?' if on else ' ')
            return text

        def run(fw_uc, lcd_, state, rec=0):
            for addr, val in [(0x121706, state), (0x1217be, 1), (0x1217b0, 1), (REC_FLAGS, rec),
                              (0xe3279, 1), (CFG + 0xeb, 15), (0x12170b, 1), (CFG + 0xea, 11)]:
                fw_uc.mem_write(addr, bytes([val]))
            fw_uc.mem_write(CFG + 0xec, struct.pack('<H', 400))
            call(fw_uc, 0x21318)
            return lit(lcd_.ram)

        FW_STOCK = FW
        FW = 'build_backups/v001_original.bin'
        stock_uc, stock_lcd = machine()               # the factory refresh, for comparison
        FW = FW_STOCK
        uc, lcd = machine()
        word32 = lambda a: struct.unpack('<I', uc.mem_read(a, 4))[0]
        def tick_refresh(state, rec=0):
            segs = run(uc, lcd, state, rec)
            stock = run(stock_uc, stock_lcd, state, rec)
            outside = {sg for sg in segs ^ stock if sg[0] not in SS}
            return segs, outside

        uc.mem_write(TICK, struct.pack('<I', 0x1234))
        ok = True
        def check(label, got, want):
            global ok
            ok &= got == want
            print(f'code: {label}: {got!r} (want {want!r}){"" if got == want else "  <-- FAIL"}')

        segs, outside = tick_refresh(0)
        nxt = word32(NEXT_IDX)
        check('photo mode, first refresh shows NEXT', shown(segs), tags[nxt])
        check('photo mode, everything outside the SS cells as stock', outside, set())
        for n in range(4):                           # four captures
            uc.mem_write(TICK, struct.pack('<I', 0x1234 + 37 * (n + 1)))
            before = word32(NEXT_IDX)
            call(uc, LUT_FILL, count=400_000_000)
            cur, nxt = word32(PAL_IDX), word32(NEXT_IDX)
            check(f'capture {n + 1} uses the shown preset', cur, before)
            check(f'capture {n + 1} next differs from current', nxt != cur and nxt < len(tags), True)
            check(f'capture {n + 1} display shows the next one', shown(tick_refresh(0)[0]), tags[nxt])
        segs, outside = tick_refresh(1)
        check('video mode, idle shows NEXT', shown(segs), tags[word32(NEXT_IDX)])
        check('video mode, everything outside the SS cells as stock', outside, set())
        segs, outside = tick_refresh(1, rec=2)
        check('video mode, recording shows the preset in use', shown(segs), tags[word32(PAL_IDX)])
        check('video mode recording, outside the SS cells as stock', outside, set())
        segs = run(uc, lcd, 2)
        check('readout state exactly as stock (ISO 400, F5.6, SS 1/25): differing', fmt(segs ^ run(stock_uc, stock_lcd, 2)), '-')
        print('code test', 'PASSED' if ok else 'FAILED')
        sys.exit(0 if ok else 1)
