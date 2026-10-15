"""Classify every byte of structurally identical Mesh pairs into regions and
measure, per region slot, which conversion reproduces the PC bytes."""
import sys, collections, struct
import pairs
from ds2 import geo, templates as T


def same_structure(a, b):
    if a.table_count != b.table_count:
        return False
    for ta, tb in zip(a.tables, b.tables):
        for f in ['vert_count', 'face_count', 'lod_type', 'vert_size', 'vert_id', 'uv_size', 'name_offset', 'vert_offset', 'face_offset', 'bone_palette_offset']:
            if getattr(ta, f) != getattr(tb, f):
                return False
    return True


def rec_size(t):
    return 0x20 if t.vert_size == -1 else 0x14 if t.lod_type == 4 else 0x0C if t.lod_type == 5 else None


def region_map(d, g):
    """List of (start, end, label, record_size) for known regions."""
    R = [(0, 0x100, 'header', 0x100)]
    R.append((g.data_table1, g.data_table1 + geo.DT1_ENTRY * g.table_count, 'dt1', geo.DT1_ENTRY))
    R.append((g.data_table2, g.data_table2 + 16 * len(g.dt2), 'dt2', 16))
    for t in g.tables:
        rs = rec_size(t)
        if rs and t.vert_offset and t.vert_offset + rs * t.vert_count <= len(d):
            R.append((t.vert_offset, t.vert_offset + rs * t.vert_count, 'vert%X' % rs, rs))
        if t.face_offset and t.face_offset + 2 * t.face_count <= len(d):
            R.append((t.face_offset, t.face_offset + 2 * t.face_count, 'faces', 2))
        if t.bone_palette_offset and t.palette_count:
            R.append((t.bone_palette_offset, t.bone_palette_offset + 2 * t.palette_count, 'palette', 2))
        if t.name_offset:
            e = d.find(b'\0', t.name_offset)
            R.append((t.name_offset, e + 1, 'name', 1))
    return R


if __name__ == '__main__':
    P = pairs.load('Mesh')
    tmpl = {}
    cover = collections.Counter()
    total = 0
    for k, x, p in P:
        if len(x) != len(p):
            continue
        a, b = geo.parse(x, True), geo.parse(p, False)
        if not same_structure(a, b):
            continue
        total += len(x)
        for s, e, label, rs in region_map(x, a):
            cover[label] += e - s
            if rs % 4 == 0:
                for o in range(s, e - rs + 1, rs):
                    t = tmpl.setdefault(label, T.Template(rs // 4))
                    t.train(x[o:o + rs], p[o:o + rs])
    print('bytes covered by region (of %d):' % total, dict(cover))
    for label, t in tmpl.items():
        perms = t.perms()
        bad = [(i * 4, max(t.counts[i]), t.informative[i]) for i in range(t.n) if t.informative[i] and max(t.counts[i]) < t.informative[i] * 0.995]
        print(label, 'samples', t.samples, 'perms', ''.join('=' if p == (0, 1, 2, 3) else 'S' if p == (3, 2, 1, 0) else 'h' if p == (1, 0, 3, 2) else 'U' if p == T.UNION else '?' for p in perms))
        print('    slots not explained by a byte permutation (offset, best fit, informative):', bad[:12])
