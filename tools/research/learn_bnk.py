"""Learns ds2/bnk_model.pkl (animation banks) from the pairs; reports
held-out and full scores."""
import sys, pickle, collections, os
import pairs
from ds2 import reloc

def score(model, P):
    c = collections.Counter()
    for k, x, p in P:
        y = model.convert(x)
        c['none' if y is None else 'exact' if y == p else 'size' if len(y) != len(p) else 'wrong'] += 1
    return dict(c)

P = [q for q in pairs.load('BNK') if len(q[1]) == len(q[2])]
for name, tr, te in (('held-out', P[::2], P[1::2]), ('all', P, P)):
    m = reloc.Model()
    for k, x, p in tr: m.train(x, p)
    m.finish()
    print(name, score(m, te), 'types', len(m.perms))
pickle.dump(m, open(os.path.join(os.path.dirname(__file__) or '.', 'ds2', 'bnk_model.pkl'), 'wb'))
