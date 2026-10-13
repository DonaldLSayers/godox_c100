# Godox C100 firmware hacking — image processing progress

_2026-10-13_

Goal: make the C100 produce pixel-art photos in the spirit of the
[Pixless camera](https://petapixel.com/2025/01/09/0-03-megapixel-pixless-camera-captures-charming-pixel-art-photos/) —
small resolution, a limited colour palette, and dithering.

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
- `patch_code.py` — apply byte patches addressed by RAM address; refuses to
  touch the bootloader or the SD-updater, and verifies the original bytes first.
- `build.sh` — **rebuild `build/GP_CARDVR_UPGRADE.BIN` from the original**:
  applies sound swaps, then assembles each `tools/patches/*.s` and patches it
  in. Fails if a patch overflows its slot or has an unresolved relocation.
- `sim_dither.py` — off-camera preview of palette + ordered dithering on a YUV
  photo (for choosing the look before writing firmware).

Reverse engineering: Ghidra headless project under `build/ghidra/`, decompiled
C in `decomp/c100.c`, string→function index in `decomp/strings.tsv`
(scripts in `tools/ghidra/`). Disassembly via Homebrew `llvm-objdump` on a
minimal ELF wrapper (`mkelf.py` in the scratchpad) around `build/app_load0.bin`.

## Backups (in `build_backups/`)

- `v001_original.bin` — factory v1.1.6.
- `v002_updated_sounds.bin` — + custom shutter (SMB kick) and power-on (SMB coin) sounds.
- `v003_smaller_image.bin` — + 4:3 photo mode remapped to 320×240.

## What works

### 1. Custom sounds
Replaced `CAMERA.wav` (shutter) and `POWERON_AUDIO.wav` with 11025 Hz 16-bit
mono clips. Confirmed on camera — this is what proved the updater has no checksum.

### 2. Smaller photos (320×240)
`FUN_0000f004` builds each photo's size from a jump table (per aspect ratio).
The 4:3 entry (and the unused 10–12 entries) now jump into our code cave, which
sets a 1440×1080 crop (full 4:3 sensor area) and a **320×240** final size, then
rejoins the normal photo path at `0xf188`. Earlier mistake: setting only the
final size made the firmware crop 1:1 instead of scaling; the crop and the
first scaler stage must be set too.

- 4:3 → 320×240 (scaled, full field of view). Confirmed on camera.
- Other aspect ratios unchanged (1920×1080, 1616×1080, 1024×1024).

## In progress: the photo pixel hook

We want to modify pixels after the ISP/scaler produces them but before JPEG.

**Hook point:** `FUN_00015448`, the scaler "frame/strip ready" callback,
registered only for photo capture (runs in interrupt context). Its first
instruction is replaced with a branch to our code cave; the cave re-runs that
instruction and returns.

**Code cave:** `FUN_000bab6c`, a ~2 KB function that nothing references (verified
against all B/BL targets and pointers, ARM and Thumb). Holds the hook, the 4:3
size patch, and a scratch word.

**Safety:** the hook only writes to a buffer whose address exactly matches one
of the photo buffers allocated in `FUN_0001808c` (full frame `PHOTO+0x14`, or
scaler strip A/B `PHOTO+0x18`; `PHOTO = 0x1317ac`). An unexpected call leaves
memory untouched — worst case a normal colour photo, never a crash.

### Buffer format — decoded from on-camera diagnostics

A plain "set chroma to neutral" first did nothing (format wasn't what we
assumed), so we used two on-camera diagnostics that report through the photo
itself:

1. **Status bits encoded in the photo width.** Showed: hook *is* called, with a
   frame-ready status, on a scaler strip buffer, and the pixel format byte
   (`PHOTO+0x20`) is `'"'` (0x22), not `'!'` (0x21).
2. **A byte-offset ramp** written across the whole strip buffer (`byte[i] =
   i>>6`). The resulting photo lets us map buffer offset → (x, y, plane).

**Result (confirmed, model error ≈ 3 / 255 = JPEG noise):**

- Each strip callback delivers **32 image rows**; `STRIP_BYTES` (value at
  `0x13155c`, = width × 32 × 3/2) = 15360 for a 320-wide photo.
- The buffer is **row-interleaved**, not planar:

  ```
  per row:  [ W bytes luma Y ][ W/2 bytes chroma, U,V interleaved ]
  strip  =  32 such rows, back to back
  ```

  For the 320-wide photo: 320 Y + 160 chroma = 480 bytes/row, ×32 = 15360.
  Chroma is horizontally subsampled 4:1 (80 U + 80 V per row).

So **to neutralise colour (B&W):** in every 480-byte row, leave bytes 0–319 (Y)
and set bytes 320–479 (chroma) to 0x80. The earlier whole-"last third of
buffer" write hit the bottom ~8–10 rows entirely (both Y and chroma), which is
why only horizontal grey bands appeared.

The hook already does cache maintenance around its writes (`0x401ac` invalidate,
`0x401b8` clean) so the JPEG encoder sees the modified bytes.

## Next steps

1. **B&W, done right:** per-row, set only the chroma bytes to 0x80. (Being built.)
2. **Game Boy palette + ordered (Bayer) dithering:** map each Y byte to a small
   ramp of palette shades using a 4×4 Bayer threshold; this is a change to the
   same per-row loop. Per-pixel, no neighbour dependence, so it fits the
   strip-at-a-time model and the interrupt budget.
3. Possibly: contrast stretch before mapping (photos are dim, so detail bunches
   in the middle shades), and higher JPEG quality so dither dots survive.

## Image-size / timing notes

- Hook cost scales with pixels: ~1 ms at 320×240, ~20 ms at 1920×1080. Fine for
  stills; watch it if ever used on 16:9.
- Photos land in `DCIM` on the card as `IMG_xxxx.jpg`. Test shots so far:
  36–42 (B&W attempt, no effect), 43–46 (status diagnostic), 47–49 (first 4:2:0
  B&W attempt — grey bands), 50–52 (offset ramp — decoded the layout above).
