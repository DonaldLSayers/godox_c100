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
  `SILENT=1 sh tools/build.sh` builds with no sounds and the speaker amp never
  switched on; plain `sh tools/build.sh`
  uses the Super Mario kick (shutter) and coin (power-on). The UI/focus beep
  (`BEEP.wav`) is silenced in both.
- `sim_dither.py` — off-camera preview of palette + ordered dithering (early,
  grayscale-ramp version).
- `sim_palette.py` — exact off-camera replica of the current hook (blocks,
  Bayer, weighted nearest colour, lookup-table quantisation).
- `palettes.py` — the palette definitions; `palettes.py asm` generates the
  table `build.sh` assembles into the cave.
- `palette_preview.py` — renders every palette on photos (contact sheets).
- `emu_cave.py` — runs the built cave code in an ARM emulator (Unicorn) and
  checks it pixel-for-pixel against `sim_palette.py`.
  See [2026-10-14-palettes.md](2026-10-14-palettes.md).

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
- `v005_bw_dithering.bin`, `v006_first_colored_dithering.bin`,
  `v007_cycled_color_palettes_dithering.bin`,
  `v008_cycled_color_palettes_dithering_larger.bin` — the dithering steps up to
  v1 palettes at 640 wide.
- `v009_more_palettes.bin` — v2: 8 palettes of 10–32 colours, lookup table,
  random palette per photo (see [2026-10-14-palettes.md](2026-10-14-palettes.md)).
- `v010_speaker_silenced.bin` — + speaker amp never switched on (`SILENT=1`).
- `v011_small_video.bin` — + 640-wide video at every aspect ratio (`SMALLVID=1`).

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

## Smaller video (step 1 towards pixel-art video)

Stock video: H.264 High@4.1, 1920×1080, ~28 fps, ~9 Mbit/s, 16 kHz mono PCM,
in a QuickTime `.mov` named `IMG_xxxx.mov` (the `MOVA%04d.avi` strings are
leftovers). The same `FUN_0000f004` sizes video (`APMode 0x101`, photo is
`0x102`); the video setting (`FUN_00023888`) dispatches through its own jump
table at `0xf0a0` (`ldrls` at `0xf098`) and **follows the camera's aspect
setting**. Native entries: 0/1/9 = 1920×1080, 2 = 1616×1080, 3 = 1440×1080,
4 = 1024², 5 = 1344×1080, 6 = 816×1080, 7 = 320×240, 11 = 3840×2160,
12 = 2560×1440, 15 = 2592×1944, others 1280×720.

Size struct fields (`r4`, as printed by `[R]Tw,Th, Sw,Sh, Cw,Ch`): crop C at
+10/+12, first scaler S at +6/+8, target T at +14/+16, mode byte at +4
(photo 1, video 3). Every stock video size has C = S = T.

**Video differs from photo:** photos need S = C (full size) with only T small
(the final scaler shrinks); for video that gives garbage, and video needs
S = T (the first scaler shrinks; there is no final downscale stage).

`build.sh` (`SMALLVID=1`, default) points entries 0/1/9 (16:9), 2 (3:2),
3 (4:3) and 4 (1:1) at cave stubs `vid169`/`vid32`/`vid43`/`vid11`: C = native
crop for the aspect, S = T = 640 wide, mode 3, rejoining the video branch at
`0xf410` (which expects T in r6/r7). They share `size_common` with the photo
stubs, which tells photo/video apart by `APMode` bit 1; photo stubs were
checked unchanged in Unicorn. `SMALLVID=0` keeps stock full-size video.

Test log (all 3:2):

- IMG_0293 — 1616×1080: only the 16:9 entries were patched, so the stub never ran.
- IMG_0294 — S = C = 1616×1080, T = 640×428: H.264 accepts 640×428, but the
  picture is garbage horizontal bands and frames come in bursts of 2–3 (1 ms
  apart, every ~40 ms, ~68 "fps") — the encoder is fed data of another shape.
- IMG_0295 — C = 1616×1080, S = T = 640×428, mode 3: **works**. Clean picture,
  steady ~27 fps, ~1.5 Mbit/s. (One flash ran four independent experiments,
  one per aspect setting; this was the 3:2 one. Field of view vs a photo of
  the same scene still to be confirmed.)
- IMG_0300–0303 — all four aspects (640×360/428/480/640), ~30 fps, valid.
  Field of view matches photos of the same scene (IMG_0304–0307); the laptop
  measures ~850 sensor px wide in all four, so each is its aspect's native crop
  scaled down, not cropped further.

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

### Effect: palette dithering (v1)

> Superseded on 2026-10-14 by 10–32 colour palettes and a per-photo lookup
> table: see [2026-10-14-palettes.md](2026-10-14-palettes.md).

Per 2×2 block the hook:

1. averages the block's 4 luma and adds a **4×4 Bayer** ordered-dither offset;
2. reads the block's real U,V;
3. finds the **nearest of 6 palette colours** in full Y+U+V space (Manhattan
   distance) — true nearest-colour matching, not a grayscale ramp;
4. paints the whole block that palette colour (Y to all four luma, U,V to the
   pair).

Per-block is the natural unit in 4:2:0 (one chroma pair per block) and keeps the
work well inside the interrupt budget.

### Palette cycling and a random start (v1)

> v2 picks a random palette for every photo instead (see the palettes doc).

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
- Mode-switch sound = `CLICK.wav` (sound slot 0). The mode switch handlers
  (`------mode N------` at 0x1dc0c etc.) post message `0x7018` together with
  `MSG_APQ_MODE_TO_*`; the state loops answer `0x7018` with `FUN_00022a80(0)`,
  which plays `CLICK.WAV` if the key-tone setting (config byte +0x19) is on.
  Silenced with `SILENT=1`.
