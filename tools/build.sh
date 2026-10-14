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
# SILENT=1 makes the shutter, power-on and mode-switch click silent (same slots,
# zeroed samples) AND never switches the speaker amplifier on (see SPK_PATCHES
# below), so there is no amp hiss either.
#   SILENT=1 sh tools/build.sh   -> no sounds, speaker amp stays off
#   sh tools/build.sh            -> Super Mario kick / coin sounds
SILENT=${SILENT:-0}
python3 tools/gp_res.py "$ORIG" build/res >/dev/null
if [ "$SILENT" = "1" ]; then
    python3 -I tools/mk_silence.py build/kick_11k.wav build/silent_cam.wav
    python3 -I tools/mk_silence.py build/coin_11k.wav build/silent_pwr.wav
    python3 -I tools/mk_silence.py build/res/CLICK.wav build/click_silent.wav
    python3 tools/patch_res.py "$ORIG" CAMERA.wav build/silent_cam.wav "$OUT"
    python3 tools/patch_res.py "$OUT" POWERON_AUDIO.wav build/silent_pwr.wav "$OUT"
    python3 tools/patch_res.py "$OUT" CLICK.wav build/click_silent.wav "$OUT"
else
    python3 tools/patch_res.py "$ORIG" CAMERA.wav build/kick_11k.wav "$OUT"
    python3 tools/patch_res.py "$OUT" POWERON_AUDIO.wav build/coin_11k.wav "$OUT"
fi

# BEEP.wav (the UI/focus beep) is always silenced, in both sound profiles.
python3 -I tools/mk_silence.py build/res/BEEP.wav build/beep_silent.wav
python3 tools/patch_res.py "$OUT" BEEP.wav build/beep_silent.wav "$OUT"

# Speaker amplifier = GPIO 0x2c, driven by gpio_write FUN_000433f4(pin, level).
# Sound playback FUN_00022a80 switches it on, waits 100 ms, then queues the WAV;
# the peripheral task (FUN_00021e60, ~1 s tick) only switches it off again on
# its 2nd tick after that, so every sound gives ~1-2 s of amp hiss even when
# the WAV is silent. With SILENT=1 the "on" calls become NOPs (pure pin writes,
# return value unused), so the amp is never powered:
#   0x22b38  FUN_00022a80, every UI sound (shutter, click, power-on, beep)
#   0x350f0  state_startup_init, unconditional "on" at boot
#   0x2ed50  photo state, the remaining "on"
SPK_PATCHES=""
if [ "$SILENT" = "1" ]; then
    SPK_PATCHES="0x22b38:2d8200eb:0000a0e1 0x350f0:bf3800eb:0000a0e1 0x2ed50:a75100eb:0000a0e1"
fi

# --- look knobs (applied to each block's brightness before palette matching) ---
# CONTRAST: percent, 100 = neutral. Higher = more dramatic (spreads midtones to
#   the palette's dark/bright ends, good for flat/dim scenes); lower = softer.
#   Useful range ~70..160 (e.g. CONTRAST=130 punchy, CONTRAST=85 gentle).
# BRIGHT: luma offset, 0 = neutral. Positive lifts (lighter), negative darkens.
#   Useful range ~ -60..60 (full -128..127).
#   e.g.  CONTRAST=130 BRIGHT=10 sh tools/build.sh
CONTRAST=${CONTRAST:-100}
BRIGHT=${BRIGHT:-0}
CFIX=$(( CONTRAST * 128 / 100 ))   # contrast in /128 fixed point (128 = neutral)
BFIX=$(( BRIGHT + 128 ))           # bias so the assembler never sees a negative

# --- assemble a patch: prints ADDR:OLDHEX:NEWHEX for patch_code.py ---
asm() {  # asm NAME START END [extra llvm-mc args, e.g. --defsym=X=1]
    name=$1 start=$2 end=$3; shift 3
    $LLVM/llvm-mc -triple=armv5te-none-eabi --defsym=CONTRAST_FIX=$CFIX --defsym=BRIGHT_FIX=$BFIX \
        -I build/obj "$@" -filetype=obj "tools/patches/$name.s" -o "build/obj/$name.o"
    set -- "$name" "$start" "$end"
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
# Palette table from tools/palettes.py, included by photo_cave.s.
python3 -I tools/palettes.py asm > build/obj/palettes.inc
CAVE=$(asm photo_cave 0xbab6c 0xbb340)      # dead FUN_000bab6c
sym() {  # address of a label in the assembled cave
    $LLVM/llvm-nm build/obj/photo_cave.o | awk -v s="$1" '$3 == s { print "0x" $1 }'
}
HOOK_JUMP=$(asm hook_jump 0x15448 0x1544c --defsym=HOOK=$(sym hook))
CYC_JUMP=$(asm cyc_jump 0x187c4 0x187c8 --defsym=STUB=$(sym idx_stub))  # per-photo palette + table
# Video frame diagnostics (VIDDIAG=1): hook FUN_00018d14 (frame -> H.264
# encoder) into a second cave in dead code at 0xbb774-0xbc744 (unreferenced
# functions FUN_000bb774..FUN_000bc19c; see tools/patches/video_cave.s).
VIDDIAG=${VIDDIAG:-0}
VDIAG_PATCHES=""
if [ "$VIDDIAG" = "1" ]; then
    VCAVE=$(asm video_cave 0xbb774 0xbc744)
    VHOOK=$(asm vhook_jump 0x18d14 0x18d18 --defsym=HOOK=$($LLVM/llvm-nm build/obj/video_cave.o | awk '$3 == "vhook" { print "0x" $1 }'))
    VDIAG_PATCHES="$VCAVE $VHOOK"
fi
# Resolution jump table @0xf3d0 (ldrls pc,[pc,idx,lsl#2] @0xf3c8): entries hold
# absolute handler addresses, so point each photo aspect ratio straight at its
# cave stub. 0/1=16:9 1920, 2=3:2 1616, 3=4:3 1440, 4=1:1 1024; b/c = hi-res.
jt() {  # jt ENTRY OLDHEX LABEL -> ENTRY:OLDHEX:<label address, little-endian>
    printf '%s:%s:%s\n' "$1" "$2" "$(python3 -I -c "import sys; print(int(sys.argv[1], 0).to_bytes(4, 'little').hex())" "$(sym "$3")")"
}
# Video resolution jump table @0xf0a0 (ldrls pc,[pc,idx,lsl#2] @0xf098), same
# scheme as the photo one; video follows the camera's aspect setting:
# 0/1/9 = 16:9 1920, 2 = 3:2 1616, 3 = 4:3 1440, 4 = 1:1 1024, all -> 640 wide.
# SMALLVID=0 keeps the stock full-size video.
SMALLVID=${SMALLVID:-1}
VID_PATCHES=""
if [ "$SMALLVID" = "1" ]; then
    VID_PATCHES="$(jt 0xf0a0 f8f50000 vid169) $(jt 0xf0a4 f8f50000 vid169) $(jt 0xf0c4 f8f50000 vid169)
        $(jt 0xf0a8 a8f60000 vid32) $(jt 0xf0ac 88f60000 vid43) $(jt 0xf0b0 98f60000 vid11)"
fi
python3 tools/patch_code.py "$OUT" "$OUT" \
    "$HOOK_JUMP" "$CYC_JUMP" "$CAVE" $VDIAG_PATCHES \
    "$(jt 0xf3d0 9cf70000 stub169)" \
    "$(jt 0xf3d4 9cf70000 stub169)" \
    "$(jt 0xf3d8 b0f70000 stub32)" \
    "$(jt 0xf3dc c4f70000 photo43)" \
    "$(jt 0xf3e0 d4f60000 stub11)" \
    "$(jt 0xf3fc 60f70000 photo43)" \
    "$(jt 0xf400 74f70000 photo43)" \
    $VID_PATCHES \
    $SPK_PATCHES
