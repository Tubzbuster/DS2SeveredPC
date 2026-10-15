"""Learns ds2/<type>_model.pkl for a relocation-table type (BNK, RCB) from
the pairs; held-out and full scores.   python3 learn_reloc.py RCB"""
import collections, os, pickle, sys
import pairs
from ds2 import reloc


def score(m, P):
    c = collections.Counter(); bad = tot = 0
    for k, x, p in P:
        y = m.convert(x)
        if y is None: c['none'] += 1; continue
        c['exact' if y == p else 'wrong'] += 1
        n = len(x) // 4
        bad += sum(1 for i in range(n) if y[4*i:4*i+4] != p[4*i:4*i+4]); tot += n
    return dict(c), bad, tot


typ = sys.argv[1]
DEFAULT = {'BNK': 'raw', 'RCB': 'swap'}
P = [q for q in pairs.load(typ) if len(q[1]) == len(q[2])]
for name, tr, te in (('held-out', P[::2], P[1::2]), ('all', P, P)):
    m = reloc.Model(DEFAULT.get(typ, 'raw'))
    for k, x, p in tr: m.train(x, p)
    m.finish()
    print(typ, name, score(m, te), 'types', len(m.perms))
pickle.dump(m, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ds2', typ.lower() + '_model.pkl'), 'wb'))
