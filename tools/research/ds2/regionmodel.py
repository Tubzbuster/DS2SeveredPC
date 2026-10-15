"""Byte-order model for files laid out as a fixed header plus arrays found
through header offset fields (Graph, ISM).

The file is cut into regions at the values of the header's offset fields
(each region named by the field that points at it, ending where the next
one starts). Each region is read in 4-byte units from its own start (a
2-byte unit at an odd end). A unit's byte order is looked up by
(region, position mod stride, unit size); the stride of each region is
the one that predicts the training pairs best (leave-one-file-out).
Units that read the same under every order (0, -1, ...) are not counted.

The model is plain JSON so it can be shipped with the installer.
"""
import json, struct
from collections import Counter, defaultdict

PERMS4 = {
    'swap': lambda a: a[::-1],
    'raw': lambda a: a,
    'u16': lambda a: a[1::-1] + a[:1:-1],     # two u16
    'u16a': lambda a: a[1::-1] + a[2:],       # u16, 2 bytes
    'au16': lambda a: a[:2] + a[:1:-1],       # 2 bytes, u16
}
PERMS2 = {'swap': lambda a: a[::-1], 'raw': lambda a: a}
STRIDES = [4, 8, 12, 16, 20, 24, 32, 36, 40, 44, 48, 56, 64, 0x50, 0x60, 0x80]
ABS = 0


def _perms(n):
    return PERMS4 if n == 4 else PERMS2


def regions(x, header, fields):
    starts = {}
    for f in fields:
        v = struct.unpack_from('>I', x, f)[0]
        if header <= v < len(x) and v % 2 == 0 and v not in starts:
            starts[v] = f
    st = sorted(starts)
    out = [('hdr', 0, min(header, len(x)))]
    if st and st[0] > header:
        out.append(('gap', header, st[0]))
    for i, s in enumerate(st):
        out.append((str(starts[s]), s, st[i + 1] if i + 1 < len(st) else len(x)))
    return out


def units(x, header, fields):
    for name, s, e in regions(x, header, fields):
        o = s
        while o < e:
            n = 4 if o + 4 <= e else e - o
            yield name, o - s, o, n
            o += n


def labels(a, b):
    return [k for k, f in _perms(len(a)).items() if f(a) == b] if len(a) in (2, 4) else []


def _key(stride, rel, n):
    return '%d,%d' % (rel if stride == ABS else rel % stride, n)


class Model:
    def __init__(self, header, fields, strides=None, tables=None):
        self.header, self.fields = header, list(fields)
        self.strides, self.tables = strides or {}, tables or {}

    # -- training --------------------------------------------------------
    @classmethod
    def train(cls, pairs, header, fields):
        cand = STRIDES + [ABS]
        tot = defaultdict(lambda: defaultdict(Counter))      # (region, stride) -> key -> labels
        per = []
        for x, c in pairs:
            if len(x) != len(c):
                continue
            own = defaultdict(lambda: defaultdict(Counter))
            us = []
            for name, rel, o, n in units(x, header, fields):
                L = labels(x[o:o + n], c[o:o + n])
                us.append((name, rel, n, L))
                if not L or len(L) == len(_perms(n)):
                    continue
                for s in cand:
                    for l in L:
                        own[(name, s)][_key(s, rel, n)][l] += 1
            for k, t in own.items():
                for kk, cn in t.items():
                    tot[k][kk].update(cn)
            per.append((us, own))
        err = Counter()
        for us, own in per:
            for name, rel, n, L in us:
                if not L or len(L) == len(_perms(n)):
                    continue
                for s in cand:
                    k = _key(s, rel, n)
                    cn = tot[(name, s)][k] - own[(name, s)][k]
                    pr = cn.most_common(1)[0][0] if cn else 'swap'
                    if pr not in L:
                        err[(name, s)] += 1
        names = {name for name, _ in tot}
        strides, tables = {}, {}
        for name in names:
            s = min(cand, key=lambda s: (err[(name, s)], s if s else 1 << 30))
            strides[name] = s
            tables[name] = {k: cn.most_common(1)[0][0] for k, cn in tot[(name, s)].items()
                            if cn.most_common(1)[0][0] != 'swap'}
        return cls(header, fields, strides, tables)

    # -- use -------------------------------------------------------------
    def convert(self, x):
        out = bytearray(len(x))
        for name, rel, o, n in units(x, self.header, self.fields):
            s = self.strides.get(name, ABS)
            pr = self.tables.get(name, {}).get(_key(s, rel, n), 'swap')
            out[o:o + n] = _perms(n)[pr](x[o:o + n]) if n in (2, 4) else x[o:o + n]
        return bytes(out)

    def save(self, path):
        json.dump(dict(header=self.header, fields=self.fields, strides=self.strides, tables=self.tables),
                  open(path, 'w'), indent=0, sort_keys=True)

    @classmethod
    def load(cls, path):
        d = json.load(open(path))
        return cls(d['header'], d['fields'], d['strides'], d['tables'])
