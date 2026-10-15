"""Learn VFX component templates from the pairs; report how many pairs a
template-based conversion reproduces exactly (train on half, test on half
as well as on all)."""
import collections, pickle, sys
import pairs
from ds2 import templates as T, vfx as V


def learn(P):
    tmpl = {}
    for k, x, p in P:
        if len(x) != len(p) or len(x) % 4:
            continue
        for key, s, e in V.segments(x):
            t = tmpl.get(key)
            if t is None:
                t = tmpl[key] = T.Template((e - s) // 4)
            t.train(x[s:e], p[s:e])
    return tmpl


def convert(tmpl, x):
    out = bytearray()
    for key, s, e in V.segments(x):
        t = tmpl.get(key)
        if t is None:
            return None
        out += T.apply(t.perms(), x[s:e])
    return bytes(out)


def score(tmpl, P):
    c = collections.Counter()
    for k, x, p in P:
        y = convert(tmpl, x)
        c['unknown segment' if y is None else 'exact' if y == p else 'wrong'] += 1
    return c


if __name__ == '__main__':
    P = pairs.load('VFX')
    even, odd = P[0::2], P[1::2]
    t_half = learn(even)
    print('train on half -> other half:', dict(score(t_half, odd)))
    t_all = learn(P)
    print('train on all -> all:', dict(score(t_all, P)), ' templates:', len(t_all))
    pickle.dump({k: (t.perms(), t.samples) for k, t in t_all.items()}, open('ds2/vfx_templates.pkl', 'wb'))
