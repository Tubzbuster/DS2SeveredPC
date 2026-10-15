"""Mesh 360 -> PC, structure-aware: the header holds pointers to tables
(0x4C, 0x50, 0x54, 0x60, 0x68, 0x6C, 0x78, 0x7C); the asset is cut at those
pointers and at internal vertex/index streams into labelled regions.
Regions are converted with learned byte-permutation templates; vertex
streams with the per-slot rules from learn_mesh."""
import collections, struct, sys
import pairs, learn_mesh as L
from ds2 import mesh as MS, templates as T

PTRS = {0x4C: 'p4C', 0x50: 'p50', 0x54: 'p54', 0x60: 'p60', 0x68: 'streams', 0x6C: 'streams_end', 0x78: 'p78', 0x7C: 'p7C'}


def regions(x, be=True):
    E = '>' if be else '<'
    n = len(x)
    starts = {0: 'header'}
    for off, name in PTRS.items():
        v = struct.unpack_from(E + 'I', x, off)[0]
        if 0 < v < n and v not in starts:
            starts[v] = name
    S = [s for s in MS.streams(x, be) if L.internal(s, x)]
    for i, s in enumerate(S):
        starts[s['offset']] = ('stream', i)
        e = s['offset'] + s['count'] * s['stride']
        if e < n and e not in starts:
            starts[e] = ('after_stream', i)
    pos = sorted(starts)
    out = []
    for a, b in zip(pos, pos[1:] + [n]):
        out.append((starts[a], a, b))
    return out, S


def learn(P):
    tm = {}
    _, table = L.learn(P)
    for k, x, p in P:
        if len(x) != len(p) or regions(x)[0] != [(r[0], r[1], r[2]) for r in regions(p, False)[0]]:
            continue
        R, S = regions(x)
        for name, a, b in R:
            if isinstance(name, tuple) and name[0] == 'stream':
                continue
            key = (name, b - a)
            t = tm.get(key)
            if t is None:
                t = tm[key] = T.Template((b - a) // 4)
            t.train(x[a:b], p[a:b])
    return tm, table


def convert(model, x):
    tm, table = model
    R, S = regions(x)
    out = bytearray(x)
    for name, a, b in R:
        if isinstance(name, tuple) and name[0] == 'stream':
            s = S[name[1]]
            if s['type'] == 1:
                for i in range(a, b - 1, 2):
                    out[i], out[i + 1] = x[i + 1], x[i]
                continue
            conv = table.get(L.stream_key(s))
            if conv is None:
                return None, ('stream', L.stream_key(s))
            for v in range(s['count']):
                for slot, cname in enumerate(conv):
                    o = a + s['stride'] * v + 4 * slot
                    out[o:o + 4] = L.SLOT[cname](x[o:o + 4])
            continue
        t = tm.get((name, b - a))
        if t is None:
            return None, (name, b - a)
        out[a:b] = T.apply(t.perms(), x[a:b])
    out[8:12] = struct.pack('<I', 3)   # platform: 360 = 1, PC = 3
    return bytes(out), None


def score(model, P):
    c = collections.Counter()
    missing = collections.Counter()
    for k, x, p in P:
        if len(x) != len(p):
            c['size differs'] += 1
            continue
        y, why = convert(model, x)
        if y is None:
            c['unknown region'] += 1
            missing[why[0] if isinstance(why[0], str) else str(why[0])] += 1
        elif y == p:
            c['exact'] += 1
        else:
            bad = sum(1 for i in range(len(p)) if abs(y[i] - p[i]) > 1)
            c['within tolerance' if bad == 0 else 'wrong (%s)' % ('<1%' if bad < len(p) / 100 else '>1%')] += 1
    return c, missing


if __name__ == '__main__':
    P = pairs.load(sys.argv[1] if len(sys.argv) > 1 else 'Mesh')
    m = learn(P[0::2])
    c, miss = score(m, P[1::2])
    print('held-out:', dict(c), ' unknown regions:', miss.most_common(6))
    m = learn(P)
    c, miss = score(m, P)
    print('all:', dict(c), ' unknown regions:', miss.most_common(6))
