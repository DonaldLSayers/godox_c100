#!/bin/sh
# Rebuild build/GP_CARDVR_UPGRADE.BIN from the original firmware:
# custom sounds + code patches. Edit the lists below to change what goes in.
set -e
cd "$(dirname "$0")/.."
LLVM=/opt/homebrew/opt/llvm/bin
ORIG=c100_v1.1.6_20260929/GP_CARDVR_UPGRADE.BIN
OUT=build/GP_CARDVR_UPGRADE.BIN
mkdir -p build/obj

# --- sounds ---
# SILENT=1 makes the shutter and power-on silent (same slots, zeroed samples).
#   SILENT=1 sh tools/build.sh   -> no sounds
#   sh tools/build.sh            -> Super Mario kick / coin sounds
SILENT=${SILENT:-0}
if [ "$SILENT" = "1" ]; then
    python3 -I tools/mk_silence.py build/kick_11k.wav build/silent_cam.wav
    python3 -I tools/mk_silence.py build/coin_11k.wav build/silent_pwr.wav
    python3 tools/patch_res.py "$ORIG" CAMERA.wav build/silent_cam.wav "$OUT"
    python3 tools/patch_res.py "$OUT" POWERON_AUDIO.wav build/silent_pwr.wav "$OUT"
else
    python3 tools/patch_res.py "$ORIG" CAMERA.wav build/kick_11k.wav "$OUT"
    python3 tools/patch_res.py "$OUT" POWERON_AUDIO.wav build/coin_11k.wav "$OUT"
fi

# BEEP.wav (the UI/focus beep) is always silenced, in both sound profiles.
python3 tools/gp_res.py "$ORIG" build/res >/dev/null
python3 -I tools/mk_silence.py build/res/BEEP.wav build/beep_silent.wav
python3 tools/patch_res.py "$OUT" BEEP.wav build/beep_silent.wav "$OUT"

# --- assemble a patch: prints ADDR:OLDHEX:NEWHEX for patch_code.py ---
asm() {  # asm NAME START END
    $LLVM/llvm-mc -triple=armv5te-none-eabi -filetype=obj "tools/patches/$1.s" -o "build/obj/$1.o"
    if $LLVM/llvm-readobj -r "build/obj/$1.o" | grep -q R_ARM; then
        echo "$1: unresolved relocation (use 'mov lr, pc; b X' instead of 'bl X')" >&2; exit 1
    fi
    $LLVM/llvm-objcopy -O binary "build/obj/$1.o" "build/obj/$1.bin"
    python3 -I -c "
import sys
start, end = int(sys.argv[3], 0), int(sys.argv[4], 0)
blob = open(sys.argv[1], 'rb').read()
assert len(blob) <= end, f'{sys.argv[1]}: code runs past {end:#x} (ends at {len(blob):#x})'
new = blob[start:end]
old = open(sys.argv[2], 'rb').read()[start + 0x10200:end + 0x10200]
new += old[len(new):]
print(f'{start:#x}:{old.hex()}:{new.hex()}')
" "build/obj/$1.bin" "$ORIG" "$2" "$3"
}

# --- code patches ---
HOOK_JUMP=$(asm hook_jump 0x15448 0x1544c)
CYC_JUMP=$(asm cyc_jump 0x187c4 0x187c8)     # per-photo palette advance
CAVE=$(asm photo_cave 0xbab6c 0xbb340)      # dead FUN_000bab6c
# Resolution jump table @0xf3d0 (ldrls pc,[pc,idx,lsl#2] @0xf3c8): entries hold
# absolute handler addresses, so point each photo aspect ratio straight at its
# cave stub. 0/1=16:9 1920, 2=3:2 1616, 3=4:3 1440, 4=1:1 1024; b/c = hi-res.
python3 tools/patch_code.py "$OUT" "$OUT" \
    "$HOOK_JUMP" "$CYC_JUMP" "$CAVE" \
    0xf3d0:9cf70000:40b10b00 \
    0xf3d4:9cf70000:40b10b00 \
    0xf3d8:b0f70000:80b10b00 \
    0xf3dc:c4f70000:80b00b00 \
    0xf3e0:d4f60000:c0b10b00 \
    0xf3fc:60f70000:80b00b00 \
    0xf400:74f70000:80b00b00
