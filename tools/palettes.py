#!/usr/bin/env python3
"""The photo palettes: base colours (hex), each brought to NMIN..NMAX colours.

A palette with fewer than NMIN colours is topped up by expand() with
"overprint" mixes -- the midpoint of two base colours, like two riso inks
printed over each other -- picking each time the mix farthest from the colours
already in the set, and preferring mixes that don't come out greyer than their
parents (those muddy the look). A palette with more than NMAX is thin()ned by
dropping near-duplicates. Colours are JPEG/JFIF YCbCr, which is what the
camera's buffer holds.

  palettes.py            print every palette (hex + Y,U,V)
  palettes.py asm        print palettes.inc for photo_cave.s (palettes + tags)
"""
import sys

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


# Palette tag: two letters in a 3x5 pixel font, drawn top right on every photo
# so you can tell which palette it got. Letters in the palette's lightest
# colour, with a one-pixel outline (8 neighbours) in its darkest.
TAG = {'riso6': 'R6', 'refreshing': 'RF', 'mid_century': 'MC', 'harbour': 'HB',
       'db16': 'DB', 'endesga32': 'EG', 'sweetie16': 'S6', 'nes': 'NS'}
FONT = {  # rows top to bottom, 3 pixels each
    'B': ['110', '101', '110', '101', '110'], 'C': ['111', '100', '100', '100', '111'],
    'D': ['110', '101', '101', '101', '110'], 'E': ['111', '100', '110', '100', '111'],
    'F': ['111', '100', '110', '100', '100'], 'G': ['111', '100', '101', '101', '111'],
    'H': ['101', '101', '111', '101', '101'], 'M': ['101', '111', '111', '101', '101'],
    'N': ['110', '101', '101', '101', '101'], 'R': ['110', '101', '110', '101', '101'],
    'S': ['011', '100', '010', '001', '110'], '6': ['111', '100', '111', '101', '111'],
}
TAG_ROWS, TAG_COLS = 7, 9   # 5x7 text area (3 + 1 gap + 3) plus the outline
TAG_SCALE = 2               # blocks per font pixel (a block is 2x2 image pixels)
TAG_TOP, TAG_RIGHT = 4, 4   # margins in blocks


def tag_cells(name):
    """TAG_ROWS x TAG_COLS grid: 0 = photo shows through, 1 = dark, 2 = light."""
    text = [[0] * TAG_COLS for _ in range(TAG_ROWS)]
    for k, ch in enumerate(TAG[name]):
        for r, row in enumerate(FONT[ch]):
            for c, bit in enumerate(row):
                text[1 + r][1 + 4 * k + c] = int(bit)
    cells = [[0] * TAG_COLS for _ in range(TAG_ROWS)]
    for r in range(TAG_ROWS):
        for c in range(TAG_COLS):
            if text[r][c]:
                cells[r][c] = 2
            elif any(text[rr][cc] for rr in range(max(r - 1, 0), min(r + 2, TAG_ROWS))
                     for cc in range(max(c - 1, 0), min(c + 2, TAG_COLS))):
                cells[r][c] = 1
    return cells


# The same tag on the camera's see-through display, on the two 7-segment
# cells of the ISO readout (shown in photo and video mode, where the readout is
# blank). Not every letter has a 7-segment shape, so some are shown lowercase
# or approximated: R -> r, B -> b, D -> d, N -> n, S -> 5, M -> a "∩".
SEG7 = {'A': 'abcefg', 'b': 'cdefg', 'C': 'adef', 'd': 'bcdeg', 'E': 'adefg', 'F': 'aefg',
        'G': 'acdef', 'H': 'bcefg', 'n': 'ceg', 'r': 'eg', 'M': 'abcef',
        '5': 'acdfg', '6': 'acdefg'}
SEG7_LETTER = {'R': 'r', 'B': 'b', 'D': 'd', 'N': 'n', 'S': '5'}
# Each cell is three HT1621 addresses (found by running the firmware's digit
# routine in tools/emu_seg.py): f, e | a, g, d | b, c, as COM0 = 8, COM1 = 4,
# COM2 = 2. The COM0 bits of the first and last address are the ISO label and
# the fixed zeros; they stay off.
SEG7_BITS = {'f': (0, 4), 'e': (0, 2), 'a': (1, 8), 'g': (1, 4), 'd': (1, 2), 'b': (2, 4), 'c': (2, 2)}


def lcd_text(tag):
    return ''.join(SEG7_LETTER.get(ch, ch) for ch in tag)


def lcd_nibbles(tag):
    """Nibbles for HT1621 addresses 0..5 that show `tag` on the ISO cells."""
    nib = [0] * 6
    for cell, ch in enumerate(lcd_text(tag)):
        for seg in SEG7[ch]:
            off, bit = SEG7_BITS[seg]
            nib[3 * cell + off] |= bit
    return nib


def tag_colours(cols):
    """Indices of the darkest and lightest colour (by Y) of an expanded palette."""
    ys = [c[0] for c, _ in cols]
    return ys.index(min(ys)), ys.index(max(ys))


def main():
    pals = expanded()
    if sys.argv[1:] == ['asm']:
        print('@ Generated by tools/palettes.py asm -- do not edit.')
        print(f'    .equ    NPAL, {len(pals)}')
        print('    .macro  PALETTE_DATA                  @ per palette: count, then count x (Y,U,V)')
        for name, cols in pals.items():
            print(f'    .byte {len(cols)}, ' + ', '.join('%d,%d,%d' % c for c, _ in cols) + f'   @ {name}')
        print('    .endm')
        print(f'    .equ    TAG_ROWS, {TAG_ROWS}')
        print(f'    .equ    TAG_COLS, {TAG_COLS}')
        print(f'    .equ    TAG_SCALE, {TAG_SCALE}')
        print(f'    .equ    TAG_TOP, {TAG_TOP}')
        print(f'    .equ    TAG_RIGHT, {TAG_RIGHT}')
        nbytes = (TAG_ROWS * TAG_COLS + 3) // 4
        print(f'    .equ    TAG_BYTES, {nbytes + 2}')
        print(f'    .macro  TAG_DATA                      @ per palette: {nbytes} B of 2-bit cells'
              ' (LSB first), dark offset, light offset')
        for name, cols in pals.items():
            flat = [v for row in tag_cells(name) for v in row]
            packed = [sum(v << (2 * j) for j, v in enumerate(flat[i:i + 4])) for i in range(0, len(flat), 4)]
            dark, light = tag_colours(cols)
            print(f'    .byte ' + ', '.join(map(str, packed + [3 * dark, 3 * light])) + f'   @ {name} {TAG[name]}')
        print('    .endm')
        print('    .macro  LCD_TAG_DATA                  @ per palette: HT1621 nibbles for addresses 0..5')
        for name in pals:
            print('    .byte ' + ', '.join(map(str, lcd_nibbles(TAG[name]))) + f'   @ {name} {lcd_text(TAG[name])}')
        print('    .endm')
        return
    for name, cols in pals.items():
        print(f'{name} ({len(cols)})')
        for c, par in cols:
            print(f'  #{yuv_to_hex(c)}  Y,U,V = {c[0]:3},{c[1]:3},{c[2]:3}  {source(name, par)}')


if __name__ == '__main__':
    main()
