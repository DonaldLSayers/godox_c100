#!/usr/bin/env python3
"""The photo palettes: base colours (hex), brought to exactly NCOL colours.

A palette with more than NCOL colours uses the NCOL listed in PICK (chosen on
photos by palette_pick.py; reduce() -- darkest first, then farthest-point -- is
the fallback). A palette with fewer is topped up by expand() with
"overprint" mixes -- the midpoint of two base colours, like two riso inks
printed over each other -- picking each time the mix farthest from the colours
already in the set, and preferring mixes that don't come out greyer than their
parents (those muddy the look). Colours are JPEG/JFIF YCbCr, which is what the
camera's buffer holds.

  palettes.py [full]     print every palette (hex + Y,U,V); full = big ones whole
  palettes.py asm        print the .byte table for photo_cave.s
"""
import sys

NCOL = 10   # colours per palette after expansion
WY = 2      # luma weight in the match distance: WY*|dY| + |dU| + |dV|

# riso6, vibrant_nature and refreshing are from the v1 cave (hex converted back
# from its Y,U,V bytes, round-trips exactly). mid_century, harbour and earthy
# were added 2026-10-14; the pixel-art palettes after them (canonical Lospec
# values) later that day. Dropped: vibrant_summer, fiesta, bold_hues,
# dark_sunset, seventies.
BASE = {
    'riso6':          ['1A1B3A', 'E0405A', 'F19041', '2AA0A0', 'F0E0BF', 'FFFFFF'],
    'vibrant_nature': ['C43A3A', '3A6A50', 'A1CAA0', 'F1F0C4', '362617'],
    'refreshing':     ['A7D2E5', '4992B2', '102A43', 'F1C23E', 'E8892B'],
    'mid_century':    ['F87523', 'FFC31B', 'E7DCC9', '1DB7B9', '126D68'],
    'harbour':        ['FBD0A6', 'F37022', 'B11016', '2ABA9E', '007096'],
    'earthy':         ['0C8D90', 'E8E3C3', 'DEA937', 'CE4A1C', '4E3B2B'],
    # Pixnote 24: Apple system colours + pastels (pastels sampled from a screenshot)
    'pixnote24': ['000000', '555555', 'AAAAAA', 'FFFFFF', 'FF3B30', 'FF9500', 'FFCC00', '34C759',
                  '00C7BE', '007AFF', '5856D6', 'AF52DE', 'FF9A99', 'FFCB8E', 'FFF3A0', 'A9F0A4',
                  'A0E8E0', 'A0C8FF', 'C4B8FF', 'E0A8FE', 'FEDCB5', 'E8A87C', 'C57A5A', '8B5E3B'],
    'pico8': ['000000', '1D2B53', '7E2553', '008751', 'AB5236', '5F574F', 'C2C3C7', 'FFF1E8',
              'FF004D', 'FFA300', 'FFEC27', '00E436', '29ADFF', '83769C', 'FF77A8', 'FFCCAA'],
    'db16': ['140C1C', '442434', '30346D', '4E4A4E', '854C30', '346524', 'D04648', '757161',
             '597DCE', 'D27D2C', '8595A1', '6DAA2C', 'D2AA99', '6DC2CA', 'DAD45E', 'DEEED6'],
    'db32': ['000000', '222034', '45283C', '663931', '8F563B', 'DF7126', 'D9A066', 'EEC39A',
             'FBF236', '99E550', '6ABE30', '37946E', '4B692F', '524B24', '323C39', '3F3F74',
             '306082', '5B6EE1', '639BFF', '5FCDE4', 'CBDBFC', 'FFFFFF', '9BADB7', '847E87',
             '696A6A', '595652', '76428A', 'AC3232', 'D95763', 'D77BBA', '8F974A', '8A6F30'],
    'endesga32': ['BE4A2F', 'D77643', 'EAD4AA', 'E4A672', 'B86F50', '733E39', '3E2731', 'A22633',
                  'E43B44', 'F77622', 'FEAE34', 'FEE761', '63C74D', '3E8948', '265C42', '193C3E',
                  '124E89', '0099DB', '2CE8F5', 'FFFFFF', 'C0CBDC', '8B9BB4', '5A6988', '3A4466',
                  '262B44', '181425', 'FF0044', '68386C', 'B55088', 'F6757A', 'E8B796', 'C28569'],
    'sweetie16': ['1A1C2C', '5D275D', 'B13E53', 'EF7D57', 'FFCD75', 'A7F070', '38B764', '257179',
                  '29366F', '3B5DC9', '41A6F6', '73EFF7', 'F4F4F4', '94B0C2', '566C86', '333C57'],
    # NES: the screenshot shows the first 32; the rest is the standard Lospec list
    'nes': ['000000', 'FCFCFC', 'F8F8F8', 'BCBCBC', '7C7C7C', 'A4E4FC', '3CBCFC', '0078F8',
            '0000FC', 'B8B8F8', '6888FC', '0058F8', '0000BC', 'D8B8F8', '9878F8', '6844FC',
            '4428BC', 'F8B8F8', 'F878F8', 'D800CC', '940084', 'F8A4C0', 'F85898', 'E40058',
            'A80020', 'F0D0B0', 'F87858', 'F83800', 'A81000', 'FCE0A8', 'FCA044', 'E45C10',
            '881400', 'F8D878', 'F8B800', 'AC7C00', '503000', 'D8F878', 'B8F818', '00B800',
            '007800', 'B8F8B8', '58D854', '00A800', '006800', 'B8F8D8', '58F898', '00A844',
            '005800', '00FCFC', '00E8D8', '008888', '004058', 'F8D8F8', '787878'],
}

