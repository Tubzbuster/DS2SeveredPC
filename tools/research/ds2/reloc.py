"""Formats that end in a relocation table (word 0 = table offset; the table
lists, big-endian, every offset in the file that holds a pointer, ending
in 0), e.g. BNK animation banks. Pointers split the file into blocks; a
block's type is (parent type, offset of the pointer in the parent), found
from the root. Each block type gets a learned byte-permutation template
(ds2.templates); pointers and the table are always 32-bit swapped.
"""
import re
import struct
from . import templates as T

_TEXT = re.compile(rb'[A-Za-z0-9_.\-/ ]{4,}\x00')

MAX_WORDS = 1 << 14


def parse(x):
    if len(x) < 8:
        return None
    R = struct.unpack_from('>I', x, 0)[0]
    if not 0 < R < len(x) or (len(x) - R) % 4:
        return None
    n = (len(x) - R) // 4
    ents = struct.unpack_from('>%dI' % n, x, R)
    if ents[-1] != 0:
        return None
    ptrs = {}
    for e in ents[:-1]:
        if e % 4 or e + 4 > R:
            return None
        v = struct.unpack_from('>I', x, e)[0]
        if v > R:
            return None
        ptrs[e] = v
    starts = sorted(set(ptrs.values()) | {0, R})
    bounds = {s: (starts[i + 1] if i + 1 < len(starts) else len(x)) for i, s in enumerate(starts)}
    # types by breadth-first walk from the root
    types = {0: ('root',)}
    order = [0]
    by_block = {}
    for f, v in sorted(ptrs.items()):
        import bisect
        i = bisect.bisect_right(starts, f) - 1
        by_block.setdefault(starts[i], []).append((f, v))
    k = 0
    while k < len(order):
        b = order[k]; k += 1
        for f, v in by_block.get(b, []):
            if v not in types:
                # parent's own field offset + this pointer's offset + the
                # child's first byte (node kind)
                types[v] = (types[b][1] if len(types[b]) > 1 else -1, f - b, _kind(x, v))
                order.append(v)
    return dict(R=R, ptrs=ptrs, bounds=bounds, types=types)


def _kind(x, v):
    """what a block starts with: a hash followed by a small codec / version
    word (animation data) -> ('h', word); otherwise its first byte"""
    if v + 8 > len(x):
        return -1
    a, b = struct.unpack_from('>II', x, v)
    if a > 0xFFFFFF and b < 0x100:
        return ('h', b)
    return x[v]


def blocks(info):
    for s, e in info['bounds'].items():
        if s == info['R']:
            continue
        yield s, e, info['types'].get(s, ('orphan',))


class Model:
    def __init__(self):
        self.t = {}

    def train(self, x, p):
        info = parse(x)
        if info is None or len(x) != len(p):
            return
        for s, e, typ in blocks(info):
          for key in self.keys(typ):
            n = min((e - s) // 4, MAX_WORDS)
            tm = self.t.get(key)
            if tm is None or tm.n < n:
                old = tm
                tm = T.Template(n)
                if old:
                    for i in range(old.n):
                        tm.counts[i] = old.counts[i]
                        tm.informative[i] = old.informative[i]
                    tm.samples = old.samples
                self.t[key] = tm
            tm.train(x[s:s + 4 * n], p[s:s + 4 * n])

    @staticmethod
    def keys(typ):
        """most to least specific: full type, (pointer offset, kind),
        (kind,), any block"""
        if len(typ) == 3:
            return [typ, ('f', typ[1], typ[2]), ('k', typ[2]), ('any',)]
        return [typ, ('any',)]

    def finish(self):
        self.perms = {k: v.perms(swap_default_words=64) for k, v in self.t.items()}
        self.samples = {k: v.samples for k, v in self.t.items()}
        self.majority = {}
        for k, v in self.t.items():
            sw = sum(c[T.SWAP] for c in v.counts)
            rw = sum(c[T.RAW] for c in v.counts)
            self.majority[k] = T.PERMS[T.SWAP] if sw > rw else T.PERMS[T.RAW]
        del self.t
        return self

    def convert(self, x):
        info = parse(x)
        if info is None:
            return None
        out = bytearray(x)
        for s, e, typ in blocks(info):
            pm = None
            for key in self.keys(typ):
                if key in self.perms and self.samples.get(key, 0) >= 3:
                    pm = self.perms[key]
                    break
            if pm is None:
                continue
            n = (e - s) // 4
            if n > len(pm):
                # longer than any training block: small structure blocks
                # continue with the template's majority order (records
                # repeat); large ones (animation data) stay raw
                fill = self.majority[key] if n <= 256 and key != ('any',) else T.PERMS[T.RAW]
                pm = pm + [fill] * (n - len(pm))
            out[s:s + 4 * n] = T.apply(pm[:n], x[s:s + 4 * n])
        # names: printable runs of 4+ bytes ending in NUL stay as they are
        # (whole words inside the run, the '_' padding excluded)
        for m in _TEXT.finditer(x, 0, info['R']):
            a, b = m.start(), m.end()
            core = x[a:b - 1].strip(b'_')
            if len(core) < 3 or sum(c >= 0x41 for c in core) < 2:
                continue
            a = a + (len(x[a:b - 1]) - len(x[a:b - 1].lstrip(b'_')))   # skip leading padding
            for w in range((a + 3) // 4 * 4, b // 4 * 4, 4):
                out[w:w + 4] = x[w:w + 4]
            w = b // 4 * 4                     # word holding the NUL
            if a <= w < b and all(32 <= c < 127 or c == 0 for c in x[w:w + 4]) and w + 4 <= info['R'] and x[w + 3:w + 4] in (b'\0', b'_'):
                out[w:w + 4] = x[w:w + 4]
        for f in info['ptrs']:
            out[f:f + 4] = x[f:f + 4][::-1]
        R = info['R']
        n = (len(x) - R) // 4
        out[R:] = struct.pack('<%dI' % n, *struct.unpack_from('>%dI' % n, x, R))
        out[0:4] = x[0:4][::-1]
        return bytes(out)
