#!/usr/bin/env python3
"""Palette variants built from endesga32 (EG): regraded and/or thinned.

EG reads as "a full set of colours, colour-graded": its near-neutral colours
are one steady cool ramp (OKLCH hue ~260-295, chroma ~0.06 in the midtones,
fading to pure white), next to a warm skin/wood ramp, four greens and a few
red/yellow/cyan accents. db16 has no such grade: its neutrals wander from
violet through olive and pink-beige to a green-white.

So a grade here is a tint curve: an OKLab (a, b) offset as a function of
lightness L. EG's own curve (TINT_C, TINT_H below) was measured from its
neutral colours. Regrading subtracts it from every colour and adds a new one,
which shifts the chromatic colours along with the greys, as a real colour
grade would. Thinning drops colours at random, but never the darkest, the
lightest, the cool neutral ramp (it carries the grade: without it a white wall
jumps to neon green) or the last colour of a family, so the photo keeps skin,
foliage and sky and just gets coarser (funkier).

A variant is a spec string, colon-separated, all parts optional:
  eg                  EG itself
  eg:t200             tint hue 200 (teal) instead of EG's blue
  eg:t200:x1.5        ... at 1.5x EG's tint strength (x0 = no tint at all)
  eg:t220/60          split tone: shadows hue 220, highlights hue 60
  eg:sat120           chroma of everything x1.2
  eg:d12r3            drop 12 of the 32 colours, random seed 3

  grade.py SPEC...    print the palettes (hex, OKLCH, family)
"""
import math, random, sys
from palettes import BASE

# EG's measured tint: chroma and hue of its neutral ramp, by lightness.
TINT_L = [0.0, 0.21, 0.39, 0.52, 0.69, 0.84, 1.0]
TINT_C = [0.02, 0.034, 0.059, 0.053, 0.041, 0.027, 0.0]
TINT_H = [295, 294, 271, 265, 259, 259, 259]


def interp(x, xs, ys):
    for i in range(len(xs) - 1):
        if x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + (ys[i + 1] - ys[i]) * t
    return ys[-1]


def hex_to_oklab(h):
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_rgb(L, a, b):
    """Gamma-encoded sRGB floats (may be out of 0..1)."""
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (4.0767416621 * l_ - 3.3077118591 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return [12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055 for x in lin]


def oklab_to_hex(L, a, b):
    """Clip into sRGB by lowering chroma (keeps lightness and hue)."""
    L = min(max(L, 0), 1)
    while True:
        rgb = oklab_to_rgb(L, a, b)
        if all(-1e-4 <= x <= 1 + 1e-4 for x in rgb) or abs(a) + abs(b) < 1e-4:
            return ''.join(f'{max(0, min(255, round(x * 255))):02X}' for x in rgb)
        a, b = a * 0.95, b * 0.95


def lch(h):
    L, a, b = hex_to_oklab(h)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def tint(L, hue=None, x=1.0):
    """(a, b) offset of a tint curve: EG's chroma curve, at EG's hue or `hue`
    (a number, or a (shadow, highlight) pair blended between L 0.3 and 0.8)."""
    c = interp(L, TINT_L, TINT_C) * x
    if hue is None:
        h = interp(L, TINT_L, TINT_H)
    elif isinstance(hue, tuple):
        t = min(max((L - 0.3) / 0.5, 0), 1)
        d = (hue[1] - hue[0] + 180) % 360 - 180          # shortest way round
        h = hue[0] + d * t
    else:
        h = hue
    return c * math.cos(math.radians(h)), c * math.sin(math.radians(h))


def family(h):
    """Rough role of a colour in a photo, for thinning."""
    L, C, H = lch(h)
    if C < 0.07 and (200 <= H < 300 or C < 0.01):
        return 'cool'
    if C < 0.11 and (H >= 340 or H < 90):
        return 'warm'
    if 110 <= H < 215:
        return 'green'
    if 215 <= H < 300:
        return 'blue'
    if 50 <= H < 110:
        return 'yellow'
    return 'red'


def regrade(hexes, hue=None, x=1.0, sat=1.0):
    """Swap EG's tint for another one. The shift is weighted by how neutral a
    colour is: the greys take all of it, saturated colours only a quarter
    (shifting those fully turns EG's rust red orange, for one)."""
    out = []
    for h in hexes:
        L, a, b = hex_to_oklab(h)
        ea, eb = tint(L)
        na, nb = tint(L, hue, x)
        w = max(0.25, 1 - math.hypot(a, b) / 0.12)
        a, b = a + w * (na - ea), b + w * (nb - eb)
        out.append(oklab_to_hex(L, a * sat, b * sat))
    return list(dict.fromkeys(out))


def thin(hexes, n, seed):
    """Drop n colours at random, keeping the darkest, the lightest, the cool
    ramp and at least one colour of every other family."""
    r = random.Random(seed)
    keep = list(hexes)
    ends = {min(keep, key=lambda h: lch(h)[0]), max(keep, key=lambda h: lch(h)[0])}
    for _ in range(n):
        fams = [family(h) for h in keep]
        can = [h for h, f in zip(keep, fams) if h not in ends and f != 'cool' and fams.count(f) > 1]
        if not can:
            break
        keep.remove(r.choice(can))
    return keep


def variant(spec):
    """Hex colours for a spec string (see the module docstring)."""
    parts = spec.split(':')
    assert parts[0] == 'eg', 'only eg-based variants for now'
    hue, x, sat, drop = None, 1.0, 1.0, None
    for p in parts[1:]:
        if p.startswith('t'):
            hs = p[1:].split('/')
            hue = float(hs[0]) if len(hs) == 1 else (float(hs[0]), float(hs[1]))
        elif p.startswith('x'):
            x = float(p[1:])
        elif p.startswith('sat'):
            sat = float(p[3:]) / 100
        elif p.startswith('d'):
            n, seed = p[1:].split('r')
            drop = int(n), int(seed)
        else:
            raise ValueError(f'{spec}: unknown part {p!r}')
    hexes = BASE['endesga32']
    if hue is not None or x != 1 or sat != 1:
        hexes = regrade(hexes, hue, x, sat)
    if drop:
        hexes = thin(hexes, *drop)
    return hexes


if __name__ == '__main__':
    for spec in sys.argv[1:]:
        hexes = variant(spec)
        print(f'{spec} ({len(hexes)})')
        for h in sorted(hexes, key=lambda h: lch(h)[0]):
            L, C, H = lch(h)
            print(f'  #{h}  L={L:.2f} C={C:.3f} h={H:3.0f}  {family(h)}')
