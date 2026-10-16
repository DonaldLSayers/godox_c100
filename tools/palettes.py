#!/usr/bin/env python3
"""The photo palettes: base colours (hex), each brought to NMIN..NMAX colours.

A palette with fewer than NMIN colours is topped up by expand() with
"overprint" mixes -- the midpoint of two base colours, like two riso inks
printed over each other -- picking each time the mix farthest from the colours
already in the set, and preferring mixes that don't come out greyer than their
parents (those muddy the look). A palette with more than NMAX is thin()ned by
dropping near-duplicates. Colours are JPEG/JFIF YCbCr, which is what the
camera's buffer holds.

The camera uses presets (below): a match palette x a film simulation.

  palettes.py            print every preset (match colour -> film colour)
  palettes.py asm        print palettes.inc for the caves (presets, tags,
                         display codes)
"""
import os, sys

NMIN = 10   # small palettes are topped up to this many colours
NMAX = 32   # big palettes are thinned to at most this many
WY = 2      # luma weight in the match distance: WY*|dY| + |dU| + |dV|
LUT = (3, 3)  # camera lookup-table steps: Y and U/V in bins of 2^3 (photo_cave.s)

GREYS = {'000000', '7C7C7C', 'BCBCBC', 'FCFCFC'}   # NES greys thin() must keep

# The full NES (2C02) palette. The source screenshot showed the first 32; the
# rest is the standard Lospec list. thin() takes it down to NMAX for BASE.
NES_FULL = [
    '000000', 'FCFCFC', 'F8F8F8', 'BCBCBC', '7C7C7C', 'A4E4FC', '3CBCFC', '0078F8',
    '0000FC', 'B8B8F8', '6888FC', '0058F8', '0000BC', 'D8B8F8', '9878F8', '6844FC',
    '4428BC', 'F8B8F8', 'F878F8', 'D800CC', '940084', 'F8A4C0', 'F85898', 'E40058',
    'A80020', 'F0D0B0', 'F87858', 'F83800', 'A81000', 'FCE0A8', 'FCA044', 'E45C10',
    '881400', 'F8D878', 'F8B800', 'AC7C00', '503000', 'D8F878', 'B8F818', '00B800',
    '007800', 'B8F8B8', '58D854', '00A800', '006800', 'B8F8D8', '58F898', '00A844',
    '005800', '00FCFC', '00E8D8', '008888', '004058', 'F8D8F8', '787878',
]


def clamp(x):
    return max(0, min(255, round(x)))


