"""Mesh 360 -> PC converter (structure-preserving).

Regions (see geo.py): header, DataTable1 entries, DataTable2 descriptors
and the remaining metadata use learned/standard byte orders; vertex records
are converted per slot (floats swapped, DEC3N normals and signed-byte
tangents re-encoded as PC unsigned bytes, bone indices kept, weights u16
swapped); index buffers u16 swapped; names, bone palettes and other text
kept as stored.
"""
import math, struct
from . import geo, templates as T


def _ub(v):
    return max(0, min(255, int(math.floor((max(-1.0, min(1.0, v)) + 1.0) * 127.5))))


def _s8(c):
    return c - 256 if c >= 128 else c


def normal(w):
    v = struct.unpack('>I', w)[0]
    out = []
    for sh in (0, 10, 20):
        c = (v >> sh) & 1023
        out.append(_ub((c - 1024 if c >= 512 else c) / 511.0))
    return bytes(out + [255])


def tangent32(w):        # skinned records: x y z w, PC flips the handedness byte
    if w[:3] == b'\0\0\0':
        return bytes(4)
    xyz = [_ub(_s8(c) / 127.0) for c in w[:3]]
    return bytes(xyz + [0 if _s8(w[3]) > 0 else 255])


def tangent20(w):        # 0x14 records: stored w z y x
    r = w[::-1]
    if r[:3] == b'\0\0\0':
        return b'\0\0\0\xff'
    xyz = [_ub(_s8(c) / 127.0) for c in r[:3]]
    return bytes(xyz + [255 if _s8(r[3]) > 0 else 0])


def rec_size(t):
    return 0x20 if t.vert_size == -1 else 0x14 if t.lod_type == 4 else 0x0C if t.lod_type == 5 else None


def _swap(b, o, n=4):
    b[o:o + n] = b[o:o + n][::-1]


_NAMECH = set(b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./\\-:')


def _texty_run(x, i):
    """True if x[i:i+4] lies in a NUL-terminated name-like string of 8+
    characters (letters, digits, _ . / \\ - :)."""
    j = i
    while j > 0 and i - j < 256 and x[j - 1] in _NAMECH:
        j -= 1
    k = i
    while k < len(x) and x[k] in _NAMECH:
        k += 1
    return k - j >= 8 and k < len(x) and x[k] == 0 and j <= i < k + 1


def convert(x, tmpl):
    """tmpl: dict label -> list of permutations, for header/dt1/dt2."""
    a = geo.parse(x, True)
    out = bytearray(x)
    done = bytearray(len(x))

    def mark(s, e):
        done[s:e] = b'\1' * (e - s)

    def templ(s, e, label, size):
        perms = tmpl[label]
        for o in range(s, e - size + 1, size):
            out[o:o + size] = T.apply(perms, x[o:o + size])
        mark(s, e)

    templ(0, 0x100, 'header', 0x100)
    out[8:12] = struct.pack('<I', 3)                    # platform: PC
    templ(a.data_table1, a.data_table1 + geo.DT1_ENTRY * a.table_count, 'dt1', geo.DT1_ENTRY)
    templ(a.data_table2, a.data_table2 + 16 * len(a.dt2), 'dt2', 16)
    for t in a.tables:   # u16 at +0xAE: the 360 sometimes stores face count + 1, the PC the face count
        v = struct.unpack_from('>H', x, t.entry + 0xAE)[0]
        if v == t.face_count + 1:
            out[t.entry + 0xAE:t.entry + 0xB0] = struct.pack('<H', t.face_count)
    for t in a.tables:
        rs = rec_size(t)
        if rs and t.vert_offset and t.vert_offset + rs * t.vert_count <= len(x):
            for v in range(t.vert_count):
                o = t.vert_offset + rs * v
                for f in range(0, 12, 4):
                    _swap(out, o + f)
                if rs >= 0x14:
                    out[o + 12:o + 16] = normal(x[o + 12:o + 16])
                    out[o + 16:o + 20] = (tangent32 if rs == 0x20 else tangent20)(x[o + 16:o + 20])
                if rs == 0x20:
                    for f in range(24, 32, 2):
                        _swap(out, o + f, 2)
            mark(t.vert_offset, t.vert_offset + rs * t.vert_count)
        if t.face_offset and t.face_offset + 2 * t.face_count <= len(x):
            for o in range(t.face_offset, t.face_offset + 2 * t.face_count, 2):
                _swap(out, o, 2)
            mark(t.face_offset, t.face_offset + 2 * t.face_count)
        if t.bone_palette_offset and t.palette_count:
            mark(t.bone_palette_offset, t.bone_palette_offset + 2 * t.palette_count)
        if t.name_offset:
            mark(t.name_offset, x.find(b'\0', t.name_offset) + 1)
    # everything else: 32-bit values, except text
    for i in range(0, len(x) - 3, 4):
        if done[i] or done[i + 3]:
            continue
        if _texty_run(x, i):
            continue
        _swap(out, i)
    return bytes(out)
