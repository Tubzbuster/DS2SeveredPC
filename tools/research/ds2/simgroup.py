"""SimGroup (level objects) in Severed's packed format, block 011795D9.

Layout: file header (Gibbed.Visceral SimGroup/FileHeader), object hash
list, 0x44-byte object records, matrices, groups (hash, count, member
offsets), then, 16-aligned, the data block: header (magic, size, 0x18,
u16 x2, record count, record table offset), type-name table (sdbm hash of
the class name, class version), record table (offset, object hash,
length, u16, u16 type-name index) and the records. A record is the
class's fields at the PC engine's offsets (simgroup_schema.json, read
from the running PC game by tools/probe), followed by string data.

360 -> PC: 32-bit values swapped except u16 fields (counts), bytes (bools,
byte flag sets) and string data kept; group hashes recomputed: sdbm over
the member objects' class-name hashes in native (little-endian) order.
"""
import json, os, struct

BLOCK = 0x011795D9
OLD_BLOCK = 0x91C8773C
ARRAY = 0x13
STRUCT = 0x16
# bytes per element and how to swap it: 4 = u32 words, 2 = u16, 1 = raw
TYPES = {
    0x00: (4, 4), 0x01: (4, 4), 0x02: (4, 4), 0x03: (2, 2), 0x04: (2, 2),
    0x05: (1, 1), 0x07: (1, 1), 0x08: (4, 1), 0x0A: (4, 4), 0x0B: (4, 4),
    0x0C: (16, 4), 0x0D: (12, 4), 0x0E: (16, 4), 0x0F: (64, 4),
    0x10: (4, 4), 0x11: (12, 4),
}
# Severed-only classes with no PC equivalent: their objects become blank
# NavFolder objects (a field-less grouping class), because an unknown class
# in a group appears to stop the whole group from being set up on PC (the
# level's ZoneWorld and StreamSets never activated). 2B747EB6 is the
# Pulse Rifle pre-upgrade (to be redone in Lua), 8F917978 / 742ECD09 are
# unidentified (one hash / one u32 each).
NEUTRAL = {0x2B747EB6, 0x8F917978, 0x742ECD09}
NEUTRAL_AS = 'NavFolder'
M = 0xFFFFFFFF
_SCHEMA = None

# Severed-only classes (absent from the PC exe) whose records have exactly the
# layout of a PC class: the object is re-labelled as that class. Matched by
# fitting every PC layout to the records (all message strings resolve, no
# data outside the fields; see docs/FINDINGS.md).
REMAP = {
    0xAC69505E: 'ShipStore',                 # store kiosks (5), DLC item fields set
    0x8F69BA55: 'SaveKiosk',                 # SaveKioskExt: save stations (9)
    0xAA6A826D: 'SimplePressAndHoldSwitch',  # quarry / mining camp switches (4)
    0x9F75D02A: 'RigAnnouncementSystem',     # RIG announcement setup (1)
    0xA1C89AA7: 'UIEndOfGameData',           # UIEndOfGameDataExt: end of DLC (1); 20 extra zero bytes
}

# Store lists (ItemStoreList, one array of item GUIDs): Severed lists Gabe
# versions of the suit packs next to his starting suit. Gabe does not
# change suits through the store in Severed, and choosing one on PC
# crashed the game, so these entries are left out of the lists (the rest
# move up). Kept: the starting "PDLC Weller Suit" {31CB97F2-70FE-C517-...}.
STORE_HIDDEN = {
    (0x31CBB1C2, 0xACB209C3),   # Security Suit
    (0x31CBB1C3, 0x3916B805),   # (hacker suit)
    (0x31CBB1C3, 0xFB56CB01),   # PDLC Miner Suit
    (0x31CBB1C4, 0x8FBB6FD5),   # PDLC Security Suit
    (0x31CBB1C4, 0xE85D26F3),   # PDLC Advanced Suit
    (0x31CBB1C5, 0x57992363),   # PDLC Heavy Damage
    (0x31CBB1C5, 0xC2AB6BA9),   # PDLC Quick Draw Suit
    (0x31CBB1C6, 0x2FCEFA83),   # PDLC EarthGov Suit
    (0x31CBB1C6, 0x8AB40943),   # PDLC Brushed Alum Suit
    (0x31CBB1C6, 0xD0F37D3D),   # PDLC Bloody Suit
}

# Objects moved (metres, +Y up) by the converter: none at present. Tests
# 1-4 (the two corpses in drill_tunnel_01 raised 12 cm, then each moved
# 200 m below the level, then Gabe's gun proxy, then the tunnel's 4
# ScriptableProps) did not stop the thump in the opening scene.
NUDGE = {}

