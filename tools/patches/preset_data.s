@ Preset data: 3 match palettes x 4 film simulations = 12 presets (see
@ tools/palettes.py). Too big for the photo cave, so it lives in the unused
@ end of the video cave's dead range (0xbbc00-0xbc400). Data only; build.sh
@ passes the label addresses to photo_cave.s.
@   MATCH_PALETTES  per match palette: count, count x (Y,U,V); lut_fill matches
@                   against these
@   PRESET_MATCH    per preset: index of its match palette
@   DISPLAY_PTRS    per preset: address of its film colours (count x (Y,U,V),
@                   index for index with the match palette); CUR_PAL, so the
@                   photo and video hooks paint with these
@   TAGS            per preset: the 3-letter tag (draw_tag)
    .syntax unified
    .arm
    .include "palettes.inc"
base:
    .org    0xbbc00
MATCH_PALETTES:
    MATCH_DATA
PRESET_MATCH:
    PRESET_MATCH_DATA
TAGS:
    TAG_DATA
DISPLAY:
    DISPLAY_DATA
    .align  2
DISPLAY_PTRS:
    DISPLAY_PTR_DATA
