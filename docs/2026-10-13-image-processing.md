# Godox C100 firmware hacking — image processing

_Started 2026-10-13, updated 2026-10-14._

Goal: make the C100 produce pixel-art photos in the spirit of the
[Pixless camera](https://petapixel.com/2025/01/09/0-03-megapixel-pixless-camera-captures-charming-pixel-art-photos/) —
small resolution, a limited colour palette, and dithering. All of that now
works on the device, including true nearest-palette colour matching, a palette
that changes every photo, and every aspect ratio.

## The device

- Chip: **GeneralPlus GP22B** (ARM926-class, little-endian ARMv5TE, runs FreeRTOS).
- Sensor: **GalaxyCore GC2083** (1080p).
- Storage: SPI flash; photos/updates on the microSD (TF) card, FAT32/exFAT.
- Firmware update: copy `GP_CARDVR_UPGRADE.BIN` to the SD card root, restart,
  wait for the LED to stop flashing. The updater checks only a 4-byte magic —
  **no checksum, no signature** — so modified firmware is accepted.

## Firmware image layout (`GP_CARDVR_UPGRADE.BIN`, v1.1.6)

| File offset | Contents |
|---|---|
| `0x00000` | bootloader + `PGpssiipps` header (no SD-update code here) |
| `0x10000` | app header `GPCODEROM` |
| `0x10200` | **app code**, loaded at **RAM 0x0** (so `file offset = addr + 0x10200`) |
| `0x170000` | resource table (sounds, logos, fonts), 512-byte-sector offsets |

The SD updater lives in the app, so a patch that still boots and still reaches
the SD-card check is always recoverable by re-flashing a good build. Only
breaking the boot path or the updater itself would remove SD recovery.

## Tooling (in `tools/`)

- `gp_res.py` — list/extract the resource table.
- `patch_res.py` — replace a resource (e.g. a WAV) in place, format- and
  size-checked.
- `mk_silence.py` — make a silent copy of a WAV (same header/size, data zeroed).
- `patch_code.py` — apply byte patches addressed by RAM address; refuses to
  touch the bootloader or the SD-updater, and verifies the original bytes first.
- `build.sh` — **rebuild `build/GP_CARDVR_UPGRADE.BIN` from the original**:
  applies sounds, then assembles each `tools/patches/*.s` and patches it in.
  Fails if a patch overflows its slot or has an unresolved relocation.
  `SILENT=1 sh tools/build.sh` builds with no sounds; plain `sh tools/build.sh`
  uses the Super Mario kick (shutter) and coin (power-on). The UI/focus beep
  (`BEEP.wav`) is silenced in both.
- `sim_dither.py` — off-camera preview of palette + ordered dithering.

Reverse engineering: Ghidra headless project under `build/ghidra/`, decompiled
C in `decomp/c100.c`, string→function index in `decomp/strings.tsv`
(scripts in `tools/ghidra/`). Raw disassembly via Homebrew `llvm-mc
--disassemble` on bytes sliced from the image.

## Backups (in `build_backups/`)

- `v001_original.bin` — factory v1.1.6.
- `v002_updated_sounds.bin` — + custom shutter / power-on sounds.
- `v003_smaller_image.bin` — + 4:3 photo mode remapped to 320×240.
- `v004_bw.bin` — + clean black & white (320×240). Re-flashed to confirm the
  photo path is fully recoverable.

## The code cave

Two things are patched into the app, both in dead space:

- **Hook point** `FUN_00015448` — the scaler "frame/strip ready" callback,
  registered only for photo capture (runs in interrupt context). Its first
  instruction (`str lr, [sp, #-4]!`) is replaced with a branch to our cave; the
  cave re-runs that instruction and returns to `0x1544c`.
- **Code cave** `FUN_000bab6c` — a ~2 KB function nothing references (verified
  against all B/BL targets and pointers, ARM and Thumb). It holds the pixel
  hook, the per-aspect size stubs, the palette tables, and a few scratch bytes.
- **Per-photo hook** `FUN_000187c4` (capture handler, runs once per photo) — its
  first instruction is replaced with a branch to `idx_stub`, which advances the
  palette index and re-runs the instruction.

> **Lesson, the hard way:** when you intercept the *first* instruction of a
> function and later rejoin it, `r0–r3` still hold that function's live
> arguments. The hook must `push {r0-r11, lr}` / `pop {r0-r11, lr}` — saving only
> `r4-r11` corrupts the callback's arguments and produces non-deterministic
> rainbow noise. A whole "it must be too slow" theory evaporated once this was
> fixed; it was never a performance problem.

## Smaller photos and every aspect ratio

`FUN_0000f004` builds each photo's capture size. The photo resolution switch
dispatches through a jump table at `0xf3d0` (`ldrls pc,[pc,idx,lsl#2]` at
`0xf3c8`) whose entries are **absolute handler addresses**, so each aspect ratio
can be pointed straight at a cave stub:

| case | native | routed to | output |
|---|---|---|---|
| 0, 1 | 1920×1080 (16:9) | `stub169` | 640×360 |
| 2 | 1616×1080 (3:2) | `stub32` | 640×428 |
| 3 | 1440×1080 (4:3) | `photo43` | 640×480 |
| 4 | 1024×1024 (1:1) | `stub11` | 640×640 |

Each stub keeps the **native crop and first-scaler size** and sets only a small
final size, then rejoins the normal photo path at `0xf188`. (The earlier mistake
was setting only the final size, which makes the firmware crop 1:1 instead of
scaling — the crop and first scaler stage must be set too.) Outputs were 320-wide
first; 640-wide is the current setting. Because every output is the same width,
the colour pipeline is unchanged between sizes — only the height differs.

## The pixel hook

The hook modifies pixels after the ISP/scaler produces them but before JPEG.

### Buffer format — decoded from on-camera diagnostics

The scaler delivers the photo in **32-row strips** into a double buffer (strip
A at `PHOTO+0x18`, strip B right after it; `PHOTO = 0x1317ac`). `STRIP_BYTES`
(value at `0x13155c`) `= width × 32 × 3/2`. The pixel format (`PHOTO+0x20`) is
`'"'` (0x22) = **YUV 4:2:0**, laid out **row-interleaved with a parity twist**.
With `stride = width × 3/2` and `third = width/2`, each 2-row band (rows `2b`,
`2b+1`) is:

```
even row:  luma Y [0, 2*third)            chroma pairs 0..third/2-1  [2*third, 3*third)
odd  row:  chroma pairs third/2..third-1  [0, third)   luma Y [third, 3*third)
```

So one **2×2 block** = one chroma (U,V) pair shared by 4 luma samples (2 in the
even row, 2 in the odd). Chroma is U,V interleaved, one pair per 2×2 block. The
hook derives `stride`, `third` and the split point from `STRIP_BYTES`, so it is
width-agnostic (works at 320, 640, …). It does cache maintenance around its
writes (`0x401ac` invalidate, `0x401b8` clean) so the JPEG encoder sees them,
and only ever writes a buffer whose address matches strip A/B — an unexpected
call leaves memory untouched.

Verifying these primitives in isolation (per-row brightness gradient, then five
solid colour bars) before attempting colour matching is what finally made the
colour work predictable: it separated "can we address and write pixels" from
"is the colour maths right."

### Effect: palette dithering (what ships)

Per 2×2 block the hook:

1. averages the block's 4 luma and adds a **4×4 Bayer** ordered-dither offset;
2. reads the block's real U,V;
3. finds the **nearest of 6 palette colours** in full Y+U+V space (Manhattan
   distance) — true nearest-colour matching, not a grayscale ramp;
4. paints the whole block that palette colour (Y to all four luma, U,V to the
   pair).

Per-block is the natural unit in 4:2:0 (one chroma pair per block) and keeps the
work well inside the interrupt budget.

### Palette cycling and a random start

Seven palettes are stored in the cave (riso6, dark sunset, vibrant summer,
fiesta, vibrant nature, bold hues, refreshing), 6 colours each as JPEG YCbCr.

- `idx_stub` advances a one-byte index (`PAL_IDX`) once per photo, wrapping at 7,
  so each shot uses the next palette.
- On the **first strip after boot** the hook seeds `PAL_IDX` from sensor pixel
  noise (sum of a few luma bytes, mod 7) and sets a "seeded" flag, so the cycle
  starts at a different palette each power-on. No persistence needed; it resets
  and re-randomises every boot.

## Sounds

- Shutter (`CAMERA.wav`) and power-on (`POWERON_AUDIO.wav`): custom clips, or
  silent with `SILENT=1`.
- UI/focus beep (`BEEP.wav`): always silenced.

## Timing notes

- Hook cost scales with pixels. 320-wide finishes comfortably; 640-wide is ~4×
  the work (twice the matches per callback, twice as many callbacks). If a size
  ever outruns the per-callback deadline it shows as the **lower part of each
  photo turning to noise while the top is correct** — the cue to optimise the
  matcher or drop back to a smaller size.
- Photos land in `DCIM` as `IMG_xxxx.jpg`.

## Ideas not yet done

- Persist the palette index across power cycles (needs a spot that survives
  reboot, e.g. a tiny file on the card).
- Contrast stretch before matching (photos are a little dim, so detail bunches
  in the mid shades).
- Per-pixel (rather than per-2×2-block) luma dithering for finer gradients.
