"""Mesh 360 -> PC: learn header templates and vertex slot conversions from
the pairs, and score with tolerance (packed normals/tangents within 1 per
byte; everything else exact)."""
import collections, struct, math, sys
import pairs
from ds2 import mesh as MS, templates as T


def ub(v):
    return max(0, min(255, int(math.floor((v + 1.0) * 127.5))))


def conv_dec3n(w):
    v, a = MS.dec3n(struct.unpack('>I', w)[0])
    return bytes([ub(v[0]), ub(v[1]), ub(v[2]), 255])


def conv_byte4n_rev(w):
    s = [b - 256 if b >= 128 else b for b in w[::-1]]
    return bytes(ub(max(-1.0, c / 127.0)) for c in s)


SLOT = {
    'f32': lambda w: w[::-1],
    'raw': lambda w: w,
    'h2': lambda w: w[1::-1] + w[3:1:-1],
    'dec3n': conv_dec3n,
    'byte4n_rev': conv_byte4n_rev,
}


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def internal(s, x):
    return s['offset'] >= 0x100 and s['offset'] + s['count'] * s['stride'] <= len(x)


def stream_key(s):
    return (s['stride'], s['type'], s['flags'])


def learn(P):
    slots = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    headers = {}
    for k, x, p in P:
        if len(x) != len(p):
            continue
        S = [s for s in MS.streams(x) if internal(s, x)]
        if [(s['count'], s['stride']) for s in MS.streams(x)] != [(s['count'], s['stride']) for s in MS.streams(p, False)]:
            continue   # different geometry on PC: not a conversion example
        first = min([s['offset'] for s in S] + [len(x)])
        first = min(first, MS.header_end(x))
        h = headers.setdefault(first, T.Template(first // 4))
        h.train(x[:first], p[:first])
        for s in S:
            if s['type'] == 1 or s['stride'] % 4:
                continue
            key = stream_key(s)
            for v in range(min(s['count'], 64)):
                for slot in range(s['stride'] // 4):
                    o = s['offset'] + s['stride'] * v + 4 * slot
                    w, q = x[o:o + 4], p[o:o + 4]
                    if w == b'\0\0\0\0':
                        continue
                    for name, f in SLOT.items():
                        y = f(w)
                        if y == q or (name in ('dec3n', 'byte4n_rev') and close(y, q, 1)):
                            slots[key][slot][name] += 1
    table = {}
    for key, d in slots.items():
        table[key] = [max(d[i].items(), key=lambda kv: (kv[1], kv[0] == 'f32'))[0] if d.get(i) else 'f32'
                      for i in range(key[0] // 4)]
    return headers, table


def convert(model, x):
    headers, table = model
    S = [s for s in MS.streams(x) if internal(s, x)]
    first = min([s['offset'] for s in S] + [len(x)])
    first = min(first, MS.header_end(x))
    h = headers.get(first)
    if h is None:
        return None
    out = bytearray(x)
    out[:first] = T.apply(h.perms(), x[:first])
    for s in S:
        o0, n, st = s['offset'], s['count'], s['stride']
        if s['type'] == 1:     # index buffer: u16
            for i in range(o0, o0 + n * st - 1, 2):
                out[i], out[i + 1] = x[i + 1], x[i]
            continue
        conv = table.get(stream_key(s))
        if conv is None:
            return None
        for v in range(n):
            for slot, name in enumerate(conv):
                o = o0 + st * v + 4 * slot
                out[o:o + 4] = SLOT[name](x[o:o + 4])
    return bytes(out)


def score(model, P):
    c = collections.Counter()
    for k, x, p in P:
        if len(x) != len(p):
            c['size differs'] += 1
            continue
        if [(s['count'], s['stride']) for s in MS.streams(x)] != [(s['count'], s['stride']) for s in MS.streams(p, False)]:
            c['different geometry'] += 1
            continue
        y = convert(model, x)
        if y is None:
            c['unknown layout'] += 1
        elif y == p:
            c['exact'] += 1
        else:
            bad = sum(1 for i in range(len(p)) if abs(y[i] - p[i]) > 1)
            c['within tolerance' if bad == 0 else 'wrong'] += 1
    return c


if __name__ == '__main__':
    typ = sys.argv[1] if len(sys.argv) > 1 else 'Mesh'
    P = pairs.load(typ)
    m = learn(P[0::2])
    print(typ, 'held-out half:', dict(score(m, P[1::2])))
    m = learn(P)
    print(typ, 'all:', dict(score(m, P)))
    for k, v in sorted(m[1].items()):
        print('  stream', k, v)
