"""Severed assets the PC game already has.

Severed reuses many base-game assets (kiosks, benches, doors, textures,
effects). Where the PC game has an asset with the same type, name and ids
(the key that pairs the base game's PC and 360 assets), its own PC version
is used instead of a conversion: exact, and it covers assets the PC tools
re-exported in another layout (e.g. kiosk_public01_am: different vertex
record sizes, which crashed the PC's skinning code when converted).

ds2/pc_assets.json (learn_pc_assets.py) maps each such key to the archive
entry hash of a PC stream holding it; the assets are read from the user's
own game archives.
"""
import json, os

# asset types taken from the PC game; meshes with their volatile data and
# textures with their headers are taken together or not at all
TYPES = {'Mesh', 'MeshVolatile', 'tg4h', 'tg4d', 'Material', 'VFX', 'MetaModel', 'HKX', 'BNK', 'RCB'}
PAIRS = {'Mesh': 'MeshVolatile', 'tg4h': 'tg4d'}


def key(typ, name, ids):
    return '%s|%s|%s' % (typ, name, '.'.join('%08X' % i for i in ids))


def load():
    p = os.path.join(os.path.dirname(__file__), 'pc_assets.json')
    return json.load(open(p)) if os.path.exists(p) else {}


def plan(assets, table):
    """indices of the assets of one stream to take from the PC, as
    {index: entry hash}; a Mesh / tg4h and the MeshVolatile / tg4d right
    after it go together"""
    out = {}
    skip = set()
    for i, a in enumerate(assets):
        if i in skip or a.type not in TYPES:
            continue
        k = table.get(key(a.type, a.name, a.ids))
        if a.type in PAIRS:
            nxt = assets[i + 1] if i + 1 < len(assets) else None
            if nxt is not None and nxt.type == PAIRS[a.type]:
                k2 = table.get(key(nxt.type, nxt.name, nxt.ids))
                skip.add(i + 1)
                if k and k2:
                    out[i], out[i + 1] = k, k2
                continue
        elif a.type in PAIRS.values():
            continue                       # only together with its Mesh / tg4h
        if k:
            out[i] = k
    return out
