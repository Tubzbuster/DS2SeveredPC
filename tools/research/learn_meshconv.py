import sys, collections, pickle
import pairs, mesh_regions as MR
from ds2 import geo, templates as T, meshconv as MC


def learn(P):
    tm = {}
    for k, x, p in P:
        if len(x) != len(p):
            continue
        a, b = geo.parse(x, True), geo.parse(p, False)
        if not MR.same_structure(a, b):
            continue
        for s, e, label, rs in MR.region_map(x, a):
            if label in ('header', 'dt1', 'dt2'):
                for o in range(s, e - rs + 1, rs):
                    tm.setdefault(label, T.Template(rs // 4)).train(x[o:o + rs], p[o:o + rs])
    return {k: t.perms() for k, t in tm.items()}


def score(tmpl, P):
    c = collections.Counter(); badbytes = collections.Counter()
    for k, x, p in P:
        if len(x) != len(p):
            c['different layout'] += 1; continue
        a, b = geo.parse(x, True), geo.parse(p, False)
        if not MR.same_structure(a, b):
            c['different layout'] += 1; continue
        y = MC.convert(x, tmpl)
        if y == p:
            c['exact'] += 1; continue
        bad = sum(1 for i in range(len(p)) if abs(y[i] - p[i]) > 1)
        c['within tolerance' if bad == 0 else 'wrong (<0.1%)' if bad < len(p) / 1000 else 'wrong'] += 1
    return c


if __name__ == '__main__':
    P = pairs.load(sys.argv[1] if len(sys.argv) > 1 else 'Mesh')
    t = learn(P[0::2]); print('held-out:', dict(score(t, P[1::2])))
    t = learn(P); print('all:', dict(score(t, P)))
    pickle.dump(t, open('ds2/mesh_templates.pkl', 'wb'))
