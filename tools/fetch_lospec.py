#!/usr/bin/env python3
"""Fetch the Lospec palettes the site's editor offers (names, colours, authors) into
tools/lospec_palettes.json, from lospec.com/palette-list/<slug>.json.

  python3 tools/fetch_lospec.py

editor_data.py reads the JSON (no network needed to build). `author` is what Lospec lists
(empty for some); `creator` is who made it where Lospec doesn't say but it is well known
(CREATORS below, only ones I'm sure of). The editor shows creator, else author, else nothing.
GB: 4-colour Game Boy palettes for the Game Boy mode. PALETTES: up to 32 colours, for the
other presets, each with the 1-3 character tag the camera shows for it.
"""
import json, os, urllib.request

GB = ['nintendo-gameboy-bgb', 'links-awakening-sgb', 'pokemon-sgb', 'gb-chocolate', 'kirokaze-gameboy',
      '2bit-demichrome', 'ice-cream-gb', 'mist-gb', 'wish-gb', 'coldfire-gb', 'rustic-gb', 'lava-gb',
      'blk-aqu4', 'spacehaze', 'moonlight-gb', 'ayy4']
PALETTES = [  # (slug, tag)
    ('pico-8', 'P8'), ('dawnbringer-16', 'D16'), ('dawnbringer-32', 'D32'), ('arne-16', 'A16'),
    ('arne-32', 'A32'), ('endesga-16', 'E16'), ('endesga-32', 'EG'), ('sweetie-16', 'S16'),
    ('vinik24', 'V24'), ('steam-lords', 'STL'), ('zx-spectrum', 'ZX'), ('apple-ii', 'A2'),
    ('fantasy-24', 'F24'), ('cc-29', 'C29'), ('na16', 'N16'), ('mulfok32', 'M32'), ('fading-16', 'F16'),
    ('europa-16', 'EU'), ('lost-century', 'LC'), ('galaxy-flame', 'GF'), ('jehkoba32', 'J32'),
    ('bubblegum-16', 'B16'), ('pollen8', 'PL8'), ('sunset-8', 'SS8'), ('nyx8', 'NY8'),
    ('slso8', 'SL8'), ('oil-6', 'O6'), ('midnight-ablaze', 'MA'), ('twilight-5', 'T5')]
CREATORS = {'pico-8': 'Lexaloffle', 'dawnbringer-16': 'DawnBringer', 'dawnbringer-32': 'DawnBringer',
            'arne-16': 'Arne', 'arne-32': 'Arne', 'sweetie-16': 'GrafxKid'}
# Lospec's author fields that are decorated; the person's name
CLEAN = {'🍍PineappleOnPizza🍍(Comissions Open)': 'PineappleOnPizza', 'Inkpendude ': 'Inkpendude'}


def fetch(slug):
    req = urllib.request.Request(f'https://lospec.com/palette-list/{slug}.json', headers={'User-Agent': 'Mozilla/5.0'})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    assert 'colors' in d, f'{slug}: {d}'
    return {'slug': slug, 'name': d['name'].strip(), 'author': CLEAN.get(d['author'], d['author']).strip(),
            'creator': CREATORS.get(slug, ''), 'colours': d['colors']}


out = {'gb': [fetch(s) for s in GB]}
out['palettes'] = []
for slug, tag in PALETTES:
    p = fetch(slug)
    assert 1 <= len(p['colours']) <= 32, f'{slug}: {len(p["colours"])} colours'
    out['palettes'].append({**p, 'tag': tag})
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lospec_palettes.json'), 'w', encoding='utf-8'),
          indent=1, ensure_ascii=False)
print(len(out['gb']), 'Game Boy palettes,', len(out['palettes']), 'others')