- Sound player `FUN_00022a80(slot)`: 0=CLICK, 1=CAMERA, 2/3=POWERON_AUDIO,
  4=unused handle, 5=BEEP. It turns the **speaker amp (GPIO 0x2c)** on, waits
  100 ms, then queues the WAV to the audio task. The amp is switched off by the
  peripheral task `FUN_00021e60` on message `0x6002` (posted every ~1 s): the
  first tick after a sound arms a counter, the second prints `@@@CLOSE SPEAKER`
  and drives GPIO 0x2c low. That is the ~1–2 s of hiss after every sound, even
  a silent one. Boot (`state_startup_init`, 0x350f0) also turns the amp on
  unconditionally.
- `SILENT=1` NOPs the three amp-on calls (0x22b38, 0x350f0, 0x2ed50), so the
  amp is never powered: no sounds and no hiss.

## Timing notes

- Hook cost scales with pixels. 320-wide finishes comfortably; 640-wide is ~4×
  the work (twice the matches per callback, twice as many callbacks). If a size
  ever outruns the per-callback deadline it shows as the **lower part of each
  photo turning to noise while the top is correct** — the cue to optimise the
  matcher or drop back to a smaller size.
- Photos land in `DCIM` as `IMG_xxxx.jpg`.

## Look knobs (contrast / brightness)

`build.sh` applies an optional per-block brightness pre-map before palette
matching (hue/colour mapping is untouched), as assemble-time constants so there
is no runtime division:

- `CONTRAST` — percent, 100 = neutral. Higher (≈115–140) is more dramatic (pushes
  midtones to the palette's dark/bright ends, good for flat/dim scenes); lower
  (≈70–90) is softer. Useful range ~70–160.
- `BRIGHT` — luma offset, 0 = neutral; positive lifts, negative darkens
  (≈ −60…60).

e.g. `CONTRAST=130 BRIGHT=10 SILENT=1 sh tools/build.sh`.

## UI graphics (GPZP, logos, and the OSD overlay)

The firmware's on-screen graphics come from three different places.

### GPZP images (menu/status assets) — editable

`.gpzp` resources are `GPZP` magic + raw fixed-Huffman DEFLATE of **RGB565**
(little-endian, 2 B/px). `0x8C71` is the transparency key (the live LCD shows
through). The LCD is **320×240**. `tools/gpzp.py` decodes/encodes these:

```
gpzp.py decode IN.gpzp OUT.png [WIDTH]     # WIDTH auto-detected if omitted
gpzp.py encode IN.png  OUT.gpzp            # width/height from the PNG
gpzp.py decode-all FIRMWARE.BIN OUTDIR     # every GPZP -> PNG
```

Round-trip is pixel-exact and re-encodes smaller than the slot (fixed Huffman).
To change one: edit the PNG (same size; alpha-0 = transparent), `encode`, then
`patch_res.py` it in (size-checked). Decoded PNGs are in `gpzp/decoded/`.
Confirmed widths: BACKGROUND 320×240, TFT_WIFI_SYM 320×240, SELECTBAR_LONG
296×40. The small bars / SP_ICON sheet have ambiguous widths (colours are always
right; only the row-wrap may be off) — pin them from their draw calls if needed.

### Power logos — editable, and unused

`POWER_ON_LOGO.jpg` is a **beach photo** and `POWER_OFF_LOGO.jpg` is **"Good
Bye!"** — plain JPEGs, left over from the OEM/children's-camera software this
firmware descends from (like `WIFI.xml`). They are standard JPEGs: replace with
a 320×240 baseline JPEG that fits the slot via `patch_res.py`.

### The live-view OSD overlay — code-drawn, not a file

The mode icons (📷🎥), metering icon, **battery**, **corner framing/aspect
brackets**, **centre reticle**, **ISO/F/SS** labels + digits, and the standby
**"Godox" wordmark** are **not stored images**. They are rendered by the
GeneralPlus bitmap-glyph/OSD engine:

- Source data: `GPRS.pak`, a **nested** GeneralPlus archive (no RGB565/alpha-key
  images inside — it is glyph/index tables).
- Loader/parser: `FUN_00028710` → `FUN_0002809c`.
- Draw routines: `FUN_00027fbc` (glyph string), `FUN_00027ea4` (one glyph), and
  the OSD callers `FUN_000242fc` / `FUN_000245f0` / `FUN_00029710` (these log
  "Failed to draw char font"). Battery: `FUN_0001ed4c`, `FUN_0002602c`.

Pak format cracked so far: `GPRS` + version, a header whose pointers at offsets
`0xb8/0xe8/0xec` reach **3 glyph groups × 12 descriptors**
(`[advance, w, h, _, u32 dataOffset]`; bitmap = `w*h` bytes, 1 B/px alpha, at
`groupBase + dataOffset`, `groupBase` = word 2 of the group's 0xC-byte
subheader). Those 36 are small anti-aliased strip glyphs — a minor sub-set. The
main icons sit behind a further index layer (e.g. the block at `0x9f07`, step
`0x570`, begins with another table of counts/offsets, not pixels), not yet
unwound.

Practical takeaway: to change the overlay, **patching the draw calls** (e.g. NOP
the "Godox" wordmark draw, or move/hide an element) is far more tractable than
fully reverse-engineering and re-packing `GPRS.pak`.

## Ideas not yet done

- Persist the palette index across power cycles (needs a spot that survives
  reboot, e.g. a tiny file on the card).
- Per-pixel (rather than per-2×2-block) luma dithering for finer gradients.
- Fully unwind `GPRS.pak` to extract/edit the OSD icon bitmaps, or (easier)
  patch specific overlay draw calls (e.g. remove the "Godox" wordmark).