# Message listeners moved to another message: {object hash: (old message,
# new message)} (CMD_SetTargetName, the record's first field: hash, 0,
# string offset). The hanging state (PlayerChangeState) holds Gabe at
# hanging height; the script releases it on ses_player_01_03_end, after the
# drop animation, so on PC he finishes the drop at ceiling height and pops
# through it. Releasing it as the drop sequence starts (mm_ses_01_03_trigger
# starts ses_player_01_03) lets him come down (F7 test: released early, he
# fell straight to the floor). The end's own release finds no listener.
RETARGET = {
    0x29515ABF: (b'PlayerChangeState_hanging_combat_deactivate', b'mm_ses_01_03_trigger'),
}


def msg_hash(name):
    """message names: sdbm of the lower-case name, multiplier 0x1003F"""
    h = 0
    for c in name.lower():
        h = (h * 0x1003F + c) & M
    return h


def _retarget(out, x, base, length, oh, stats):
    old, new = RETARGET[oh]
    h, z, rel = struct.unpack_from('>III', x, base)
    t = base + 8 + rel
    if h != msg_hash(old) or z or x[t:t + len(old) + 1] != old + b'\0' or len(new) > len(old):
        stats['retarget_skipped'] = stats.get('retarget_skipped', 0) + 1
        return
    struct.pack_into('<I', out, base, msg_hash(new))
    out[t:t + len(old) + 1] = new + bytes(len(old) + 1 - len(new))
    stats['retargeted'] = stats.get('retargeted', 0) + 1


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = {int(k, 16): v for k, v in
                   json.load(open(os.path.join(os.path.dirname(__file__), 'simgroup_schema.json'))).items()}
    return _SCHEMA


def sdbm(b, h=0):
    for c in b:
        h = (h * 65599 + c) & M
    return h


def _swap(out, x, o, size, unit):
    if unit == 4:
        n = size // 4
        out[o:o + 4 * n] = struct.pack('<%dI' % n, *struct.unpack_from('>%dI' % n, x, o))
    elif unit == 2:
        n = size // 2
        out[o:o + 2 * n] = struct.pack('<%dH' % n, *struct.unpack_from('>%dH' % n, x, o))


class Unknown(Exception):
    pass


def _record(out, x, base, length, cls, stats):
    """Converts one record in place; cls is the schema entry or None."""
    if cls is None:
        # class the PC engine does not have: 32-bit words up to the strings
        stats['unknown_class'] = stats.get('unknown_class', 0) + 1
        end = length
        for o in range(0, length - 11, 4):
            h, z, rel = struct.unpack_from('>III', x, base + o)
            t = o + 8 + rel
            if h and z == 0 and 0 < t < length:
                e = x.find(b'\0', base + t, base + length)
                s = x[base + t:e] if e >= 0 else b''
                if s and (sdbm(s.lower()) == h or sdbm(s) == h):
                    end = min(end, t)
        end = end // 4 * 4
        _swap(out, x, base, end, 4)
        return
    if length < cls['size']:
        raise Unknown('record shorter than its class')
    _struct(out, x, base, cls)
    if cls['name'] == 'ItemStoreList':
        _hide_store_items(out, x, base, cls, stats)


def _nudge(out, x, oC, count, stats):
    """object records (0x44 bytes: GUID at +12, matrix offset at +48;
    matrices are 16 floats, translation at +48): move NUDGE objects"""
    for i in range(count):
        e = oC + 0x44 * i
        d = NUDGE.get(struct.unpack_from('>4I', x, e + 12))
        m = struct.unpack_from('>I', x, e + 48)[0]
        if d and m and m + 64 <= len(x):
            t = struct.unpack_from('>3f', x, m + 48)
            struct.pack_into('<3f', out, m + 48, *(a + b for a, b in zip(t, d)))
            stats['nudged'] = stats.get('nudged', 0) + 1


def _hide_store_items(out, x, base, cls, stats):
    off, _, _, count = cls['fields'][0][:4]
    o = base + off
    keep = [out[o + 16 * i:o + 16 * i + 16] for i in range(count)
            if struct.unpack_from('>II', x, o + 16 * i) not in STORE_HIDDEN]
    stats['store_items_hidden'] = stats.get('store_items_hidden', 0) + count - len(keep)
    out[o:o + 16 * count] = b''.join(keep) + bytes(16 * (count - len(keep)))


