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
python3 tools/patch_res.py "$ORIG" CAMERA.wav build/kick_11k.wav "$OUT"
python3 tools/patch_res.py "$OUT" POWERON_AUDIO.wav build/coin_11k.wav "$OUT"

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
PHOTO43_JUMP=$(asm photo43_jump 0xf74c 0xf750)
HOOK_JUMP=$(asm hook_jump 0x15448 0x1544c)
CAVE=$(asm photo_cave 0xbab6c 0xbb200)      # dead FUN_000bab6c
python3 tools/patch_code.py "$OUT" "$OUT" \
    "$PHOTO43_JUMP" "$HOOK_JUMP" "$CAVE" \
    0xf3dc:c4f70000:4cf70000 \
    0xf3fc:60f70000:4cf70000 \
    0xf400:74f70000:4cf70000