# Which NCOL colours the camera keeps of each big palette: chosen on photos by
# tools/palette_pick.py (35 stock-firmware photos in images/, 2026-10-14).
PICK = {
    'pixnote24': ['000000', '555555', 'AAAAAA', 'FFFFFF', 'A0E8E0', 'C4B8FF', 'FEDCB5', 'E8A87C', 'C57A5A', '8B5E3B'],
    'pico8': ['000000', '1D2B53', '7E2553', 'AB5236', '5F574F', 'C2C3C7', 'FFF1E8', '83769C', 'FF77A8', 'FFCCAA'],
    'db16': ['140C1C', '442434', '4E4A4E', '854C30', 'D04648', '757161', 'D27D2C', '8595A1', 'D2AA99', 'DEEED6'],
    'db32': ['000000', '222034', 'D9A066', 'EEC39A', '323C39', 'FFFFFF', '9BADB7', '847E87', '696A6A', '595652'],
    'endesga32': ['B86F50', '733E39', '3E2731', 'FFFFFF', 'C0CBDC', '8B9BB4', '5A6988', '181425', 'E8B796', 'C28569'],
    'sweetie16': ['1A1C2C', '5D275D', 'B13E53', 'EF7D57', 'FFCD75', '38B764', 'F4F4F4', '94B0C2', '566C86', '333C57'],
    'nes': ['000000', 'FCFCFC', 'BCBCBC', '7C7C7C', 'F0D0B0', 'F87858', '503000', '004058', 'F8D8F8', '787878'],
}


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


def wdist(a, b):
    return WY * abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def reduce(base, n):
    """Pick n of the base colours: darkest first, then each time the colour
    farthest (in the camera's weighted distance) from those already picked."""
    cols = [hex_to_yuv(h) for h in base]
    keep = [min(range(len(cols)), key=lambda i: cols[i][0])]
    while len(keep) < n:
        keep.append(max((i for i in range(len(cols)) if i not in keep),
                         key=lambda i: min(wdist(cols[i], cols[k]) for k in keep)))
    return [(cols[i], None) for i in sorted(keep)]


def expand(base, n=NCOL):
    """Return [(yuv, parents)] with exactly n colours (all of them if n is None).

    Fewer than n base colours: topped up with mixes. More: reduce()d to n.
    parents is None for a base colour, else the (i, j) indices it mixes.
    """
    base = list(dict.fromkeys(base))
    if n is None or len(base) >= n:
        return reduce(base, n) if n else [(hex_to_yuv(h), None) for h in base]
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


def expanded(full=False):
    """Every palette at NCOL colours (big ones: their PICK); full=True keeps
    big palettes whole."""
    return {name: expand(cols if full or name not in PICK else PICK[name],
                         max(NCOL, len(cols)) if full else NCOL)
            for name, cols in BASE.items()}


def main():
    pals = expanded(full=sys.argv[1:] == ['full'])
    if sys.argv[1:] == ['asm']:
        print('PALETTES:                               @ NPAL x NCOL colours, JPEG/JFIF (Y,U,V)')
        for name, cols in pals.items():
            print('    .byte ' + ', '.join('%d,%d,%d' % c for c, _ in cols) + f'   @ {name}')
        return
    for name, cols in pals.items():
        base = BASE[name]
        print(name)
        for c, par in cols:
            how = 'base' if par is None else f'mix {base[par[0]]}+{base[par[1]]}'
            print(f'  #{yuv_to_hex(c)}  Y,U,V = {c[0]:3},{c[1]:3},{c[2]:3}  {how}')


if __name__ == '__main__':
    main()
