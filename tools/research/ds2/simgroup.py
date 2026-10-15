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
M = 0xFFFFFFFF
_SCHEMA = None


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
    names = []
    for i in range((toff - hs) // 8):
        h, ver = struct.unpack_from('>II', x, B + hs + 8 * i)
        names.append((h, ver))
        _swap(out, x, B + hs + 8 * i, 8, 4)
    sch = schema()
    by_obj = {}
    for i in range(cnt):
        e = B + toff + 16 * i
        ro, oh, ln, a, b = struct.unpack_from('>IIIHH', x, e)
        _swap(out, x, e, 12, 4)
        _swap(out, x, e + 12, 4, 2)
        h, ver = names[b] if b < len(names) else (None, None)
        by_obj[oh] = h
        if ln == 0:
            continue
        cls = sch.get(h)
        if cls is not None and cls['version'] != ver:
            raise Unknown('%s version %d, PC has %d' % (cls['name'], ver, cls['version']))
        _record(out, x, B + ro, ln, cls, stats)
    # group hashes: sdbm over the members' class-name hashes, PC byte order
    if o10:
        for i in range(n18):
            e = struct.unpack_from('>I', x, o10 + 4 * i)[0]
            gcount = struct.unpack_from('>I', x, e + 4)[0]
            offs = struct.unpack_from('>%dI' % gcount, x, e + 8)
            members = [by_obj.get(struct.unpack_from('>I', x, q)[0]) or 0 for q in offs]
            if sdbm(struct.pack('>%dI' % gcount, *members)) == struct.unpack_from('>I', x, e)[0]:
                out[e:e + 4] = struct.pack('<I', sdbm(struct.pack('<%dI' % gcount, *members)))
            else:
                stats['group_hash_unverified'] = stats.get('group_hash_unverified', 0) + 1
    return bytes(out)
