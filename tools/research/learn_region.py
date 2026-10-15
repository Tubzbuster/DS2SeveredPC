"""Learns a region byte-order model (ds2/regionmodel.py) from PC/360 pairs
and writes ds2/<type>_model.json; prints a held-out score first.

    python3 learn_region.py Graph
"""
import os, sys
import pairs
from ds2 import regionmodel

CONFIG = {
    # header size, header words that hold offsets of the arrays
    'Graph': (0xA0, (0x20, 0x24, 0x28, 0x30, 0x34, 0x38, 0x40, 0x44, 0x48, 0x50, 0x58, 0x60, 0x68, 0x70)),
    'ISM': (0x20, (0x10, 0x14, 0x18, 0x1C)),
}


def score(model, ps):
    exact = ok = tot = 0
    for x, c in ps:
        y = model.convert(x)
        exact += y == c
        tot += len(c) // 4
        ok += sum(y[i:i + 4] == c[i:i + 4] for i in range(0, len(c) - 3, 4))
    return exact, len(ps), ok / max(tot, 1)


def main(typ):
    header, fields = CONFIG[typ]
    uniq = {}
    for _, x, c in pairs.load(typ):
        if len(x) == len(c):
            uniq.setdefault(x, c)
    ps = sorted(uniq.items(), key=lambda t: len(t[0]))
    held = regionmodel.Model.train(ps[::2], header, fields)
    print('held-out: %d/%d exact, %.4f%% of words' % (score(held, ps[1::2])[:2] + (100 * score(held, ps[1::2])[2],)))
    m = regionmodel.Model.train(ps, header, fields)
    print('training: %d/%d exact' % score(m, ps)[:2])
    m.save(os.path.join(os.path.dirname(__file__), 'ds2', typ.lower() + '_model.json'))


if __name__ == '__main__':
    main(sys.argv[1])
