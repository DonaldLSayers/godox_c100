@ Preset data: up to MAX_PRESETS presets (see tools/palettes.py). Too big for
@ the photo cave, so it lives in the unused end of the video cave's dead range
@ (0xbbc00-0xbc400). Data only; build.sh passes the label addresses to
@ photo_cave.s. Every table is padded to room for MAX_PRESETS (NMAX colours
@ each), so the labels sit at fixed addresses (palettes.py PD) whatever the
@ presets: the site's editor patches its presets into one template build.
@   MATCH_PALETTES  per preset: count, count x (Y,U,V); lut_fill matches
@                   against these
@   PRESET_MATCH    per preset: index of its match palette (= the preset's)
@   TAGS            per preset: the 3-letter tag (draw_tag)
@   GB_DATA         the Game Boy mode's thresholds and shade colours (gb.py)
@   DISPLAY_PTRS    per preset: address of its paint colours (count x (Y,U,V),
@                   index for index with the match palette); CUR_PAL, so the
@                   photo and video hooks paint with these
    .syntax unified
    .arm
    .include "palettes.inc"
    .include "gb.inc"
base:
    .org    PD_MATCH
MATCH_PALETTES:
    MATCH_DATA
PRESET_MATCH:
    PRESET_MATCH_DATA
TAGS:
    TAG_DATA
DISPLAY:
    DISPLAY_DATA
DISPLAY_PTRS:
    DISPLAY_PTR_DATA
    GB_DATA
PRESET_DATA_END:
