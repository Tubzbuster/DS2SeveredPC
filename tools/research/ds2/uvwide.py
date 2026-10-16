"""Lightmap-shaded meshes: the PC's 20-byte UV stream.

A mesh table names its material at DataTable1 entry +0x0C (one of the
material's id words, `material.parse` a/b/c/d). On PC, every vertex buffer
holding a table whose material has the lightmap shader (a pass with shader
0x0E155D33) carries a 20-byte UV stream: u, v, 0.0, 1.0 and a colour. The
360 keeps its own 8-byte (u, v) or 12-byte (u, v, colour) stream there
(all such buffers in the PC/360 pairs). Left as on the 360, the PC shader
reads them with the wrong stride and draws the mesh black.

Widening the streams changes, in the PC mesh:
- each table with an 8/12-byte UV stream: entry +0x07 (UV format code: 6 for 8 bytes, 2 for 12)
  -> 0, entry +0x27 (UV size) -> 20;
- the vertex buffer's DataTable2 descriptor: flags byte +0x0A -> 0;
- the UV stream's descriptor: size = count * 20, flags +0x08 -> 0x14,
  +0x0A -> 0; streams after it in the volatile move up by the growth;
- the header word +0x0C: mesh plus volatile size.
The volatile (MeshVolatile asset) is rebuilt with the wider streams and
ends at its last stream, padded to 0x80.
"""
import struct
from . import geo, material

LM_SHADER = 0x0E155D33
DEFAULT_COLOUR = b'\0\0\0\xff'
TAIL = struct.pack('<ff', 0.0, 1.0)


def lm_ids(materials):
    """ids of the materials whose PC form has the lightmap shader, from
    (360 bytes, PC bytes) pairs"""
    out = set()
    for x, pc in materials:
        if pc is None:
            continue
        try:
            m, mx = material.parse(pc, False), material.parse(x, True)
        except (struct.error, IndexError):
            continue
        if any(s == LM_SHADER for s, f, t, _ in m.passes):
            out |= {v for v in (mx.a, mx.b, mx.c, mx.d) if v}
    return out


def widened(x, g, lm):
    """{vertex buffer index: UV stream index} to widen, for a 360 mesh: once
    one buffer holds a lightmap material, every 8/12-byte UV stream of the
    mesh is widened (as in the pairs)"""
    pairs, hit = {}, False
    for b, (size, count, flags, ptr) in enumerate(g.dt2[:-1]):
        s2, c2, f2, p2 = g.dt2[b + 1]
        if ptr < g.local_uv_offset <= p2 and count and c2 == count and s2 // c2 in (8, 12):
            pairs[b] = b + 1
    for t in g.tables:
        if t.uv_size in (8, 12) and struct.unpack_from('>I', x, t.entry + 0xC)[0] in lm:
            hit = True
    return pairs if hit else {}


def _new_offsets(g, widen):
    """old volatile offset -> new, for every external stream"""
    streams = sorted((ptr - g.local_uv_offset, i) for i, (size, count, flags, ptr) in enumerate(g.dt2)
                     if ptr >= g.local_uv_offset)
    out, grow = {}, 0
    for off, i in streams:
        out[i] = off + grow
        if i in widen.values():
            size, count = g.dt2[i][0], g.dt2[i][1]
            grow += 20 * count - size
    return out, grow


def mesh(y, x, g, widen):
    """patch the PC mesh y (converted from 360 mesh x, geo g) for the
    widened streams"""
    if not widen:
        return y
    y = bytearray(y)
    offs, grow = _new_offsets(g, widen)
    for t in g.tables:
        if t.uv_size in (8, 12):
            y[t.entry + 0x07] = 0
            y[t.entry + 0x27] = 20
    for b, u in widen.items():
        o = g.data_table2 + 16 * b
        y[o + 0x0A] = 0
        o = g.data_table2 + 16 * u
        struct.pack_into('<I', y, o, 20 * g.dt2[u][1])
        y[o + 0x08] = 0x14
        y[o + 0x0A] = 0
    for i, off in offs.items():
        struct.pack_into('<I', y, g.data_table2 + 16 * i + 12, g.local_uv_offset + off)
    end = max(offs[i] + (20 * g.dt2[i][1] if i in widen.values() else g.dt2[i][0]) for i in offs)
    struct.pack_into('<I', y, 0x0C, g.local_uv_offset + ((end + 0x7F) & ~0x7F))
    return bytes(y)


def volatile(v, xv, g, widen):
    """rebuild the PC volatile v (converted from the 360 volatile xv) with
    the widened streams, read from the 360 data"""
    if not widen:
        return v
    offs, grow = _new_offsets(g, widen)
    streams = sorted((g.dt2[i][3] - g.local_uv_offset, i) for i in offs)
    out = bytearray()
    pos = 0
    for off, i in streams:
        size, count = g.dt2[i][0], g.dt2[i][1]
        out += v[pos:off]                         # anything between streams
        if i in widen.values():
            stride = size // count
            for k in range(count):
                w = xv[off + stride * k:off + stride * (k + 1)]
                colour = w[8:12] if stride == 12 else DEFAULT_COLOUR
                out += w[3::-1] + w[7:3:-1] + TAIL + colour
        else:
            out += v[off:off + size]
        pos = off + size
    out += bytes(-len(out) % 0x80)                 # the PC pads the volatile to 0x80
    return bytes(out)