def hex_to_yuv(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (clamp(0.299 * r + 0.587 * g + 0.114 * b),
            clamp(128 - 0.168736 * r - 0.331264 * g + 0.5 * b),
            clamp(128 + 0.5 * r - 0.418688 * g - 0.081312 * b))


def yuv_to_hex(c):
    y, u, v = c[0], c[1] - 128, c[2] - 128
    rgb = (y + 1.402 * v, y - 0.344136 * u - 0.714136 * v, y + 1.772 * u)
    return ''.join(f'{clamp(x):02X}' for x in rgb)


def chroma(c):
    return abs(c[1] - 128) + abs(c[2] - 128)


def dist(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def thin(hexes, n, protect=()):
    """Drop near-duplicates until n colours are left: take the closest pair
    (Y+U+V) and drop whichever of the two is closer to the rest of the set.
    Colours in protect are never dropped (the greys, which photos lean on)."""
    yuv = {h: hex_to_yuv(h) for h in hexes}
    keep = list(dict.fromkeys(hexes))
    while len(keep) > n:
        pairs = [(dist(yuv[a], yuv[b]), a, b) for i, a in enumerate(keep) for b in keep[i + 1:]
                 if not (a in protect and b in protect)]
        _, a, b = min(pairs)
        rest = lambda x, other: min(dist(yuv[x], yuv[y]) for y in keep if y not in (x, other))
        if a in protect or (b not in protect and rest(b, a) < rest(a, b)):
            a, b = b, a
        keep.remove(a)
    return keep


# riso6 and refreshing are from the v1 cave (hex converted back from its Y,U,V
# bytes, round-trips exactly). The rest were added 2026-10-14; the pixel-art
# palettes use the canonical Lospec values. Tried and dropped: vibrant_summer,
# fiesta, bold_hues, dark_sunset, vibrant_nature, seventies, pixnote24, pico8,
# db32, earthy.
BASE = {
    'riso6':       ['1A1B3A', 'E0405A', 'F19041', '2AA0A0', 'F0E0BF', 'FFFFFF'],
    'refreshing':  ['A7D2E5', '4992B2', '102A43', 'F1C23E', 'E8892B'],
    'mid_century': ['F87523', 'FFC31B', 'E7DCC9', '1DB7B9', '126D68',
                    '093634', '1A1B3A'],  # + dark teal, dark navy
    'harbour':     ['FBD0A6', 'F37022', 'B11016', '2ABA9E', '007096'],
    'db16': ['140C1C', '442434', '30346D', '4E4A4E', '854C30', '346524', 'D04648', '757161',
             '597DCE', 'D27D2C', '8595A1', '6DAA2C', 'D2AA99', '6DC2CA', 'DAD45E', 'DEEED6'],
    'endesga32': ['BE4A2F', 'D77643', 'EAD4AA', 'E4A672', 'B86F50', '733E39', '3E2731', 'A22633',
                  'E43B44', 'F77622', 'FEAE34', 'FEE761', '63C74D', '3E8948', '265C42', '193C3E',
                  '124E89', '0099DB', '2CE8F5', 'FFFFFF', 'C0CBDC', '8B9BB4', '5A6988', '3A4466',
                  '262B44', '181425', 'FF0044', '68386C', 'B55088', 'F6757A', 'E8B796', 'C28569'],
    'sweetie16': ['1A1C2C', '5D275D', 'B13E53', 'EF7D57', 'FFCD75', 'A7F070', '38B764', '257179',
                  '29366F', '3B5DC9', '41A6F6', '73EFF7', 'F4F4F4', '94B0C2', '566C86', '333C57'],
    'nes': thin(NES_FULL, NMAX, protect=GREYS),
}

# Palettes topped up past NMIN (breaking their original set for more range).
SIZE = {'db16': 24}


def expand(base, n=NMIN):
    """Return [(yuv, parents)]: the base colours, topped up with mixes to n.

    parents is None for a base colour, else the (i, j) indices it mixes.
    """
    base = list(dict.fromkeys(base))
    out = [(hex_to_yuv(h), None) for h in base]
    pairs = [(i, j) for i in range(len(base)) for j in range(i + 1, len(base))]
    mix = {p: tuple((out[p[0]][0][k] + out[p[1]][0][k]) / 2 for k in range(3)) for p in pairs}
    vivid = [p for p in pairs
             if chroma(mix[p]) >= 0.8 * min(chroma(out[p[0]][0]), chroma(out[p[1]][0]))]
    for pool in (vivid, pairs):          # greying mixes only if vivid runs out
        while len(out) < n:
            pool = [p for p in pool if p not in [q for _, q in out]]
            if not pool:
                break
            best = max(pool, key=lambda p: min(dist(mix[p], c) for c, _ in out))
            out.append((tuple(clamp(x) for x in mix[best]), best))
    return out


def source(name, par):
    """Human-readable origin of a colour in palette name."""
    if par is None:
        return 'base'
    return f'mix of #{BASE[name][par[0]]} + #{BASE[name][par[1]]}'


def expanded():
    pals = {name: expand(cols, SIZE.get(name, NMIN)) for name, cols in BASE.items()}
    assert all(NMIN <= len(c) <= NMAX for c in pals.values())
    return pals


# ---- Presets (2026-10-16): 3 match palettes x 4 film simulations ----
# Each block gets its nearest colour in the preset's match palette (as with the
# plain palettes), and is painted with that colour as a film simulation would
# render it: a G'MIC film LUT applied to the palette's colours by film.py, kept
# in film_colours.py so the build doesn't need the LUTs. The match palettes:
#   E  endesga32 + 3 greens (foliage landed on its browns), minus 3 colours
#      that were used 0.0% on the plain photos, to stay at NMAX
#   6  riso6, overprint-expanded to 16 instead of 10 (less funky)
#   H  harbour + a dark (it had none; shadows went flat plum), expanded to 16
# Tag = palette letter + film code, e.g. EAV, HP6. See docs/c100-firmware.md.
EG_GREENS = ['2B5322', '4F7945', '77A36E']  # OKLCH L 0.40/0.53/0.67, C 0.09, hue 140
EG_UNUSED = {'FF0044', 'FEE761', '2CE8F5'}
HB_DARK = '011F2A'                          # harbour's blue at OKLCH L 0.22
MATCH = {
    'E': [hex_to_yuv(h) for h in BASE['endesga32'] if h not in EG_UNUSED]
         + [hex_to_yuv(h) for h in EG_GREENS],
    '6': [c for c, _ in expand(BASE['riso6'], 16)],
    'H': [c for c, _ in expand(BASE['harbour'] + [HB_DARK], 16)],
}
FILMS = {'AV': 'agfa_vista_200', 'FP': 'fuji_provia_100_generic',
         'FV': 'fuji_velvia_100_generic', 'P6': 'polaroid_690'}


def presets():
    """[(tag, match colours, display colours)] in firmware order, as (Y,U,V)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # build.sh runs python -I
    from film_colours import DISPLAY, SOURCE
    out = []
    for p, cols in MATCH.items():
        assert SOURCE.get(p) == [yuv_to_hex(c) for c in cols], \
            f'film_colours.py is stale for palette {p}: run tools/film.py gen'
        for f in FILMS:
            out.append((p + f, cols, [hex_to_yuv(h) for h in DISPLAY[p + f]]))
    assert all(len(m) <= NMAX for _, m, _ in out)
    return out


# Tag: the letters in a 3x5 pixel font, drawn top right on every photo so you
# can tell which preset it got. Letters in the lightest colour, with a
# one-pixel outline (8 neighbours) in the darkest. TAG names the old palettes
# (palette_preview.py); the presets' tags are 3 letters.
TAG = {'riso6': 'R6', 'refreshing': 'RF', 'mid_century': 'MC', 'harbour': 'HB',
       'db16': 'DB', 'endesga32': 'EG', 'sweetie16': 'S6', 'nes': 'NS'}
FONT = {  # rows top to bottom, 3 pixels each
    'A': ['010', '101', '111', '101', '101'],
    'B': ['110', '101', '110', '101', '110'], 'C': ['111', '100', '100', '100', '111'],
    'D': ['110', '101', '101', '101', '110'], 'E': ['111', '100', '110', '100', '111'],
    'F': ['111', '100', '110', '100', '100'], 'G': ['111', '100', '101', '101', '111'],
    'H': ['101', '101', '111', '101', '101'], 'M': ['101', '111', '111', '101', '101'],
    'N': ['110', '101', '101', '101', '101'], 'P': ['110', '101', '110', '100', '100'],
    'R': ['110', '101', '110', '101', '101'], 'S': ['011', '100', '010', '001', '110'],
    'V': ['101', '101', '101', '101', '010'], '6': ['111', '100', '111', '101', '111'],
}
TAG_LETTERS = 3
TAG_ROWS, TAG_COLS = 7, 4 * TAG_LETTERS + 1  # 3 letters, 1-pixel gaps, plus the outline
TAG_SCALE = 2               # blocks per font pixel (a block is 2x2 image pixels)
TAG_TOP, TAG_RIGHT = 4, 4   # margins in blocks


def tag_cells(text):
    """7 x (4*len+1) grid: 0 = photo shows through, 1 = dark, 2 = light."""
    cols = 4 * len(text) + 1
    lit = [[0] * cols for _ in range(TAG_ROWS)]
    for k, ch in enumerate(text):
        for r, row in enumerate(FONT[ch]):
            for c, bit in enumerate(row):
                lit[1 + r][1 + 4 * k + c] = int(bit)
    cells = [[0] * cols for _ in range(TAG_ROWS)]
    for r in range(TAG_ROWS):
        for c in range(cols):
            if lit[r][c]:
                cells[r][c] = 2
            elif any(lit[rr][cc] for rr in range(max(r - 1, 0), min(r + 2, TAG_ROWS))
                     for cc in range(max(c - 1, 0), min(c + 2, cols))):
                cells[r][c] = 1
    return cells


def tag_colours(cols):
    """Indices of the darkest and lightest colour (by Y) in a list of (Y,U,V)."""
    ys = [c[0] for c in cols]
    return ys.index(min(ys)), ys.index(max(ys))


# The same tag on the camera's see-through display, on the three 7-segment
# cells of the shutter-speed (SS) readout, blank in photo and video mode. V has
# no 7-segment shape and shows as U; S as 5.
SEG7 = {'A': 'abcefg', 'E': 'adefg', 'F': 'aefg', 'H': 'bcefg', 'P': 'abefg',
        'U': 'bcdef', '5': 'acdfg', '6': 'acdefg'}
SEG7_LETTER = {'V': 'U', 'S': '5'}
# Segment -> (HT1621 address, COM) for each SS cell, left to right, found by
# running the firmware's SS digit routines (FUN_0004a374, FUN_0004a1f0,
# FUN_0004a074) for 0..9 in tools/emu_seg.py. Each cell is wired differently.
# Addresses 0x0d..0x13 hold nothing but these 21 segments.
SS_CELLS = [
    {'a': (0x0d, 0), 'b': (0x0e, 0), 'c': (0x0f, 2), 'd': (0x0e, 2), 'e': (0x0d, 2), 'f': (0x0d, 1), 'g': (0x0e, 1)},
    {'a': (0x0f, 0), 'b': (0x10, 0), 'c': (0x11, 1), 'd': (0x11, 2), 'e': (0x10, 2), 'f': (0x0f, 1), 'g': (0x10, 1)},
    {'a': (0x12, 0), 'b': (0x13, 0), 'c': (0x13, 1), 'd': (0x13, 2), 'e': (0x12, 2), 'f': (0x11, 0), 'g': (0x12, 1)},
]
SS_FIRST, SS_COUNT = 0x0d, 7    # HT1621 addresses written


def lcd_text(tag):
    return ''.join(SEG7_LETTER.get(ch, ch) for ch in tag)


def lcd_nibbles(tag):
    """Nibbles for HT1621 addresses 0x0d..0x13 that show `tag` on the SS cells
    (COM0 = nibble bit 8, COM1 = 4, COM2 = 2)."""
    nib = [0] * SS_COUNT
    for cell, ch in zip(SS_CELLS, lcd_text(tag)):
        for seg in SEG7[ch]:
            addr, com = cell[seg]
            nib[addr - SS_FIRST] |= 8 >> com
    return nib


def main():
    if sys.argv[1:] == ['asm']:
        pre = presets()
        print('@ Generated by tools/palettes.py asm -- do not edit.')
        print(f'    .equ    NPAL, {len(pre)}                      @ presets')
        print('    .macro  MATCH_DATA                    @ per match palette: count, then count x (Y,U,V)')
        for p, cols in MATCH.items():
            print(f'    .byte {len(cols)}, ' + ', '.join('%d,%d,%d' % c for c in cols) + f'   @ {p}')
        print('    .endm')
        print('    .macro  PRESET_MATCH_DATA             @ per preset: index of its match palette')
        print('    .byte ' + ', '.join(str(list(MATCH).index(t[0])) for t, _, _ in pre))
        print('    .endm')
        print('    .macro  DISPLAY_DATA                  @ per preset: count x (Y,U,V) film colours')
        for i, (tag, _, disp) in enumerate(pre):
            print(f'disp_{i}:')
            print('    .byte ' + ', '.join('%d,%d,%d' % c for c in disp) + f'   @ {tag}')
        print('    .endm')
        print('    .macro  DISPLAY_PTR_DATA              @ per preset: address of its film colours')
        for i in range(len(pre)):
            print(f'    .word   disp_{i} - base')
        print('    .endm')
        print(f'    .equ    TAG_ROWS, {TAG_ROWS}')
        print(f'    .equ    TAG_COLS, {TAG_COLS}')
        print(f'    .equ    TAG_SCALE, {TAG_SCALE}')
        print(f'    .equ    TAG_TOP, {TAG_TOP}')
        print(f'    .equ    TAG_RIGHT, {TAG_RIGHT}')
        nbytes = (TAG_ROWS * TAG_COLS + 3) // 4
        print(f'    .equ    TAG_BYTES, {nbytes + 2}')
        print(f'    .macro  TAG_DATA                      @ per preset: {nbytes} B of 2-bit cells'
              ' (LSB first), dark offset, light offset')
        for tag, _, disp in pre:
            assert len(tag) == TAG_LETTERS
            flat = [v for row in tag_cells(tag) for v in row]
            packed = [sum(v << (2 * j) for j, v in enumerate(flat[i:i + 4])) for i in range(0, len(flat), 4)]
            dark, light = tag_colours(disp)
            print(f'    .byte ' + ', '.join(map(str, packed + [3 * dark, 3 * light])) + f'   @ {tag}')
        print('    .endm')
        print(f'    .equ    SS_FIRST, {SS_FIRST:#x}')
        print(f'    .equ    SS_COUNT, {SS_COUNT}')
        print(f'    .macro  LCD_TAG_DATA                  @ per preset: HT1621 nibbles for addresses'
              f' {SS_FIRST:#x}..{SS_FIRST + SS_COUNT - 1:#x}')
        for tag, _, _ in pre:
            print('    .byte ' + ', '.join(map(str, lcd_nibbles(tag))) + f'   @ {tag} {lcd_text(tag)}')
        print('    .endm')
        return
    for tag, cols, disp in presets():
        print(f'{tag} ({len(cols)})')
        for c, d in zip(cols, disp):
            print(f'  #{yuv_to_hex(c)} -> #{yuv_to_hex(d)}  Y,U,V = {d[0]:3},{d[1]:3},{d[2]:3}')


if __name__ == '__main__':
    main()
