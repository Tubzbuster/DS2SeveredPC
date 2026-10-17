"""Mesh 360 -> PC converter (structure-preserving).

Regions (see geo.py): header, DataTable1 entries, DataTable2 descriptors
and the remaining metadata use learned/standard byte orders; vertex records
are converted per slot (floats swapped, DEC3N normals and signed-byte
tangents re-encoded as PC unsigned bytes, bone indices kept, weights u16
swapped); index buffers u16 swapped; names, bone palettes and other text
kept as stored.
"""
import math, struct
from . import geo, strips, templates as T


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
    for t in a.tables:   # u32 at +0x68: second vertex buffer index of CPU-skinned tables (the template leaves it raw)
        out[t.entry + 0x68:t.entry + 0x6C] = x[t.entry + 0x68:t.entry + 0x6C][::-1]
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
    return restrip(x, a, out)


PRIM = 0x3C          # DT1 u16: primitive type (360 strip 6 -> PC strip 5), then u16 index count
STRIP_360, STRIP_PC = 6, 5
ALIGN = 0x80


GRID = 0x8C          # DT1 pointer: per-table grid


def _grid(x, out, t, pmap, n):
    """the table's spatial grid: 3 vectors (32-bit, converted already), then
    u16 nx, ny, nz, reference count, cell count, the references (positions
    of runs in the table's strip) and cell count + 1 offsets into them. The
    positions are carried through the strip join (the PC files' own grids
    were rebuilt by their tools with other runs)."""
    r = struct.unpack_from('>I', x, t.entry + GRID)[0]
    if not r:
        return
    nx, ny, nz, nref, ncell = struct.unpack_from('>5H', x, r + 0x30)
    if nx * ny * nz != ncell or r + 0x30 + 2 * (5 + nref + ncell + 1) > len(x):
        return
    refs = struct.unpack_from('>%dH' % nref, x, r + 0x3A)
    offs = struct.unpack_from('>%dH' % (ncell + 1), x, r + 0x3A + 2 * nref)
    refs = [min(pmap.get(v, v), max(n - 3, 0)) for v in refs]
    struct.pack_into('<%dH' % (5 + nref + ncell + 1), out, r + 0x30, nx, ny, nz, nref, ncell, *refs, *offs)


def restrip(x, a, out):
    """Triangle strips: the 360 restarts them with index 0xFFFF, which the PC
    cannot draw (it reads vertex 65535). Rebuild each strip table's indices
    with degenerate joins (strips.join) and the PC strip type. The grown index
    buffers are placed after the mesh's own data (before any volatile data
    the mesh itself carries); the volatile pointers
    (DT2 ptr >= local UV offset, relative to it), the mesh size (0x9C) and
    the total size (0x0C) move with it."""
    prim = {id(t): struct.unpack_from('>H', x, t.entry + PRIM)[0] for t in a.tables}
    if not any(p == STRIP_360 for p in prim.values()):
        return bytes(out)
    L = a.local_uv_offset
    tail = bytearray()
    moved = {}                                        # DT2 index -> (new ptr, new count)
    for i, (size, count, flags, ptr) in enumerate(a.dt2):
        if ptr >= L:
            continue
        tabs = [t for t in a.tables if t.face_offset and ptr <= t.face_offset < ptr + size]
        if not any(prim[id(t)] == STRIP_360 for t in tabs):
            continue
        new = []
        ranges = {}
        for t in sorted(tabs, key=lambda t: t.face_offset):
            key = (t.face_offset, t.face_count)
            if key not in ranges:
                idx = struct.unpack_from('>%dH' % t.face_count, x, t.face_offset)
                pmap = None
                if prim[id(t)] == STRIP_360:
                    idx, pmap = strips.join_map(idx)
                ranges[key] = (len(new), len(idx), pmap)
                new += idx
            if ranges[key][2] is not None:
                _grid(x, out, t, ranges[key][2], ranges[key][1])
            start, n = ranges[key][:2]
            e = t.entry
            struct.pack_into('<II', out, e + 0x30, n, start)
            if prim[id(t)] == STRIP_360:
                struct.pack_into('<HH', out, e + PRIM, STRIP_PC, n)
                v = struct.unpack_from('>H', x, e + 0xAE)[0]
                struct.pack_into('<H', out, e + 0xAE, max(v - 1, 0))
            struct.pack_into('<I', out, e + 0x88, L + len(tail) + 2 * start)
        out[ptr:ptr + size] = bytes(size)
        moved[i] = (L + len(tail), len(new))
        tail += struct.pack('<%dH' % len(new), *new)
        tail += bytes(-len(tail) % 16)
    if not moved:
        return bytes(out)
    tail += bytes(-(L + len(tail)) % ALIGN)
    delta = len(tail)
    for i, (size, count, flags, ptr) in enumerate(a.dt2):
        o = a.data_table2 + 16 * i
        if i in moved:
            p, n = moved[i]
            struct.pack_into('<II', out, o, 2 * n, n)
            struct.pack_into('<I', out, o + 12, p)
        elif ptr >= L:
            struct.pack_into('<I', out, o + 12, ptr + delta)
    struct.pack_into('<I', out, 0x9C, L + delta)
    struct.pack_into('<I', out, 0x0C, struct.unpack_from('>I', x, 0x0C)[0] + delta)
    # relocation table (header 0x48 count, 0x4C offset): {u32 field offset,
    # u32 value}; the engine writes each value back into its field at load
    # time, so the values must follow the moved pointers
    count, table = struct.unpack_from('>II', x, 0x48)
    for i in range(count):
        loc = struct.unpack_from('>I', x, table + 8 * i)[0]
        out[table + 8 * i + 4:table + 8 * i + 8] = out[loc:loc + 4]
    return bytes(out[:L]) + bytes(tail) + bytes(out[L:])     # volatile data some meshes carry
