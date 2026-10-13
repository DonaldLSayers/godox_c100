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
    $LLVM/llvm-objcopy -O binary "build/obj/$1.o" "build/obj/$1.bin"
    python3 -I -c "
import sys
start, end = int(sys.argv[3], 0), int(sys.argv[4], 0)
new = open(sys.argv[1], 'rb').read()[start:]
old = open(sys.argv[2], 'rb').read()[start + 0x10200:end + 0x10200]
assert len(new) <= len(old), 'patch too big'
new += old[len(new):]
print(f'{start:#x}:{old.hex()}:{new.hex()}')
" "build/obj/$1.bin" "$ORIG" "$2" "$3"
}

# --- code patches ---
PHOTO43=$(asm photo43_320x240 0xf74c 0xf788)
python3 tools/patch_code.py "$OUT" "$OUT" \
    "$PHOTO43" \
    0xf3dc:c4f70000:4cf70000 \
    0xf3fc:60f70000:4cf70000 \
    0xf400:74f70000:4cf70000