def _struct(out, x, base, cls):
    for f in cls['fields']:
        off, typ = f[0], f[1]
        if typ == ARRAY:
            count, elem = f[3], f[4]
            if elem == STRUCT:
                sub = _class(f[5])
                for i in range(count):
                    _struct(out, x, base + off + i * sub['size'], sub)
                continue
            if elem not in TYPES:
                raise Unknown('array element type %#x' % elem)
            size, unit = TYPES[elem]
            for i in range(count):
                _swap(out, x, base + off + i * size, size, unit)
        elif typ == STRUCT:
            _struct(out, x, base + off, _class(f[3]))
        else:
            if typ not in TYPES:
                raise Unknown('field type %#x' % typ)
            size, unit = TYPES[typ]
            _swap(out, x, base + off, size, unit)


def _class(h):
    c = schema().get(int(h, 16)) if h else None
    if c is None:
        raise Unknown('embedded struct of unknown class %s' % h)
    return c


def convert(x, stats=None):
    if stats is None:
        stats = {}
    if len(x) < 0x3C:
        return None
    hsz, o8, oC, o10 = struct.unpack_from('>IIII', x, 4)
    n14, n16, n18 = struct.unpack_from('>HHH', x, 0x14)
    B = (hsz + 15) // 16 * 16
    if B + 0x18 > len(x) or struct.unpack_from('>I', x, B)[0] != BLOCK:
        return None
    out = bytearray(x)
    # header part: 32-bit words, u16 counts at 0x14-0x1B
    _swap(out, x, 0, B, 4)
    for o in (0x14, 0x18):
        _swap(out, x, o, 4, 2)
    # block
    _, size, hs, v1, v2, cnt, toff = struct.unpack_from('>IIIHHII', x, B)
    if B + size != len(x):
        return None
    _swap(out, x, B, 0x0C, 4)
    _swap(out, x, B + 0x0C, 4, 2)
    _swap(out, x, B + 0x10, 8, 4)
    sch = schema()
    by_name = {c['name']: (k, c) for k, c in sch.items()}
    names, orig = [], []
    for i in range((toff - hs) // 8):
        h, ver = struct.unpack_from('>II', x, B + hs + 8 * i)
        orig.append(h)
        if h in NEUTRAL and h not in sch:
            nh, c = by_name[NEUTRAL_AS]
            stats['neutralised'] = stats.get('neutralised', 0) + 1
            h, ver = nh, c['version']
        elif h not in sch and h in REMAP:
            nh, c = by_name[REMAP[h]]
            stats['remapped'] = stats.get('remapped', {})
            stats['remapped'][REMAP[h]] = stats['remapped'].get(REMAP[h], 0) + 1
            h, ver = nh, c['version']
        names.append((h, ver))
        out[B + hs + 8 * i:B + hs + 8 * i + 8] = struct.pack('<II', h, ver)
    by_obj = {}
    for i in range(cnt):
        e = B + toff + 16 * i
        ro, oh, ln, a, b = struct.unpack_from('>IIIHH', x, e)
        _swap(out, x, e, 12, 4)
        _swap(out, x, e + 12, 4, 2)
        h, ver = names[b] if b < len(names) else (None, None)
        by_obj[oh] = (orig[b], h) if b < len(names) else (0, 0)
        if ln == 0:
            continue
        cls = sch.get(h)
        if cls is not None and cls['version'] != ver:
            raise Unknown('%s version %d, PC has %d' % (cls['name'], ver, cls['version']))
        if orig[b] in NEUTRAL and orig[b] not in sch:
            out[B + ro:B + ro + ln] = bytes(ln)      # blank NavFolder
            continue
        _record(out, x, B + ro, ln, cls, stats)
        if oh in RETARGET:
            _retarget(out, x, B + ro, ln, oh, stats)
    # group hashes: sdbm over the members' class-name hashes, PC byte order
    if o10:
        for i in range(n18):
            e = struct.unpack_from('>I', x, o10 + 4 * i)[0]
            gcount = struct.unpack_from('>I', x, e + 4)[0]
            offs = struct.unpack_from('>%dI' % gcount, x, e + 8)
            members = [by_obj.get(struct.unpack_from('>I', x, q)[0], (0, 0)) for q in offs]
            if sdbm(struct.pack('>%dI' % gcount, *[m[0] for m in members])) == struct.unpack_from('>I', x, e)[0]:
                out[e:e + 4] = struct.pack('<I', sdbm(struct.pack('<%dI' % gcount, *[m[1] for m in members])))
            else:
                stats['group_hash_unverified'] = stats.get('group_hash_unverified', 0) + 1
    _nudge(out, x, oC, n16, stats)
    return bytes(out)
