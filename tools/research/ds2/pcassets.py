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


# Severed meshes that are a base-game mesh with other materials: built from
# the PC game's own mesh (same tables, in the same order), with Severed's
# material ids written into the tables that differ. exterior_black_win
# (Severed's gunship hull) is the base game's gunship_hi_02 exterior.dae
# with the windows (window_sort_1_Shape) given another material; converted,
# its texture coordinates came out smeared (the PC exporter merges and
# re-lays its vertex buffers).
#   Severed key -> (PC stream entry, PC mesh key, PC volatile key)
DERIVED = {
    'Mesh|exterior_black_win.dae|01961BED.01B32676.01B32676.01B32676.3A5DD4F6': (
        '2E72F4DC',
        'Mesh|exterior.dae|01961BED.36BD9CD9.36BD9CD9.36BD9CD9.4D8D3C4E',
        'MeshVolatile|exterior.dae.volatile|E2BA6D49.C9426326.C9426326.C9426326.B272C3B1'),
}


def derive_mesh(pc_mesh, sev_360_mesh):
    """the PC mesh with the 360 mesh's material ids (DT1 +0x0C), or None if
    the tables do not line up (count, or more than one table renamed:
    Severed renamed the hull's window_sort_1_Shape to window_01Shape)"""
    import struct
    from . import geo
    gp, gx = geo.parse(pc_mesh, False), geo.parse(sev_360_mesh, True)
    if len(gp.tables) != len(gx.tables):
        return None
    out = bytearray(pc_mesh)
    name = lambda d, t: d[t.name_offset:d.find(b'\0', t.name_offset)] if t.name_offset else b''
    if sum(name(pc_mesh, tp) != name(sev_360_mesh, tx) for tp, tx in zip(gp.tables, gx.tables)) > 1:
        return None
    for tp, tx in zip(gp.tables, gx.tables):
        struct.pack_into('<I', out, tp.entry + 0x0C, struct.unpack_from('>I', sev_360_mesh, tx.entry + 0x0C)[0])
    return bytes(out)


def match_materials(pc_mesh, sev_360_mesh):
    """a mesh taken from the PC game, with the material ids (DT1 +0x0C) of
    Severed's own mesh where they differ, as (bytes, [(table, PC id,
    Severed id)]); None if nothing differs or the tables do not line up.
    The PC copy of a mesh Severed re-used can name another material than
    Severed's: the Oracle Twitcher's body and limbs are the PC game's, but
    Severed gives them its own material, so the PC ids name a material that
    is not loaded in the landing bay (exe 0x8347EA reads a null material)."""
    import struct
    from . import geo
    gp, gx = geo.parse(pc_mesh, False), geo.parse(sev_360_mesh, True)
    if len(gp.tables) != len(gx.tables):
        return None
    name = lambda d, t: d[t.name_offset:d.find(b'\0', t.name_offset)] if t.name_offset else b''
    if any(name(pc_mesh, tp) != name(sev_360_mesh, tx) for tp, tx in zip(gp.tables, gx.tables)):
        return None
    out = bytearray(pc_mesh)
    changed = []
    for i, (tp, tx) in enumerate(zip(gp.tables, gx.tables)):
        old = struct.unpack_from('<I', pc_mesh, tp.entry + 0x0C)[0]
        new = struct.unpack_from('>I', sev_360_mesh, tx.entry + 0x0C)[0]
        if old != new:
            struct.pack_into('<I', out, tp.entry + 0x0C, new)
            changed.append((i, old, new))
    return (bytes(out), changed) if changed else None
