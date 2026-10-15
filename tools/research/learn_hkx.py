"""Learns ds2/hkx_model.pkl from the HKX pairs; held-out and full scores."""
import collections, os, pickle, sys
import pairs
from ds2 import hkx


def score(m, P):
    c = collections.Counter(); badw = totw = 0
    for k, x, p in P:
        y = hkx.convert(m, x)
        if y is None: c['none'] += 1; continue
        c['exact' if y == p else 'wrong'] += 1
        n = len(x) // 4
        badw += sum(1 for i in range(n) if y[4*i:4*i+4] != p[4*i:4*i+4]); totw += n
    return dict(c), badw, totw


P = [q for q in pairs.load('HKX') if len(q[1]) == len(q[2])]
for name, tr, te in (('held-out', P[::2], P[1::2]), ('all', P, P)):
    m = hkx.new_model()
    for k, x, p in tr: m.train(x, p)
    m.finish()
    print(name, score(m, te), 'types', len(m.perms))
pickle.dump(m, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ds2', 'hkx_model.pkl'), 'wb'))
