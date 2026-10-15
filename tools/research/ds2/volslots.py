"""MeshVolatile 360 -> PC: the volatile holds the mesh's external vertex
streams; mesh DataTable2 descriptors with ptr >= local_uv_offset point into
it at (ptr - local_uv_offset). Each 4-byte slot of a stream is converted
by the rule learned per stream format (learn_volatile.py ->
volatile_table.pkl)."""
from . import meshconv as MC

SLOT = {
    'f32': lambda w: w[::-1],
    'raw': lambda w: w,
    'h2': lambda w: w[1::-1] + w[3:1:-1],
    'normal': MC.normal,
    't32': MC.tangent32,
    't20': MC.tangent20,
}


def fmt_key(flags):
    return flags.hex()


def streams_in_volatile(g, vsize):
    out = []
    for size, count, flags, ptr in g.dt2:
        if ptr >= g.local_uv_offset and count:
            off = ptr - g.local_uv_offset
            stride = size // count if count else 0
            if off + size <= vsize and stride and stride % 4 == 0:
                out.append((off, count, stride, flags))
    return out


def convert(table, g, x):
    out = bytearray(x)
    done = bytearray(len(x))
    for off, count, stride, flags in streams_in_volatile(g, len(x)):
        conv = table.get((fmt_key(flags), stride))
        if conv is None:
            return None
        for v in range(count):
            for slot, name in enumerate(conv):
                o = off + stride * v + 4 * slot
                out[o:o + 4] = SLOT[name](x[o:o + 4])
        done[off:off + stride * count] = b'\1' * (stride * count)
    # the rest (per-table UV records of skinned / 0x14 tables) is floats
    for i in range(0, len(x) - 3, 4):
        if not done[i]:
            out[i:i + 4] = x[i:i + 4][::-1]
    return bytes(out)
