"""Learns a per-file-position byte-order template for small fixed-layout
types (ANIM): ds2/<type>_postmpl.pkl.   python3 learn_postmpl.py ANIM"""
import os, pickle, sys
import pairs
from ds2 import templates as T

typ = sys.argv[1]
P = [q for q in pairs.load(typ) if len(q[1]) == len(q[2])]
n = max(len(x) for k, x, p in P) // 4
t = T.Template(n)
for k, x, p in P:
    t.train(x, p)
pm = t.perms(swap_default_words=n, raw_min=2)
pickle.dump(pm, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ds2', typ.lower() + '_postmpl.pkl'), 'wb'))
print(typ, len(P), 'pairs,', n, 'positions')
