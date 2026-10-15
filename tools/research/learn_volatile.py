"""MeshVolatile 360 -> PC: the volatile holds the mesh's external vertex
streams; mesh DataTable2 descriptors with ptr >= local_uv_offset point into
it at (ptr - local_uv_offset). Learn per stream format (stride, type, flag)
the conversion of each 4-byte slot, then score (packed vectors within 1)."""
import collections, struct, sys, pickle
import pairs
from ds2 import streamfile, geo, meshconv as MC

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


def candidates(meshes, vol):
    """Meshes this volatile may belong to: same base name, external streams
    that fit. (In a real stream file the volatile directly follows its mesh;
    the type-split training data lost that order, hence candidates.)"""
    base = vol.name.lower()
    base = base[:-len('.volatile')] if base.endswith('.volatile') else base
    out = []
    for m in meshes.get(base, []):
        g = geo.parse(m[1], m[0])
        need = max([ptr - g.local_uv_offset + size for size, count, flags, ptr in g.dt2 if ptr >= g.local_uv_offset] + [0])
        if 0 < need <= vol.usize <= need + 0x1000:
            out.append(g)
    return out


def find_mesh(meshes, vol, pc_payload=None, table=None):
    c = candidates(meshes, vol)
    if not c:
        return None
    if len(c) == 1 or pc_payload is None or table is None:
        return c[0]
    x = vol.payload()
    def err(g):
        y = convert(table, g, x)
        return len(x) if y is None else sum(1 for i in range(0, len(x), 64) if abs(y[i] - pc_payload[i]) > 1)
    return min(c, key=err)


def load_meshes(path, be):
    d = collections.defaultdict(list)
    for a in streamfile.read(open(path, 'rb').read())[1]:
        d[a.name.lower()].append((be, a.payload()))
    return d


def learn(P, meshes):
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for k, xv, pv in P:
        if len(xv.payload()) != len(pv.payload()):
            continue
        g = find_mesh(meshes, xv)
        if g is None:
            continue
        x, p = xv.payload(), pv.payload()
        for off, count, stride, flags in streams_in_volatile(g, len(x)):
            for v in range(0, count, max(1, count // 64)):
                for slot in range(stride // 4):
                    o = off + stride * v + 4 * slot
                    w, q = x[o:o + 4], p[o:o + 4]
                    if w == b'\0\0\0\0' and q == w:
                        continue
                    for name, f in SLOT.items():
                        y = f(w)
                        if y == q or (name in ('normal', 't32', 't20') and all(abs(a - b) <= 1 for a, b in zip(y, q))):
                            counts[(fmt_key(flags), stride)][slot][name] += 1
    table = {}
    for key, d in counts.items():
        table[key] = [max(d[i].items(), key=lambda kv: kv[1])[0] if d.get(i) else 'f32' for i in range(key[1] // 4)]
    return table


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


def score(table, P, meshes):
    c = collections.Counter()
    for k, xv, pv in P:
        x, p = xv.payload(), pv.payload()
        if len(x) != len(p):
            c['different size'] += 1; continue
        g = find_mesh(meshes, xv, p, table)
        if g is None:
            c['mesh not found'] += 1; continue
        y = convert(table, g, x)
        if y is None:
            c['unknown stream format'] += 1; continue
        bad = sum(1 for i in range(len(p)) if abs(y[i] - p[i]) > 1)
        c['exact' if y == p else 'within tolerance' if bad == 0 else 'wrong (<0.1%)' if bad < len(p) / 1000 else 'wrong'] += 1
    return c


if __name__ == '__main__':
    R = pairs.DEFAULT
    meshes = load_meshes(R + '/x360/Mesh.str', True)
    P = pairs.load('MeshVolatile', with_assets=True)
    t = learn(P[0::2], meshes); print('held-out:', dict(score(t, P[1::2], meshes)))
    t = learn(P, meshes); print('all:', dict(score(t, P, meshes)))
    for k, v in sorted(t.items()): print('  ', k, v)
    pickle.dump(t, open('ds2/volatile_table.pkl', 'wb'))
